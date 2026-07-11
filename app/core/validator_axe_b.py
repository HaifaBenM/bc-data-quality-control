"""
Validation Axe B — Vérification des codes de référence BC.
Vérifie que les codes saisis existent dans les tables de référence.

Sources (par ordre de priorité) :
  1. Onglets de référence du fichier uploadé (ex: "Conditions de paiement")
  2. Cache Supabase (chargé depuis BC en Sprint 3)
  3. Si aucune source → champ non vérifiable (Info, pas d'erreur bloquante)
"""
import pandas as pd
from app.db.metadata_db import get_reference_values, get_reference_values_by_table_id
from app.core.bc_order import sort_sheets_by_bc_order, get_bc_order_summary


# ══════════════════════════════════════════════════════════════════════════════
# MAPPING : champ de données → table de référence
# Clé = table_id BC, Valeur = {champ_données: config_référence}
# ══════════════════════════════════════════════════════════════════════════════

REFERENCE_MAP = {

    # ── Table 18 — Clients ─────────────────────────────────────────────────────
    "18": {
        "Code conditions paiement": {
            "patterns":  ["Conditions de paiement", "Condition paiement"],
            "key":       "Code",
            "label":     "Conditions de paiement",
            "cache_key": "paymentTerms",
        },
        "Code devise": {
            "patterns":  ["Devise", "4 Devise"],
            "key":       "Code",
            "label":     "Devises",
            "cache_key": "currencies",
        },
        "Code pays/région": {
            "patterns":  ["Pays", "9 Pays", "Paysrégion"],
            "key":       "Code",
            "label":     "Pays/Régions",
            "cache_key": "countriesRegions",
        },
        "Code vendeur": {
            "patterns":  ["Vendeur", "VendeurAcheteur", "13 Vendeur"],
            "key":       "Code",
            "label":     "Vendeurs/Acheteurs",
            "cache_key": "salespeople",
        },
        "Code magasin": {
            "patterns":  ["Magasin", "14 Magasin"],
            "key":       "Code",
            "label":     "Magasins",
            "cache_key": "locations",
        },
        "Groupe compta. client": {
            "patterns":  ["Groupe compta. client", "92 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. client",
            "cache_key": None,
        },
        "Groupe compta. marché": {
            "patterns":  ["Groupe compta. marché", "250 Groupe compta. marché"],
            "key":       "Code",
            "label":     "Groupes compta. marché",
            "cache_key": None,
        },
        "Groupe compta. marché TVA": {
            "patterns":  ["marché TVA", "323 Groupe", "TVA marché"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        "Code mode de paiement": {
            "patterns":  ["Mode de règlement", "289 Mode", "Mode paiement"],
            "key":       "Code",
            "label":     "Modes de règlement",
            "cache_key": "paymentMethods",
        },
        "Code condition relance": {
            "patterns":  ["Relance", "292 Condition"],
            "key":       "Code",
            "label":     "Conditions de relance",
            "cache_key": None,
        },
        "Code transporteur": {
            "patterns":  ["Transporteur", "291 Transporteur"],
            "key":       "Code",
            "label":     "Transporteurs",
            "cache_key": None,
        },
        "Groupe prix client": {
            "patterns":  ["Prix client", "6 Groupe prix"],
            "key":       "Code",
            "label":     "Groupes prix client",
            "cache_key": None,
        },
        "Groupe remises client": {
            "patterns":  ["Remise client", "7 Groupe remise"],
            "key":       "Code",
            "label":     "Groupes remises client",
            "cache_key": None,
        },
        "Code langue": {
            "patterns":  ["Langue", "8 Langue"],
            "key":       "Code",
            "label":     "Langues",
            "cache_key": None,
        },
    },

    # ── Table 23 — Fournisseurs ────────────────────────────────────────────────
    "23": {
        "Code conditions paiement": {
            "patterns":  ["Conditions de paiement"],
            "key":       "Code",
            "label":     "Conditions de paiement",
            "cache_key": "paymentTerms",
        },
        "Code devise": {
            "patterns":  ["Devise"],
            "key":       "Code",
            "label":     "Devises",
            "cache_key": "currencies",
        },
        "Code pays/région": {
            "patterns":  ["Pays", "Paysrégion"],
            "key":       "Code",
            "label":     "Pays/Régions",
            "cache_key": "countriesRegions",
        },
        "Groupe compta. fournisseur": {
            "patterns":  ["Groupe compta. fournisseur", "93 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. fournisseur",
            "cache_key": None,
        },
        "Groupe compta. marché": {
            "patterns":  ["Groupe compta. marché", "250 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché",
            "cache_key": None,
        },
        "Groupe compta. marché TVA": {
            "patterns":  ["marché TVA", "323 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        "Code mode de paiement": {
            "patterns":  ["Mode de règlement"],
            "key":       "Code",
            "label":     "Modes de règlement",
            "cache_key": "paymentMethods",
        },
        "Code acheteur": {
            "patterns":  ["Vendeur", "VendeurAcheteur"],
            "key":       "Code",
            "label":     "Acheteurs",
            "cache_key": "salespeople",
        },
    },

    # ── Table 27 — Articles ────────────────────────────────────────────────────
    "27": {
        # ── Unité de mesure ────────────────────────────────────────────────────
        "Unité de base": {
            "patterns":  ["Unité de mesure", "204 Unité", "Unités de mesure"],
            "key":       "Code",
            "label":     "Unités de mesure",
            "cache_key": "unitOfMeasures",
        },
        # ── Groupes comptables ─────────────────────────────────────────────────
        "Groupe compta. stock": {
            "patterns":  ["Groupe compta. stock", "94 Groupe compta. stock"],
            "key":       "Code",
            "label":     "Groupes compta. stock",
            "cache_key": None,
        },
        "Groupe compta. produit": {
            "patterns":  ["Groupe compta. produit", "252 Groupe compta. produit"],
            "key":       "Code",
            "label":     "Groupes compta. produit",
            "cache_key": None,
        },
        "Groupe compta. produit TVA": {
            "patterns":  ["produit TVA", "325 Groupe compta. produit TVA"],
            "key":       "Code",
            "label":     "Groupes compta. produit TVA",
            "cache_key": None,
        },
        "Gpe compta. marché TVA (prix)": {
            "patterns":  ["marché TVA", "74 Gpe compta", "TVA prix"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        # ── Références fournisseur ─────────────────────────────────────────────
        "N° fournisseur": {
            "patterns":  ["23 Fournisseur", "Fournisseur"],
            "key":       "N°",
            "label":     "Fournisseurs",
            "cache_key": "vendors",
        },
        # ── Catégorie et remises ───────────────────────────────────────────────
        "Code catégorie article": {
            "patterns":  ["Catégorie article", "5722 Catégorie"],
            "key":       "Code",
            "label":     "Catégories d'articles",
            "cache_key": "itemCategories",
        },
        "Groupe rem. article": {
            "patterns":  ["Groupe remises article", "340 Groupe remises"],
            "key":       "Code",
            "label":     "Groupes remises article",
            "cache_key": None,
        },
        # ── Pays/région ────────────────────────────────────────────────────────
        "Code pays/région achat": {
            "patterns":  ["Pays", "9 Pays", "Pays/région"],
            "key":       "Code",
            "label":     "Pays/Régions",
            "cache_key": "countriesRegions",
        },
        "Code pays/région origine": {
            "patterns":  ["Pays", "9 Pays", "Pays/région"],
            "key":       "Code",
            "label":     "Pays/Régions",
            "cache_key": "countriesRegions",
        },
        # ── No. Series ─────────────────────────────────────────────────────────
        "Souches de n°": {
            "patterns":  ["Souches de n", "308 Souches"],
            "key":       "Code",
            "label":     "Souches de n°",
            "cache_key": "noSeries",
        },
        # ── Taxes ──────────────────────────────────────────────────────────────
        "Code groupe taxes": {
            "patterns":  ["Groupe taxes", "322 Groupe taxes", "USA groupe taxes"],
            "key":       "Code",
            "label":     "USA Groupes taxes",
            "cache_key": None,
        },
        # ── Modèle échelonnement ───────────────────────────────────────────────
        "Code modèle échelonnement par défaut": {
            "patterns":  ["Modèle éch", "1300 Modèle", "Deferral"],
            "key":       "Code",
            "label":     "Modèles d'échelonnement",
            "cache_key": None,
        },
        # ── Traçabilité ────────────────────────────────────────────────────────
        "Code traçabilité": {
            "patterns":  ["Traçabilité", "6502 Traça"],
            "key":       "Code",
            "label":     "Codes traçabilité",
            "cache_key": None,
        },
        # ── Mode d'achat ───────────────────────────────────────────────────────
        "Code achat": {
            "patterns":  ["5730 Code achat", "Code achat"],
            "key":       "Code",
            "label":     "Codes achat",
            "cache_key": None,
        },
    },

    # ── Table 15 — Plan comptable ──────────────────────────────────────────────
    "15": {
        "Groupe compta. marché": {
            "patterns":  ["Groupe compta. marché", "250 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché",
            "cache_key": None,
        },
        "Groupe compta. produit": {
            "patterns":  ["Groupe compta. produit", "252 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. produit",
            "cache_key": None,
        },
        "Groupe compta. marché TVA": {
            "patterns":  ["marché TVA", "323 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        "Groupe compta. produit TVA": {
            "patterns":  ["produit TVA", "325 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. produit TVA",
            "cache_key": None,
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _normalize(value: str) -> str:
    """Normalise une valeur pour comparaison : strip + espaces insécables."""
    return (
        str(value)
        .strip()
        .replace("\xa0", " ")   # espace insécable → espace normal
        .replace("\u202f", " ") # espace fine insécable
        .strip()
    )


def _find_ref_sheet(all_sheets: dict, patterns: list) -> str | None:
    """
    Trouve le nom de l'onglet de référence dans le fichier.
    Cherche par correspondance partielle (case-insensitive).
    """
    for sheet_name in all_sheets.keys():
        sheet_norm = sheet_name.lower().replace(" ", "").replace("-", "")
        for pattern in patterns:
            pat_norm = pattern.lower().replace(" ", "").replace("-", "")
            if pat_norm in sheet_norm or sheet_norm in pat_norm:
                return sheet_name
    return None


def _get_valid_codes(df: pd.DataFrame, key_field: str = "Code") -> set:
    """
    Extrait les codes valides depuis un DataFrame de référence.
    Gère les espaces insécables et la casse.
    """
    # Trouver la colonne clé (peut avoir des espaces ou des variantes)
    actual_key = None
    for col in df.columns:
        if _normalize(str(col)).lower() == key_field.lower():
            actual_key = col
            break

    if actual_key is None and len(df.columns) > 0:
        actual_key = df.columns[0]  # Fallback : première colonne

    if actual_key is None:
        return set()

    codes = set()
    for val in df[actual_key].dropna():
        normalized = _normalize(str(val))
        if normalized and normalized.lower() != "nan":
            codes.add(normalized)
            codes.add(normalized.upper())
            codes.add(normalized.lower())

    return codes


# ══════════════════════════════════════════════════════════════════════════════
# MOTEUR DE VALIDATION AXE B
# ══════════════════════════════════════════════════════════════════════════════

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

    Logique :
      Pour chaque champ où validate_field = TRUE :
        ref_table_id = execution_plan.get_ref_table_id(table_id, field_name)
        valid_codes  = BC_cache(ref_table_id) ∪ simulation_context(ref_table_id)
        Si valeur absente → ANOMALIE MAJEURE

    Fallback REFERENCE_MAP (si execution_plan absent ou refTableId=0) :
      Utilise l'ancien mécanisme par patterns pour les tables connues.
    """
    anomalies = []
    if df is None or df.empty:
        return anomalies

    try:
        table_id_int = int(table_id) if table_id else 0
    except (ValueError, TypeError):
        table_id_int = 0

    # ── Chemin 1 : lookup dynamique via execution_plan (refTableId AL) ─────────
    if execution_plan and table_id_int:
        for col in df.columns:
            # Vérifier validate_field flag
            if not execution_plan.validate_field_for(table_id_int, col):
                continue

            ref_tid = execution_plan.get_ref_table_id(table_id_int, col)
            if not ref_tid:
                continue  # pas de TableRelation → pas de vérification Axe B

            # Codes valides : BC cache + simulation context
            bc_codes, found = get_reference_values_by_table_id(
                profile_code, company_id, ref_tid
            )
            sim_codes = sim_context.get_values(ref_tid) if sim_context else set()
            valid_codes = bc_codes | sim_codes

            if not found and not sim_codes:
                # Table inconnue → INFO
                anomalies.append({
                    "Ligne":              0,
                    "Onglet":             sheet_name,
                    "Champ":              col,
                    "Valeur":             "",
                    "Type d'anomalie":   "Code de référence non vérifiable",
                    "Sévérité":           "Info",
                    "Message":            (
                        f"Impossible de vérifier '{col}' : "
                        f"la table de référence (ID {ref_tid}) n'est pas "
                        f"dans le cache BC. Chargez la metadata BC depuis le profil client."
                    ),
                    "Correction suggérée": "",
                    "Axe":               "B",
                    "Détail":            f"ref_table_id={ref_tid}",
                })
                continue

            # Valider chaque ligne
            for row_idx, row in df.iterrows():
                value = str(row.get(col, "") or "").strip()
                if not value or value.lower() in ("nan", "none", ""):
                    continue

                if value not in valid_codes:
                    examples = sorted(valid_codes)[:3] if valid_codes else []
                    tag_bc   = valid_codes and found
                    anomalies.append({
                        "Ligne":              int(row_idx) + 4,
                        "Onglet":             sheet_name,
                        "Champ":              col,
                        "Valeur":             value,
                        "Type d'anomalie":   "Code de référence invalide",
                        "Sévérité":           "Majeure",
                        "Message":            (
                            f"'{col}' = '{value}' n'existe pas dans "
                            f"la table référencée (ID {ref_tid})."
                            + (f" Exemples valides : {examples}" if examples else "")
                        ),
                        "Correction suggérée": examples[0] if examples else "",
                        "Axe":               "B",
                        "BC":                tag_bc,
                    })

        # Appliquer simulation_context enrichment (même logique qu'avant)
        if sim_context and metadata_loader:
            try:
                for col in df.columns:
                    _ref_tid2 = execution_plan.get_ref_table_id(table_id_int, col)
                    if not _ref_tid2:
                        continue
                    _sim = sim_context.get_values(_ref_tid2)
                    if _sim:
                        # Les anomalies déjà générées pour ce champ peuvent être
                        # faux positifs si la valeur est dans sim_context
                        anomalies = [
                            a for a in anomalies
                            if not (
                                a.get("Champ") == col
                                and str(a.get("Valeur","")).strip() in _sim
                            )
                        ]
            except Exception:
                pass

        return anomalies

    # ── Chemin 2 : fallback REFERENCE_MAP (execution_plan absent) ─────────────
    field_refs = dict(REFERENCE_MAP.get(table_id, {}))
    if not field_refs:
        return anomalies

    # Construction ref_codes_cache (logique originale préservée)
    ref_codes_cache: dict[str, tuple[set, str, bool]] = {}
    not_found_fields: set[str] = set()

    for field_name, ref_config in field_refs.items():
        if field_name not in df.columns:
            continue

        sim_codes = set()
        if sim_context and metadata_loader:
            try:
                _ref_tid_fb = metadata_loader.get_ref_table_id(table_id_int, field_name)
                if _ref_tid_fb:
                    sim_codes = sim_context.get_values(_ref_tid_fb)
            except Exception:
                pass

        # 1. Chercher dans le fichier
        ref_sheet = _find_ref_sheet(all_sheets, ref_config["patterns"])
        if ref_sheet:
            ref_df   = all_sheets.get(ref_sheet)
            f_codes  = _get_valid_codes(ref_df, ref_config["key"]) if ref_df is not None else set()
            codes    = f_codes | sim_codes
            ref_codes_cache[field_name] = (codes, f"onglet '{ref_sheet}'", True)
            continue

        # 2. Cache Supabase
        if profile_code and ref_config.get("cache_key"):
            cached = get_reference_values(profile_code, ref_config["cache_key"])
            if cached or sim_codes:
                codes = set(c for c in cached if c) | sim_codes
                ref_codes_cache[field_name] = (codes, f"cache BC ({ref_config['label']})", True)
                continue

        # 3. Sim context seul
        if sim_codes:
            ref_codes_cache[field_name] = (sim_codes, "fichier (intra-package)", True)
        else:
            not_found_fields.add(field_name)
            ref_codes_cache[field_name] = (set(), ref_config["label"], False)

    # Anomalies INFO pour champs non vérifiables
    for field_name in not_found_fields:
        _, label, _ = ref_codes_cache.get(field_name, (set(), field_name, False))
        anomalies.append({
            "Ligne":              0,
            "Onglet":             sheet_name,
            "Champ":              field_name,
            "Valeur":             "",
            "Type d'anomalie":   "Code de référence non vérifiable",
            "Sévérité":           "Info",
            "Message":            (
                f"Impossible de vérifier '{field_name}' : "
                f"la table de référence '{label}' n'est pas dans le fichier "
                f"et n'est pas dans le cache BC. Chargez la metadata BC."
            ),
            "Correction suggérée": "",
            "Axe":               "B",
        })

    # Validation ligne par ligne
    for row_idx, row in df.iterrows():
        row_num = int(row_idx) + 4
        for field_name, (valid_codes, source, found) in ref_codes_cache.items():
            if field_name not in df.columns or not found:
                continue
            value = str(row.get(field_name, "") or "").strip()
            if not value or value.lower() in ("nan", "none", ""):
                continue
            if value not in valid_codes:
                examples = sorted(valid_codes)[:3] if valid_codes else []
                anomalies.append({
                    "Ligne":              row_num,
                    "Onglet":             sheet_name,
                    "Champ":              field_name,
                    "Valeur":             value,
                    "Type d'anomalie":   "Code de référence invalide",
                    "Sévérité":           "Majeure",
                    "Message":            (
                        f"'{field_name}' = '{value}' n'existe pas "
                        f"dans {source}."
                        + (f" Exemples valides : {examples}" if examples else "")
                    ),
                    "Correction suggérée": examples[0] if examples else "",
                    "Axe":               "B",
                    "BC":                found,
                })

    return anomalies

def validate_file_axe_b(
    parse_result:    dict,
    profile_code:    str  = "",
    company_id:      str  = "",
    sim_context      = None,   # SimulationContext partagé entre les tables
    metadata_loader  = None,   # MetadataLoader
    execution_plan   = None,   # ExecutionPlan (flags BC)
) -> dict:
    """
    Lance la validation Axe B sur TOUTES les tables analysables du fichier
    (data_tables + ref_tables).

    Avant : seules les tables classées "data" étaient à la fois (a) contrôlées
    elles-mêmes ET (b) candidates comme cible de la boucle externe — bien que
    `all_sheets` (passé à validate_axe_b) ait toujours contenu TOUTES les
    feuilles du fichier pour la résolution des lookups. Le problème n'était
    donc pas la résolution des références, mais le fait qu'une feuille comme
    "Conditions de paiement" n'était jamais elle-même la cible d'un contrôle
    Axe B (utile dès qu'une table de référence référence elle-même un autre
    code, ex: futures tables avec FK imbriquées).

    Maintenant : toute table non-système (data + ref) est contrôlée comme
    cible, tout en restant disponible comme source de lookup pour les autres
    — exactement le comportement de BC standard observé via
    ValidateFieldRelationAgainstCompanyDataAndPackage (vérifie une donnée à
    la fois contre la société ET contre le reste du package).

    Retourne :
    {
        total_anomalies, major, minor, info,
        lines_analyzed,
        by_sheet: {sheet_name: [anomalies]},
        all_anomalies: [toutes les anomalies]
    }
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
    ref_tables  = parse_result.get("ref_tables", [])
    all_sheets  = parse_result.get("sheets", {})
    metadata    = parse_result.get("metadata", {})

    # Tri dans l'ordre d'intégration BC : Processing Order ASC, Table ID ASC.
    # Cohérent avec validate_file_axe_a — les deux axes traitent les tables
    # dans le même ordre, ce qui reproduit le flux BC :
    # ApplyPackageTables → pour chaque table → ValidateFieldRelation.
    tables_to_validate = sort_sheets_by_bc_order(
        data_tables + ref_tables, metadata
    )

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

        # Mettre à jour le simulation context avec les PK de cette table
        if sim_context and table_id:
            try:
                from app.core.simulation_context import extract_pk_values
                _tid_int = int(table_id)
                if _tid_int:
                    _pk_vals = extract_pk_values(df, _tid_int, parse_result)
                    sim_context.add(_tid_int, _pk_vals)
            except Exception:
                pass

        # Trigger Simulator — OnInsert (si skip_triggers = False)
        if execution_plan and not execution_plan.skip_triggers_for(
            int(table_id) if table_id else 0
        ):
            try:
                from app.core.trigger_simulator import TriggerSimulator
                from app.db.metadata_db import get_reference_values, get_reference_values_by_table_id
                if metadata_loader:
                    tsim = TriggerSimulator(sim_context, metadata_loader)
                    trigger_anom = tsim.simulate_table(
                        table_id   = int(table_id),
                        sheet_name = sheet_name,
                        df         = df,
                        bc_cache_fn= lambda tid: set(
                            get_reference_values(profile_code, str(tid)) or []
                        ),
                    )
                    for ta in trigger_anom:
                        anomalies.append({
                            "Ligne":              ta.row_number,
                            "Onglet":             ta.sheet_name,
                            "Champ":              ta.field_name,
                            "Valeur":             ta.value,
                            "Type d'anomalie":   f"Trigger {ta.trigger_type}",
                            "Sévérité":           ta.severity,
                            "Message":            ta.message,
                            "Correction suggérée": "",
                            "Axe":                "A-Trigger",
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
