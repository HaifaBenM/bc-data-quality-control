"""
Validation Axe B — Vérification des codes de référence BC.
100% dynamique via ExecutionPlan (refTableId + refFieldId depuis extension AL).
Lazy load automatique depuis BC API si cache absent.
"""
import pandas as pd
from app.db.metadata_db import get_reference_values_by_table_id
from app.core.bc_order import sort_sheets_by_bc_order, get_bc_order_summary
from app.core.correction_classifier import classify_reference_anomaly
from app.core.execution_planner import resolve_key_field_in_columns


def validate_axe_b(
    df:             pd.DataFrame,
    table_id:       str,
    all_sheets:     dict,
    sheet_name:     str  = "",
    profile_code:   str  = "",
    company_id:     str  = "",
    sim_context     = None,
    metadata_loader = None,
    execution_plan  = None,
) -> list[dict]:
    """
    Axe B — Validation des références (≈ Valider Package BC).

    Pour chaque champ où validate_field = TRUE :
      ref_table_id = execution_plan.get_ref_table_id(table_id, field_name)
      ref_field_id = execution_plan.get_ref_field_id(table_id, field_name)
      valid_codes  = lazy_load(ref_table_id, ref_field_id) ∪ sim_context(ref_table_id)

    Lazy load : cache Supabase → extension AL tableValues → BC API v2.0 fallback.

    Chaque "Code de référence invalide" est en plus classifié :
      - VALEUR_CORRIGIBLE   : un code valide proche existe (faute de frappe
        probable) -> corrigible dans le fichier généré.
      - PREALABLE_BC_REQUIS : aucun code valide ne s'en rapproche -> le code
        n'existe pas côté BC, aucune correction de fichier n'est possible
        tant que la donnée maîtresse n'est pas créée dans BC.
    """
    anomalies = []
    if df is None or df.empty:
        return anomalies

    try:
        table_id_int = int(table_id) if table_id else 0
    except (ValueError, TypeError):
        table_id_int = 0

    if execution_plan and table_id_int:
        # AJOUTÉ (26/08/2026) — FIX RÉEL : une table qui référence ELLE-MÊME
        # (ex. Client → "N° client facturé", TableRelation = Customer, sur
        # la fiche Customer elle-même — auto-facturation par défaut, valeur
        # = son propre N° pour la quasi-totalité des lignes en pratique)
        # ne pouvait JAMAIS se valider correctement : sim_context n'est
        # peuplé pour une table qu'APRÈS l'avoir entièrement validée (pour
        # respecter l'ordre de dépendance BC entre tables DIFFÉRENTES) —
        # mais pendant qu'on valide CETTE table, son propre contexte est
        # encore vide, donc une auto-référence légitime ne matche jamais
        # rien. Diagnostic réel (26/08, fichier Client Aquachiara) : 1648
        # lignes sur 1664 avaient ce champ strictement égal à leur propre
        # N°, 0 vraie valeur différente — confirmé faux positif à 100%,
        # pas une vraie erreur BC. Fix ciblé : si sim_context ne connaît pas
        # encore CETTE table, on la pré-peuple avec ses propres clés
        # primaires (1ère colonne) AVANT la boucle de validation — ne
        # change rien à l'ordre inter-tables, comble seulement le cas
        # d'auto-référence intra-table.
        if sim_context is not None and not sim_context.has_table(table_id_int):
            try:
                _self_pks = [
                    str(v).strip() for v in df.iloc[:, 0]
                    if v is not None and str(v).strip() not in ("", "nan", "None")
                ]
                if _self_pks:
                    sim_context.add(table_id_int, _self_pks)
            except Exception:
                pass

        # AJOUTÉ (07/08/2026) — PERFORMANCE : avant ce fix, chaque colonne
        # validée déclenchait son propre appel get_reference_values_by_table_id
        # l'un après l'autre (jusqu'à 15+ appels séquentiels sur un onglet
        # comme "27 Article", dont plusieurs à froid = vrais allers-retours
        # BC live). On identifie d'abord TOUTES les (ref_tid, ref_fid)
        # distinctes nécessaires pour cet onglet, on les récupère EN
        # PARALLÈLE (ThreadPoolExecutor), puis la boucle ligne par ligne
        # ci-dessous consulte ce dict au lieu de rappeler la fonction —
        # comportement identique, juste la collecte réseau parallélisée.
        # Ne change RIEN à l'ordre de traitement des onglets eux-mêmes
        # (sim_context reste alimenté séquentiellement, dans l'ordre BC).
        _needed: dict[tuple[int, int], None] = {}
        for col in df.columns:
            # RÉVISÉ (18/08/2026) : critère fiable = le TYPE AL du champ
            # (Guid), pas son nom. Documenté par Microsoft comme pattern
            # standard de référence par SystemId (ex. `field(x; "Brand Id";
            # Guid) { TableRelation = "Car Brand".SystemId; }`) — vaut aussi
            # bien pour un champ standard BC que pour un champ d'extension,
            # puisque get_package_fields_qc() expose fieldType de la même
            # façon pour les deux, sans distinction à coder. Ces champs
            # contiennent le SystemId BC de l'enregistrement, pas un code
            # lisible — ils ne peuvent structurellement jamais matcher les
            # codes valides retournés pour la table référencée (toujours des
            # Code, jamais des GUID). Les valider produisait un faux positif
            # garanti à 100% sur chaque ligne (cf. export 251 du 18/08 :
            # 18 groupes confirmés existants côté BC, anomalie quand même
            # levée).
            #
            # CORRIGÉ (20/08/2026) : le repli par préfixe "ID " n'était
            # atteint QUE si _fmeta était None (`elif`) — si BC renvoie une
            # métadonnée pour la colonne mais avec un al_type incohérent
            # (autre que "Guid", résolution qui varie empiriquement selon la
            # table — confirmé : 251 "ID groupe compta. produit" correctement
            # filtré par type, mais 94 "ID groupe compta. stock" toujours
            # remonté en anomalie malgré ce fix, sur le même mécanisme), le
            # repli par nom n'était JAMAIS tenté. Les deux checks sont
            # désormais indépendants (OR, pas if/elif) — le nom sert de
            # filet de sécurité même quand une métadonnée existe mais se
            # trompe. Voir aussi clear_id_reference_columns() dans
            # correction_generator.py (même diagnostic, côté fichier de sortie).
            _fmeta = execution_plan.get_field_def(table_id_int, col)
            if (_fmeta is not None and _fmeta.al_type == "Guid") or col.startswith("ID "):
                continue
            if not execution_plan.validate_field_for(table_id_int, col):
                continue
            ref_tid = execution_plan.get_ref_table_id(table_id_int, col)
            if not ref_tid:
                continue
            # AJOUTÉ (26/08/2026) — demande Rami, cas réel Language Selection
            # (2000000050) : plage d'ID >= 2000000000 réservée par Microsoft
            # aux tables système/plateforme (System Application) — jamais des
            # données métier qu'un client peut ou doit créer. Confirmé faux
            # positif par comparaison avec les vraies erreurs BC (absent de
            # l'export réel). Exclu ici, avant même la collecte réseau —
            # aucune table de cette plage ne devrait jamais apparaître comme
            # prérequis, quel que soit le fichier.
            if ref_tid >= 2_000_000_000:
                continue
            ref_fid = execution_plan.get_ref_field_id(table_id_int, col)
            _needed[(ref_tid, ref_fid)] = None

        _ref_cache: dict[tuple[int, int], tuple[set, bool]] = {}
        # AJOUTÉ (07/08/2026) — PERFORMANCE, LE VRAI GOULOT : classify_reference_
        # anomaly() (fuzzy matching difflib contre TOUS les codes valides) était
        # appelée une fois PAR LIGNE, pas une fois par valeur distincte. Sur
        # Emplacement (3617 lignes) ou Article (791 lignes × colonnes), une même
        # valeur invalide répétée des centaines de fois relançait le même calcul
        # coûteux à chaque occurrence — le vrai facteur d'échelle des 5 minutes.
        # Mémorisé par (table référencée, valeur) : calculé une seule fois par
        # valeur distincte, réutilisé pour toutes ses répétitions.
        _classification_cache: dict[tuple[int, str], dict] = {}
        if _needed:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _fetch_ref(key: tuple[int, int]):
                tid, fid = key
                return key, get_reference_values_by_table_id(profile_code, company_id, tid, fid)

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(_fetch_ref, k) for k in _needed]
                for fut in as_completed(futures):
                    key, res = fut.result()
                    _ref_cache[key] = res

        for col in df.columns:
            # RÉVISÉ (18/08/2026) — même critère type Guid que ci-dessus.
            # CORRIGÉ (20/08/2026) — même fix que la boucle précédente : nom
            # et type vérifiés indépendamment (OR), pas en if/elif, pour que
            # le repli par nom fonctionne même quand une métadonnée existe
            # mais rapporte un al_type incohérent.
            _fmeta2 = execution_plan.get_field_def(table_id_int, col)
            if (_fmeta2 is not None and _fmeta2.al_type == "Guid") or col.startswith("ID "):
                continue
            if not execution_plan.validate_field_for(table_id_int, col):
                continue

            ref_tid = execution_plan.get_ref_table_id(table_id_int, col)
            if not ref_tid:
                continue
            # AJOUTÉ (26/08/2026) — voir commentaire identique plus haut
            # (collecte _needed) : tables système Microsoft (ID >= 2 Md),
            # jamais un vrai prérequis client.
            if ref_tid >= 2_000_000_000:
                continue

            # refFieldId — PK de la table relation (nouveau)
            ref_fid = execution_plan.get_ref_field_id(table_id_int, col)

            # Codes valides : lazy load BC (pré-récupéré en parallèle
            # ci-dessus) + simulation context intra-fichier
            bc_codes, found = _ref_cache.get((ref_tid, ref_fid), (set(), False))
            sim_codes   = sim_context.get_values(ref_tid) if sim_context else set()
            valid_codes = bc_codes | sim_codes

            if not found and not sim_codes:
                anomalies.append({
                    "Ligne":               0,
                    "Onglet":              sheet_name,
                    "Identifiant métier":      "",
                    "Champ":               col,
                    "Valeur":              "",
                    "Type d'anomalie":     "Code de référence non vérifiable",
                    "Sévérité":            "Info",
                    "Message":             (
                        f"Impossible de vérifier '{col}' : "
                        f"la table de référence (ID {ref_tid}) n'est pas accessible "
                        f"via l'extension AL ni le cache BC."
                    ),
                    "Correction suggérée": "",
                    "Axe":                 "B",
                    "Détail":              f"ref_table_id={ref_tid}, ref_field_id={ref_fid}",
                })
                continue

            # Table No. Series (ID 308) : quand ce champ ne résout à aucun code
            # valide (vide OU valeur invalide), BC échoue AUSSI en aval sur la
            # résolution automatique du numéro de série et lève une seconde
            # erreur distincte "Souches de n° n'existe pas. Code=''" — en plus
            # de l'erreur "Code de référence invalide" classique si la valeur
            # est non-vide. Confirmé empiriquement le 16/07/2026 sur dump BC
            # complet : 5/5 items (1017, 1019, ACC001, ACC002, ACC003).
            NO_SERIES_TABLE_ID = 308

            # AJOUTÉ (20/08/2026) : clé métier de la ligne (ex. N° article
            # "ACC001"), calculée une fois avant la boucle — même logique que
            # validator_axe_a.py, pour que chaque anomalie Axe B soit
            # identifiable sans réouvrir le fichier Excel (demande Rami).
            # RÉVISÉ (20/08/2026) : même filet de sécurité que validator_axe_a.py
            # — essaie l'alternative (N° <-> Code) si le champ configuré n'est
            # pas une colonne réelle de cet onglet.
            _key_field_b = (
                resolve_key_field_in_columns(table_id_int, df.columns) or "N°"
                if execution_plan else "N°"
            )

            # Valider chaque ligne
            for row_idx, row in df.iterrows():
                _key_val_b = str(row.get(_key_field_b, "") or "").strip() if _key_field_b in df.columns else ""
                value = str(row.get(col, "") or "").strip()
                is_val_empty = not value or value.lower() in ("nan", "none", "")
                is_zero_guid = value == "{00000000-0000-0000-0000-000000000000}"

                if ref_tid == NO_SERIES_TABLE_ID:
                    resolved = (
                        not is_val_empty and not is_zero_guid
                        and value in valid_codes
                    )
                    if not resolved:
                        anomalies.append({
                            "Ligne":               int(row_idx) + 4,
                            "Onglet":              sheet_name,
                            "Identifiant métier":      _key_val_b,
                            "Champ":               col,
                            "Valeur":              "",
                            "Type d'anomalie":     "Souches de n° non résolvable",
                            "Sévérité":            "Majeure",
                            "Message":             (
                                "Souches de n° n'existe pas. Champs et valeurs "
                                "d'identification : Code=''"
                            ),
                            "Correction suggérée": "",
                            # Rien à corriger dans le fichier : soit la souche
                            # de n° n'existe pas côté BC (créer table 308),
                            # soit c'est une conséquence de la valeur vide/GUID
                            # nul déjà couverte par "Code de référence invalide"
                            # ci-dessous — pas une anomalie corrigible en soi.
                            "Classification":      "PREALABLE_BC_REQUIS",
                            "Table référencée":    ref_tid,
                            "Axe":                 "B",
                            "BC":                  True,
                        })

                if is_val_empty or is_zero_guid:
                    continue

                if value not in valid_codes:
                    examples = sorted(valid_codes)[:3] if valid_codes else []
                    _cls_key = (ref_tid, value)
                    if _cls_key not in _classification_cache:
                        _classification_cache[_cls_key] = classify_reference_anomaly(value, valid_codes)
                    cls = _classification_cache[_cls_key]

                    if cls["classification"] == "VALEUR_CORRIGIBLE":
                        best_code, best_score = cls["suggestions"][0]
                        message = (
                            f"'{col}' = '{value}' n'existe pas dans la table référencée "
                            f"(ID {ref_tid}). Code proche trouvé : '{best_code}' "
                            f"(similarité {int(best_score * 100)}%) — probable faute de saisie."
                        )
                        corr_suggeree = best_code
                    else:
                        message = (
                            f"'{col}' = '{value}' n'existe dans aucune table référencée BC "
                            f"(ID {ref_tid}). Aucune valeur saisie ici ne sera valide tant que "
                            f"ce code n'est pas créé côté BC."
                            + (f" Exemples de codes valides existants : {examples}" if examples else "")
                        )
                        corr_suggeree = ""

                    anomalies.append({
                        "Ligne":               int(row_idx) + 4,
                        "Onglet":              sheet_name,
                        "Identifiant métier":      _key_val_b,
                        "Champ":               col,
                        "Valeur":              value,
                        "Type d'anomalie":     "Code de référence invalide",
                        "Sévérité":            "Majeure",
                        "Message":             message,
                        "Correction suggérée": corr_suggeree,
                        "Classification":      cls["classification"],
                        "Table référencée":    ref_tid,
                        "Axe":                 "B",
                        "BC":                  bool(valid_codes and found),
                    })

        # Nettoyage faux positifs sim_context
        if sim_context:
            try:
                for col in df.columns:
                    _ref_tid = execution_plan.get_ref_table_id(table_id_int, col)
                    if not _ref_tid:
                        continue
                    _sim = sim_context.get_values(_ref_tid)
                    if _sim:
                        anomalies = [
                            a for a in anomalies
                            if not (
                                a.get("Champ") == col
                                and str(a.get("Valeur", "")).strip() in _sim
                            )
                        ]
            except Exception:
                pass

        return anomalies

    # Pas d'execution_plan → INFO
    anomalies.append({
        "Ligne":               0,
        "Onglet":              sheet_name,
        "Identifiant métier":      "",
        "Champ":               "",
        "Valeur":              "",
        "Type d'anomalie":     "Validation références non disponible",
        "Sévérité":            "Info",
        "Message":             (
            f"Table {table_id} : impossible de valider les références (Axe B) "
            f"sans le plan d'exécution BC. "
            f"Assurez-vous que le package est sélectionné et l'extension AL déployée."
        ),
        "Correction suggérée": "",
        "Axe":                 "B",
    })
    return anomalies


def validate_file_axe_b(
    parse_result:   dict,
    profile_code:   str  = "",
    company_id:     str  = "",
    sim_context     = None,
    metadata_loader = None,
    execution_plan  = None,
) -> dict:
    """
    Lance la validation Axe B sur toutes les tables (data + ref).
    Ordre BC : Processing Order ASC, Table ID ASC.
    """
    result = {
        "total_anomalies": 0,
        "major":           0,
        "minor":           0,
        "info":            0,
        "lines_analyzed":  0,
        "by_sheet":        {},
        "all_anomalies":   [],
    }

    data_tables = parse_result.get("data_tables", [])
    ref_tables  = parse_result.get("ref_tables",  [])
    all_sheets  = parse_result.get("sheets",      {})
    metadata    = parse_result.get("metadata",    {})

    tables_to_validate = sort_sheets_by_bc_order(
        data_tables + ref_tables, metadata
    )

    # AJOUTÉ (07/08/2026) — FIX PERF MAJEUR : bc_cache_fn (passée au Trigger
    # Simulator) était appelée SANS AUCUNE mémorisation, une fois par
    # (ligne × règle OnInsert) — sur Article (791 lignes) ou Emplacement
    # (3617 lignes), ça fait des milliers d'appels réseau redondants pour
    # les MÊMES tables de référence répétées. Confirmé responsable de 354s
    # sur 368s de temps total mesuré (chronométrage du 07/08). Mémorisé une
    # fois par table de référence distincte, partagé sur tout le fichier
    # (pas juste un onglet), sans changer le résultat retourné.
    _trigger_bc_cache: dict[int, set] = {}

    def _cached_bc_cache_fn(tid: int) -> set:
        if tid not in _trigger_bc_cache:
            _trigger_bc_cache[tid] = get_reference_values_by_table_id(
                profile_code, company_id, tid
            )[0]
        return _trigger_bc_cache[tid]

    for sheet_name in tables_to_validate:
        df = all_sheets.get(sheet_name)
        if df is None or df.empty:
            continue

        meta     = metadata.get(sheet_name, {})
        table_id = meta.get("table_id", "")
        result["lines_analyzed"] += len(df)

        anomalies = validate_axe_b(
            df=df,
            table_id=table_id,
            all_sheets=all_sheets,
            sheet_name=sheet_name,
            profile_code=profile_code,
            company_id=company_id,
            sim_context=sim_context,
            metadata_loader=metadata_loader,
            execution_plan=execution_plan,
        )

        # Enrichir le simulation context avec les PK de cette table
        if sim_context and table_id:
            try:
                from app.core.simulation_context import extract_pk_values
                _tid_int = int(table_id)
                if _tid_int:
                    _pk_vals = extract_pk_values(df, _tid_int, parse_result)
                    sim_context.add(_tid_int, _pk_vals)
            except Exception:
                pass

        # Trigger Simulator — OnInsert si skip_triggers = False
        if execution_plan and not execution_plan.skip_triggers_for(
            int(table_id) if table_id else 0
        ):
            try:
                from app.core.trigger_simulator import TriggerSimulator
                if metadata_loader:
                    tsim         = TriggerSimulator(sim_context, metadata_loader)
                    trigger_anom = tsim.simulate_table(
                        table_id    = int(table_id),
                        sheet_name  = sheet_name,
                        df          = df,
                        bc_cache_fn = _cached_bc_cache_fn,
                    )
                    for ta in trigger_anom:
                        anomalies.append({
                            "Ligne":               ta.row_number,
                            "Onglet":              ta.sheet_name,
                            # AJOUTÉ (20/08/2026) : vide ici — TriggerAnomaly
                            # (trigger_simulator.py) ne porte pas encore la
                            # clé métier de la ligne. Laissé en suivi futur
                            # si ce détail s'avère nécessaire pour ce cas
                            # précis ; n'empêche pas l'affichage de la colonne.
                            "Identifiant métier":      "",
                            "Champ":               ta.field_name,
                            "Valeur":              ta.value,
                            "Type d'anomalie":     f"Trigger {ta.trigger_type}",
                            "Sévérité":            ta.severity,
                            "Message":             ta.message,
                            "Correction suggérée": "",
                            "Axe":                 "A-Trigger",
                        })
            except Exception:
                pass

        result["by_sheet"][sheet_name] = anomalies
        result["all_anomalies"].extend(anomalies)

    result["total_anomalies"] = len(result["all_anomalies"])
    result["major"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Majeure")
    result["minor"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Mineure")
    result["info"]  = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Info")

    return result