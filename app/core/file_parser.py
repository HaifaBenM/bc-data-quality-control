"""
Module de parsing des fichiers Excel BC Configuration Package.

Structure des fichiers BC :
- Ligne 1 : Métadonnées [code_package, nom_table, n°_table]
- Ligne 2 : Vide
- Ligne 3 : En-têtes des colonnes
- Ligne 4+ : Données du client
"""
import pandas as pd
from app.core.master_data_config import categorize_table, get_table_label


def parse_uploaded_file(uploaded_file) -> dict:
    """Parse un fichier Excel BC Configuration Package."""
    result = {
        "success":     False,
        "sheets":      {},
        "sheet_names": [],
        "file_name":   uploaded_file.name if uploaded_file else "",
        "total_rows":  {},
        "metadata":    {},
        "data_tables": [],
        "ref_tables":  [],
        "sys_tables":  [],
        "errors":      [],
        "warnings":    [],
    }

    if not uploaded_file:
        result["errors"].append("Aucun fichier fourni.")
        return result

    if not uploaded_file.name.lower().endswith((".xlsx", ".xls")):
        result["errors"].append(
            f"Format non supporté : '{uploaded_file.name}'. "
            "Seuls les fichiers Excel (.xlsx, .xls) sont acceptés."
        )
        return result

    try:
        # Lecture brute pour les métadonnées (ligne 1)
        raw_data = pd.read_excel(
            uploaded_file, sheet_name=None, header=None, dtype=str
        )
        uploaded_file.seek(0)

        # Lecture avec en-têtes à la ligne 3 (index 2)
        excel_data = pd.read_excel(
            uploaded_file, sheet_name=None, header=2, dtype=str
        )

        result["sheet_names"] = list(excel_data.keys())
        result["success"] = True

        for sheet_name in excel_data.keys():
            df = excel_data[sheet_name].copy()
            raw_df = raw_data[sheet_name]

            # Extraire les métadonnées BC (ligne 1)
            try:
                meta_row = raw_df.iloc[0]
                package_code = str(meta_row.iloc[0]) if pd.notna(meta_row.iloc[0]) else ""
                table_name   = str(meta_row.iloc[1]) if pd.notna(meta_row.iloc[1]) else ""
                table_id     = str(meta_row.iloc[2]) if pd.notna(meta_row.iloc[2]) else ""
                if table_id.endswith(".0"):
                    table_id = table_id[:-2]
            except Exception:
                package_code = table_name = table_id = ""

            # Skiper les onglets sans table_id numérique valide
            # (ex: onglet GUIDE généré par l'outil, onglets de documentation)
            try:
                int(table_id)
            except (ValueError, TypeError):
                result["sys_tables"].append(sheet_name)
                continue

            category = categorize_table(table_id)
            label    = get_table_label(table_id, table_name)

            result["metadata"][sheet_name] = {
                "package_code": package_code,
                "table_name":   table_name,
                "table_id":     table_id,
                "label":        label,
                "category":     category,
            }

            if category == "data":
                result["data_tables"].append(sheet_name)
            elif category == "system":
                result["sys_tables"].append(sheet_name)
            else:
                result["ref_tables"].append(sheet_name)

            # Nettoyage
            df = df.dropna(axis=1, how="all")
            df = df.dropna(axis=0, how="all")
            result["sheets"][sheet_name]    = df
            result["total_rows"][sheet_name] = len(df)

            # Avertissements
            if category == "data" and df.empty:
                result["warnings"].append(
                    f"⚠ Onglet '{sheet_name}' ({label}) : aucune donnée saisie."
                )

            if category == "data" and not df.empty:
                formula_cols = [
                    str(col) for col in df.columns
                    if df[col].astype(str).str.startswith("=", na=False).any()
                ]
                if formula_cols:
                    result["warnings"].append(
                        f"⚠ Onglet '{sheet_name}' : formules Excel dans "
                        f"{len(formula_cols)} colonne(s). "
                        "Convertir en valeurs statiques."
                    )

    except Exception as e:
        result["errors"].append(f"Impossible de lire '{uploaded_file.name}' : {str(e)}")

    return result


def get_file_summary(parse_result: dict) -> dict:
    """Retourne un résumé statistique du fichier parsé."""
    if not parse_result["success"]:
        return {}

    data_tables = parse_result.get("data_tables", [])
    metadata    = parse_result.get("metadata", {})
    total_rows  = parse_result.get("total_rows", {})

    data_info = [
        {
            "sheet":    s,
            "label":    metadata.get(s, {}).get("label", s),
            "table_id": metadata.get(s, {}).get("table_id", "?"),
            "rows":     total_rows.get(s, 0),
        }
        for s in data_tables
    ]

    return {
        "nb_data_tables":  len(data_tables),
        "nb_ref_tables":   len(parse_result.get("ref_tables", [])),
        "nb_total":        len(parse_result["sheet_names"]),
        "data_tables":     data_info,
        # Compte les lignes sur data_tables ET ref_tables — la classification
        # DATA_TABLES est une liste figée non exhaustive (cf. tables 13, 288),
        # ne pas y limiter le total affiché à l'utilisateur.
        "total_data_rows": sum(
            total_rows.get(s, 0)
            for s in data_tables + parse_result.get("ref_tables", [])
        ),
    }