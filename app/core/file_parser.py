"""
Module de parsing des fichiers Excel et CSV.
Lit le fichier uploadé et retourne les données par onglet.
"""
import pandas as pd
import io
from typing import Union


def parse_uploaded_file(uploaded_file) -> dict:
    """
    Parse un fichier Excel (.xlsx) uploadé via Streamlit.

    Retourne un dictionnaire avec :
    - success (bool) : le parsing a réussi
    - sheets (dict)  : {nom_onglet: DataFrame}
    - sheet_names (list) : liste des noms d'onglets
    - file_name (str) : nom du fichier
    - total_rows (dict) : {nom_onglet: nb_lignes}
    - errors (list) : erreurs bloquantes
    - warnings (list) : avertissements non bloquants
    """
    result = {
        "success": False,
        "sheets": {},
        "sheet_names": [],
        "file_name": uploaded_file.name if uploaded_file else "",
        "total_rows": {},
        "errors": [],
        "warnings": []
    }

    if uploaded_file is None:
        result["errors"].append("Aucun fichier fourni.")
        return result

    # ── Vérification du format ────────────────────────────────────────────────
    file_name = uploaded_file.name.lower()
    if not file_name.endswith((".xlsx", ".xls")):
        result["errors"].append(
            f"Format non supporté : '{uploaded_file.name}'. "
            "Seuls les fichiers Excel (.xlsx, .xls) sont acceptés."
        )
        return result

    # ── Lecture du fichier ────────────────────────────────────────────────────
    try:
        # Lire tous les onglets en une seule fois
        # dtype=str pour garder toutes les valeurs en texte (évite les conversions automatiques)
        excel_data = pd.read_excel(
            uploaded_file,
            sheet_name=None,  # None = tous les onglets
            header=0,         # Première ligne = en-têtes
            dtype=str         # Tout en texte pour préserver les formats
        )

        result["sheets"] = excel_data
        result["sheet_names"] = list(excel_data.keys())
        result["success"] = True

        # ── Analyse de chaque onglet ──────────────────────────────────────────
        for sheet_name, df in excel_data.items():

            # Nombre de lignes de données (hors en-tête)
            result["total_rows"][sheet_name] = len(df)

            # Onglet vide
            if df.empty:
                result["warnings"].append(
                    f"⚠ Onglet '{sheet_name}' : aucune donnée (onglet vide)."
                )
                continue

            # Colonnes sans nom (cellules fusionnées ou en-tête manquant)
            unnamed_cols = [
                col for col in df.columns
                if str(col).startswith("Unnamed:")
            ]
            if unnamed_cols:
                result["warnings"].append(
                    f"⚠ Onglet '{sheet_name}' : {len(unnamed_cols)} colonne(s) "
                    "sans en-tête détectée(s). Vérifiez les cellules fusionnées."
                )

            # Détecter les cellules contenant des formules Excel
            formula_cells = []
            for col in df.columns:
                mask = df[col].astype(str).str.startswith("=", na=False)
                if mask.any():
                    rows_with_formula = df.index[mask].tolist()
                    formula_cells.append(
                        f"colonne '{col}' lignes {rows_with_formula[:3]}"
                    )

            if formula_cells:
                result["warnings"].append(
                    f"⚠ Onglet '{sheet_name}' : formules Excel détectées dans "
                    f"{', '.join(formula_cells[:3])}. "
                    "Les formules doivent être converties en valeurs statiques."
                )

    except Exception as e:
        result["errors"].append(
            f"Impossible de lire le fichier '{uploaded_file.name}' : {str(e)}"
        )

    return result


def get_sheet_preview(sheets: dict, sheet_name: str, max_rows: int = 10) -> pd.DataFrame:
    """
    Retourne un aperçu des premières lignes d'un onglet.
    """
    if sheet_name not in sheets:
        return pd.DataFrame()

    df = sheets[sheet_name]
    return df.head(max_rows)


def get_file_summary(parse_result: dict) -> dict:
    """
    Retourne un résumé statistique du fichier parsé.
    """
    if not parse_result["success"]:
        return {}

    total_rows = sum(parse_result["total_rows"].values())
    total_cols = sum(
        len(df.columns)
        for df in parse_result["sheets"].values()
    )

    return {
        "nb_onglets": len(parse_result["sheet_names"]),
        "total_lignes": total_rows,
        "total_colonnes": total_cols,
        "onglets": parse_result["sheet_names"],
        "lignes_par_onglet": parse_result["total_rows"]
    }
