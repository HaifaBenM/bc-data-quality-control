"""
Validation Axe B — Vérification des codes de référence BC.
100% dynamique via ExecutionPlan (refTableId + refFieldId depuis extension AL).
Lazy load automatique depuis BC API si cache absent.
"""
import pandas as pd
from app.db.metadata_db import get_reference_values_by_table_id
from app.core.bc_order import sort_sheets_by_bc_order, get_bc_order_summary


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
    """
    anomalies = []
    if df is None or df.empty:
        return anomalies

    try:
        table_id_int = int(table_id) if table_id else 0
    except (ValueError, TypeError):
        table_id_int = 0

    if execution_plan and table_id_int:
        for col in df.columns:
            if not execution_plan.validate_field_for(table_id_int, col):
                continue

            ref_tid = execution_plan.get_ref_table_id(table_id_int, col)
            if not ref_tid:
                continue

            # refFieldId — PK de la table relation (nouveau)
            ref_fid = execution_plan.get_ref_field_id(table_id_int, col)

            # Codes valides : lazy load BC + simulation context intra-fichier
            bc_codes, found = get_reference_values_by_table_id(
                profile_code, company_id, ref_tid, ref_fid
            )
            sim_codes   = sim_context.get_values(ref_tid) if sim_context else set()
            valid_codes = bc_codes | sim_codes

            if not found and not sim_codes:
                anomalies.append({
                    "Ligne":               0,
                    "Onglet":              sheet_name,
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

            # Valider chaque ligne
            for row_idx, row in df.iterrows():
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
                            "Champ":               col,
                            "Valeur":              "",
                            "Type d'anomalie":     "Souches de n° non résolvable",
                            "Sévérité":            "Majeure",
                            "Message":             (
                                "Souches de n° n'existe pas. Champs et valeurs "
                                "d'identification : Code=''"
                            ),
                            "Correction suggérée": "",
                            "Axe":                 "B",
                            "BC":                  True,
                        })

                if is_val_empty or is_zero_guid:
                    continue

                if value not in valid_codes:
                    examples = sorted(valid_codes)[:3] if valid_codes else []
                    anomalies.append({
                        "Ligne":               int(row_idx) + 4,
                        "Onglet":              sheet_name,
                        "Champ":               col,
                        "Valeur":              value,
                        "Type d'anomalie":     "Code de référence invalide",
                        "Sévérité":            "Majeure",
                        "Message":             (
                            f"'{col}' = '{value}' n'existe pas dans "
                            f"la table référencée (ID {ref_tid})."
                            + (f" Exemples valides : {examples}" if examples else "")
                        ),
                        "Correction suggérée": examples[0] if examples else "",
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
                        bc_cache_fn = lambda tid: get_reference_values_by_table_id(
                            profile_code, company_id, tid
                        )[0],
                    )
                    for ta in trigger_anom:
                        anomalies.append({
                            "Ligne":               ta.row_number,
                            "Onglet":              ta.sheet_name,
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