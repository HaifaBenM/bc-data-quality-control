"""
Validation Axe B — Vérification des codes de référence BC.
Vérifie que les codes saisis existent dans les tables de référence.

Sources (par ordre de priorité) :
  1. Onglets de référence du fichier uploadé (ex: "Conditions de paiement")
  2. Cache Supabase (chargé depuis BC en Sprint 3)
  3. Si aucune source → champ non vérifiable (Info, pas d'erreur bloquante)
"""
import pandas as pd
from app.db.metadata_db import get_reference_values_by_table_id
from app.core.bc_order import sort_sheets_by_bc_order, get_bc_order_summary


# ══════════════════════════════════════════════════════════════════════════════
# MAPPING : champ de données → table de référence
# Clé = table_id BC, Valeur = {champ_données: config_référence}
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

    Si execution_plan absent : INFO 'non vérifiable' (comportement honnête).
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

    # Pas d'execution_plan → impossible de déterminer les TableRelations
    # Comportement honnête : INFO pour tous les champs de la table
    anomalies.append({
        "Ligne":              0,
        "Onglet":             sheet_name,
        "Champ":              "",
        "Valeur":             "",
        "Type d'anomalie":   "Validation références non disponible",
        "Sévérité":           "Info",
        "Message":            (
            f"Table {table_id} : impossible de valider les références (Axe B) "
            f"sans le plan d'exécution BC. "
            f"Assurez-vous que le package est sélectionné et l'extension AL déployée."
        ),
        "Correction suggérée": "",
        "Axe":               "B",
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
                from app.db.metadata_db import get_reference_values_by_table_id
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
