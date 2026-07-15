"""
Validation Axe A — Contraintes BC standard.
100% dynamique via ExecutionPlan (fieldType + fieldLength depuis extension AL).
Fallback : contrôles universels si plan absent.
"""
import re
import pandas as pd
from datetime import datetime
from app.core.bc_order import sort_sheets_by_bc_order, get_bc_order_summary


DATE_FORMATS = [
    "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
    "%d.%m.%Y", "%m/%d/%Y", "%Y%m%d",
]
BOOL_TRUE  = {"oui", "yes", "true", "vrai", "1", "x", "✓"}
BOOL_FALSE = {"non", "no", "false", "faux", "0", ""}
_DEFAULT_TEXT_MAX = 250


def _is_empty(value) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() in ("nan", "none", "nat")

def _to_str(value) -> str:
    return "" if _is_empty(value) else str(value).strip()

def _validate_integer(v: str) -> bool:
    try:
        int(float(v.replace(" ", "").replace("\u202f", "")))
        return True
    except (ValueError, TypeError):
        return False

def _validate_decimal(v: str) -> bool:
    try:
        float(v.replace(" ", "").replace("\u202f", "").replace(",", "."))
        return True
    except (ValueError, TypeError):
        return False

def _validate_date(v: str) -> bool:
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(v.strip(), fmt)
            return True
        except ValueError:
            continue
    return False

def _validate_boolean(v: str) -> bool:
    return v.lower().strip() in BOOL_TRUE | BOOL_FALSE

def _validate_email(v: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", v))

def _infer_type(col: str) -> str | None:
    """Heuristique minimale — uniquement Date et Email."""
    c = col.lower()
    if "date" in c:                        return "Date"
    if "e-mail" in c or "email" in c:      return "Email"
    return None

def _sanitize_py_type(py_type: str | None, str_val: str) -> str | None:
    """
    Corrige les incohérences type AL vs valeur réelle.
    BC peut retourner Decimal pour des champs Option/Boolean.
    """
    if py_type != "Decimal":
        return py_type
    # Valeur booléenne → AL a mal typé ce champ
    if str_val.lower() in ("false", "true", "oui", "non", "yes", "no"):
        return None
    # Valeur contenant des lettres → pas un Decimal
    if any(c.isalpha() for c in str_val):
        return None
    return py_type


def validate_axe_a(
    df:            pd.DataFrame,
    table_id:      str,
    sheet_name:    str = "",
    execution_plan = None,
) -> list[dict]:
    anomalies  = []
    table_id_s = str(table_id)
    key_field  = execution_plan.get_key_field(int(table_id)) \
                 if execution_plan and table_id else "N°"

    has_plan   = (
        execution_plan is not None
        and execution_plan.source == "bc_api"
        and bool(execution_plan.get_field_defs_for_table(
            int(table_id) if table_id else 0
        ))
    )
    field_defs = (
        execution_plan.get_field_defs_for_table(int(table_id))
        if has_plan else {}
    )

    seen_keys: dict[str, int] = {}

    for row_idx, row in df.iterrows():
        line_num = int(row_idx) + 1

        for col in df.columns:
            raw_val  = row.get(col)
            str_val  = _to_str(raw_val)
            is_empty = _is_empty(raw_val)
            fm       = field_defs.get(str(col))

            # 1. Formule Excel
            if str_val.startswith("="):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Formule Excel", severity="Majeure",
                    message=f"'{col}' contient une formule Excel. Convertir en valeur statique.",
                ))
                continue

            # 2. Champ obligatoire vide
            if fm and fm.is_required and is_empty:
                anomalies.append(_anomaly(
                    line=line_num, field=col, value="", sheet=sheet_name,
                    error_type="Champ obligatoire vide", severity="Majeure",
                    message=f"'{col}' est obligatoire et ne peut pas être vide.",
                ))
                continue

            if is_empty:
                continue

            # 3. Longueur maximale
            if fm:
                # py_type == "Text" uniquement : un type AL non reconnu par
                # _AL_TYPE_MAP (ex: MediaSet pour Image) retombe sur py_type=None
                # via dict.get() — l'inclure ici (ancien check : py_type in
                # ("Text", None)) appliquait à tort fieldLength (parfois une
                # taille de stockage binaire, pas un nb de caractères) à des
                # champs qui n'ont rien à voir avec du texte (ex: Image → 38
                # car. > "max" 16 alors que BC ne signale rien sur ce champ).
                if fm.max_length and fm.py_type == "Text" and len(str_val) > fm.max_length:
                    anomalies.append(_anomaly(
                        line=line_num, field=col, value=str_val, sheet=sheet_name,
                        error_type="Longueur maximale dépassée", severity="Majeure",
                        message=f"'{col}' : {len(str_val)} car. (max BC = {fm.max_length}).",
                        suggested_fix=str_val[:fm.max_length],
                    ))
            else:
                if len(str_val) > _DEFAULT_TEXT_MAX:
                    anomalies.append(_anomaly(
                        line=line_num, field=col, value=str_val[:40] + "…", sheet=sheet_name,
                        error_type="Longueur maximale dépassée", severity="Mineure",
                        message=f"'{col}' : {len(str_val)} car. dépasse {_DEFAULT_TEXT_MAX} (seuil générique).",
                        suggested_fix=str_val[:_DEFAULT_TEXT_MAX],
                    ))

            # 4. Type de données
            raw_py_type = fm.py_type if fm else _infer_type(col)
            # Correction incohérences AL
            py_type     = _sanitize_py_type(raw_py_type, str_val)
            sev_type    = "Majeure" if fm else "Mineure"

            if py_type == "Integer" and not _validate_integer(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Type incorrect (entier attendu)", severity=sev_type,
                    message=f"'{col}' doit être un entier, valeur : '{str_val}'.",
                ))
            elif py_type == "Decimal" and not _validate_decimal(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Type incorrect (décimal attendu)", severity=sev_type,
                    message=f"'{col}' doit être un décimal, valeur : '{str_val}'. Séparateur : '.' ou ','.",
                ))
            elif py_type == "Date" and not _validate_date(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Format de date incorrect", severity=sev_type,
                    message=f"'{col}' : '{str_val}' n'est pas une date valide. Formats : JJ/MM/AAAA, AAAA-MM-JJ.",
                ))
            elif py_type == "Boolean" and not _validate_boolean(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Type incorrect (booléen attendu)", severity="Mineure",
                    message=f"'{col}' : '{str_val}' n'est pas un booléen. Valeurs : Oui/Non, True/False, 1/0.",
                ))
            elif py_type == "Email" and not _validate_email(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Format e-mail incorrect", severity="Mineure",
                    message=f"'{col}' : '{str_val}' n'est pas une adresse e-mail valide.",
                ))
            elif py_type == "Option" and fm and fm.option_values:
                if str_val not in fm.option_values:
                    allowed = ", ".join(f"'{v}'" for v in fm.option_values if v.strip())
                    anomalies.append(_anomaly(
                        line=line_num, field=col, value=str_val, sheet=sheet_name,
                        error_type="Valeur Option non autorisée", severity="Majeure",
                        message=f"'{col}' : '{str_val}' non autorisé. Valeurs BC : {allowed}.",
                    ))

        # 5. Doublons clé primaire
        if key_field in df.columns:
            key_val = _to_str(row.get(key_field))
            if key_val:
                if key_val in seen_keys:
                    anomalies.append(_anomaly(
                        line=line_num, field=key_field, value=key_val, sheet=sheet_name,
                        error_type="Doublon (clé primaire)", severity="Majeure",
                        message=f"'{key_field}' = '{key_val}' dupliqué. Déjà présent à la ligne {seen_keys[key_val]}.",
                    ))
                else:
                    seen_keys[key_val] = line_num

    return anomalies


def _anomaly(
    line: int, field: str, value: str, sheet: str,
    error_type: str, severity: str, message: str,
    suggested_fix: str = None,
) -> dict:
    return {
        "Ligne":               line,
        "Onglet":              sheet,
        "Champ":               field,
        "Valeur":              value,
        "Type d'anomalie":     error_type,
        "Sévérité":            severity,
        "Message":             message,
        "Correction suggérée": suggested_fix or "",
        "Axe":                 "A",
    }


def validate_file_axe_a(parse_result: dict, execution_plan=None) -> dict:
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
    metadata    = parse_result.get("metadata", {})
    sheets      = parse_result.get("sheets", {})

    tables_to_validate = sort_sheets_by_bc_order(data_tables + ref_tables, metadata)
    result["bc_order_summary"] = get_bc_order_summary(data_tables + ref_tables, metadata)

    for sheet_name in tables_to_validate:
        df = sheets.get(sheet_name)
        if df is None or df.empty:
            continue

        meta     = metadata.get(sheet_name, {})
        table_id = meta.get("table_id", "")
        result["lines_analyzed"] += len(df)

        anomalies = validate_axe_a(
            df=df,
            table_id=table_id,
            sheet_name=sheet_name,
            execution_plan=execution_plan,
        )

        result["by_sheet"][sheet_name] = anomalies
        result["all_anomalies"].extend(anomalies)

    result["total_anomalies"] = len(result["all_anomalies"])
    result["major"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Majeure")
    result["minor"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Mineure")
    result["info"]  = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Info")

    return result


def get_anomalies_dataframe(anomalies: list) -> pd.DataFrame:
    if not anomalies:
        return pd.DataFrame()
    cols = ["Ligne","Onglet","Champ","Valeur","Type d'anomalie","Sévérité","Message","Correction suggérée","Axe"]
    df   = pd.DataFrame(anomalies)
    return df[[c for c in cols if c in df.columns]]