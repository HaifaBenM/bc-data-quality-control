"""
Validation Axe D — Moteur de règles métier client.
Applique les règles spécifiques saisies dans le profil client
(8 types : valeur par défaut, transformation, table de correspondance,
condition métier, format obligatoire, plage de valeurs, exclusion, doublon).
"""
import re
import json
import pandas as pd


# ── Parseurs utilitaires ──────────────────────────────────────────────────────

def _to_str(value) -> str:
    if value is None: return ""
    s = str(value).strip()
    return "" if s.lower() in ("nan","none","nat","") else s


def _is_empty(value) -> bool:
    return not bool(_to_str(value))


def _extract_quoted(text: str) -> str:
    """Extrait la valeur entre guillemets simples ou doubles."""
    m = re.search(r"['\"](.+?)['\"]", text)
    return m.group(1).strip() if m else text.strip()


def _extract_range(text: str) -> tuple[float, float] | None:
    """Extrait min et max depuis 'X à Y' ou 'X-Y' ou 'X et Y'."""
    patterns = [
        r"([\d.]+)\s*[àa-]\s*([\d.]+)",
        r"([\d.]+)\s*et\s*([\d.]+)",
        r"min\s*[=:]\s*([\d.]+).*max\s*[=:]\s*([\d.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1)), float(m.group(2))
            except ValueError:
                pass
    return None


def _parse_mapping_table(text: str) -> dict:
    """
    Parse une table de correspondance depuis le texte de l'action.
    Formats acceptés :
      'ancien' → 'nouveau'
      ancien=nouveau
      JSON {"ancien": "nouveau"}
    """
    mapping = {}
    # Essayer JSON d'abord
    try:
        j = json.loads(text)
        if isinstance(j, dict):
            return {str(k).strip(): str(v).strip() for k, v in j.items()}
    except Exception:
        pass

    # Format "clé → valeur" ou "clé = valeur"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sep in ["→", "->", "=", ":"]:
            if sep in line:
                parts = line.split(sep, 1)
                key = _extract_quoted(parts[0])
                val = _extract_quoted(parts[1])
                if key:
                    mapping[key] = val
                break

    return mapping


def _anomaly_d(
    line: int, field: str, value: str, sheet: str,
    error_type: str, severity: str, message: str,
    rule_label: str = "", suggested_fix: str = "",
    auto_correct: bool = False,
) -> dict:
    return {
        "Ligne":             line,
        "Onglet":            sheet,
        "Champ":             field,
        "Valeur":            value,
        "Type d'anomalie":   error_type,
        "Sévérité":          severity,
        "Message":           message,
        "Correction suggérée": (
            f"⚡ {suggested_fix}" if (suggested_fix and auto_correct)
            else suggested_fix
        ),
        "Règle":             rule_label,
        "Axe":               "D",
    }


# ══════════════════════════════════════════════════════════════════════════════
# MOTEUR DE RÈGLES
# ══════════════════════════════════════════════════════════════════════════════

def apply_rule(rule: dict, df: pd.DataFrame, sheet_name: str) -> list:
    """
    Applique une règle métier à un DataFrame.
    Retourne une liste d'anomalies/suggestions.
    """
    rule_type   = rule.get("rule_type", "")
    field       = rule.get("field_name", "")
    condition   = rule.get("condition", "").strip()
    action      = rule.get("action", "").strip()
    severity    = rule.get("severity", "Mineure")
    auto        = rule.get("auto_correct", False)
    label       = rule.get("label", rule_type)

    anomalies = []

    # ── 1. Valeur par défaut ──────────────────────────────────────────────────
    if rule_type == "Valeur par défaut":
        if not field or field not in df.columns:
            return anomalies
        default_val = _extract_quoted(action) if action else action
        for idx, row in df.iterrows():
            if _is_empty(row.get(field)):
                anomalies.append(_anomaly_d(
                    line=int(idx)+1, field=field, value="", sheet=sheet_name,
                    error_type="Valeur par défaut manquante",
                    severity=severity,
                    message=f"Règle «{label}» : '{field}' est vide → valeur par défaut = '{default_val}'.",
                    rule_label=label,
                    suggested_fix=default_val,
                    auto_correct=auto,
                ))

    # ── 2. Transformation ─────────────────────────────────────────────────────
    elif rule_type == "Transformation":
        if not field or field not in df.columns:
            return anomalies
        old_val = _extract_quoted(condition) if condition else ""
        new_val = _extract_quoted(action) if action else action
        if not old_val:
            return anomalies
        for idx, row in df.iterrows():
            current = _to_str(row.get(field))
            if current.lower() == old_val.lower():
                anomalies.append(_anomaly_d(
                    line=int(idx)+1, field=field, value=current, sheet=sheet_name,
                    error_type="Transformation requise",
                    severity=severity,
                    message=f"Règle «{label}» : '{field}' = '{current}' → remplacer par '{new_val}'.",
                    rule_label=label,
                    suggested_fix=new_val,
                    auto_correct=auto,
                ))

    # ── 3. Table de correspondance ────────────────────────────────────────────
    elif rule_type == "Table de correspondance":
        if not field or field not in df.columns:
            return anomalies
        mapping = _parse_mapping_table(action)
        if not mapping:
            return anomalies
        for idx, row in df.iterrows():
            current  = _to_str(row.get(field))
            curr_up  = current.upper()
            matched  = next(
                (v for k, v in mapping.items() if k.upper() == curr_up), None
            )
            if matched:
                anomalies.append(_anomaly_d(
                    line=int(idx)+1, field=field, value=current, sheet=sheet_name,
                    error_type="Correspondance à appliquer",
                    severity=severity,
                    message=f"Règle «{label}» : '{current}' → '{matched}'.",
                    rule_label=label,
                    suggested_fix=matched,
                    auto_correct=auto,
                ))

    # ── 4. Condition métier ───────────────────────────────────────────────────
    elif rule_type == "Condition métier":
        # Cherche la structure "Si [champ1] = 'X' alors [champ2] = 'Y'"
        match_if   = re.search(r"si\s+['\"]?([^'\"\s=]+)['\"]?\s*=\s*['\"]([^'\"]+)['\"]", condition, re.IGNORECASE)
        match_then = re.search(r"alors?\s+['\"]?([^'\"\s=]+)['\"]?\s*=?\s*['\"]?([^'\"]+)['\"]?", action, re.IGNORECASE)

        if match_if and match_then:
            cond_field, cond_val = match_if.group(1), match_if.group(2)
            then_field, then_val = match_then.group(1), match_then.group(2)

            if cond_field in df.columns and then_field in df.columns:
                for idx, row in df.iterrows():
                    cf_val   = _to_str(row.get(cond_field))
                    then_cur = _to_str(row.get(then_field))
                    if cf_val.lower() == cond_val.lower():
                        if then_cur.lower() != then_val.lower():
                            anomalies.append(_anomaly_d(
                                line=int(idx)+1, field=then_field, value=then_cur,
                                sheet=sheet_name,
                                error_type="Condition métier non respectée",
                                severity=severity,
                                message=(
                                    f"Règle «{label}» : "
                                    f"Si {cond_field}='{cond_val}' "
                                    f"alors {then_field} doit être '{then_val}' "
                                    f"(valeur actuelle : '{then_cur}')."
                                ),
                                rule_label=label,
                                suggested_fix=then_val,
                                auto_correct=auto,
                            ))

    # ── 5. Format obligatoire ─────────────────────────────────────────────────
    elif rule_type == "Format obligatoire":
        if not field or field not in df.columns:
            return anomalies
        # Chercher un pattern regex dans l'action ou construire depuis la description
        pattern = action.strip()
        if not pattern:
            return anomalies
        # Si c'est une description (pas une regex), essayer de l'interpréter
        if pattern.lower() in ("numérique", "chiffres"):
            pattern = r"^\d+$"
        elif pattern.lower() in ("email", "e-mail"):
            pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        elif "siret" in pattern.lower():
            pattern = r"^\d{14}$"
        elif "siren" in pattern.lower():
            pattern = r"^\d{9}$"

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return anomalies

        for idx, row in df.iterrows():
            current = _to_str(row.get(field))
            if not current:
                continue
            if not compiled.match(current):
                anomalies.append(_anomaly_d(
                    line=int(idx)+1, field=field, value=current, sheet=sheet_name,
                    error_type="Format invalide",
                    severity=severity,
                    message=f"Règle «{label}» : '{field}' = '{current}' ne respecte pas le format '{action}'.",
                    rule_label=label,
                ))

    # ── 6. Plage de valeurs ───────────────────────────────────────────────────
    elif rule_type == "Plage de valeurs":
        if not field or field not in df.columns:
            return anomalies
        rng = _extract_range(action)
        if not rng:
            return anomalies
        min_val, max_val = rng
        for idx, row in df.iterrows():
            current = _to_str(row.get(field))
            if not current:
                continue
            try:
                num = float(current.replace(",", "."))
                if not (min_val <= num <= max_val):
                    anomalies.append(_anomaly_d(
                        line=int(idx)+1, field=field, value=current, sheet=sheet_name,
                        error_type="Valeur hors plage",
                        severity=severity,
                        message=(
                            f"Règle «{label}» : '{field}' = {current} "
                            f"est hors de la plage [{min_val} – {max_val}]."
                        ),
                        rule_label=label,
                    ))
            except ValueError:
                pass

    # ── 7. Exclusion de ligne ─────────────────────────────────────────────────
    elif rule_type == "Exclusion de ligne":
        if not field or field not in df.columns:
            return anomalies
        excl_val = _extract_quoted(condition) if condition else condition
        for idx, row in df.iterrows():
            current = _to_str(row.get(field))
            if current.lower() == excl_val.lower():
                anomalies.append(_anomaly_d(
                    line=int(idx)+1, field=field, value=current, sheet=sheet_name,
                    error_type="Ligne à exclure",
                    severity="Majeure",
                    message=f"Règle «{label}» : ligne exclue car '{field}' = '{current}'.",
                    rule_label=label,
                ))

    # ── 8. Détection doublon ──────────────────────────────────────────────────
    elif rule_type == "Détection doublon":
        # Chercher les champs à combiner dans condition ou field
        fields_to_check = []
        if field and field in df.columns:
            fields_to_check.append(field)
        # Chercher champs supplémentaires dans la condition
        for col in df.columns:
            if col in condition and col != field:
                fields_to_check.append(col)

        if not fields_to_check:
            return anomalies

        seen = {}
        for idx, row in df.iterrows():
            key = tuple(_to_str(row.get(f,"")) for f in fields_to_check)
            if any(v for v in key):
                if key in seen:
                    anomalies.append(_anomaly_d(
                        line=int(idx)+1,
                        field=" + ".join(fields_to_check),
                        value=" / ".join(key),
                        sheet=sheet_name,
                        error_type="Doublon métier",
                        severity=severity,
                        message=(
                            f"Règle «{label}» : combinaison "
                            f"{' + '.join(fields_to_check)} = '{' / '.join(key)}' "
                            f"déjà présente à la ligne {seen[key]}."
                        ),
                        rule_label=label,
                    ))
                else:
                    seen[key] = int(idx)+1

    return anomalies


def validate_axe_d(
    df:          pd.DataFrame,
    rules:       list,
    sheet_name:  str = "",
) -> list:
    """
    Applique toutes les règles métier actives à un DataFrame.
    """
    all_anomalies = []
    for rule in rules:
        if not rule.get("active", True):
            continue
        try:
            anomalies = apply_rule(rule, df, sheet_name)
            all_anomalies.extend(anomalies)
        except Exception:
            pass
    return all_anomalies


def validate_file_axe_d(
    parse_result: dict,
    active_rules: list,
) -> dict:
    """
    Applique les règles métier sur toutes les tables de données.
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

    if not active_rules:
        return result

    data_tables = parse_result.get("data_tables", [])
    sheets      = parse_result.get("sheets", {})
    metadata    = parse_result.get("metadata", {})

    for sheet_name in data_tables:
        df   = sheets.get(sheet_name)
        if df is None or df.empty:
            continue

        meta     = metadata.get(sheet_name, {})
        table_id = meta.get("table_id", "")
        label    = meta.get("label", sheet_name)

        result["lines_analyzed"] += len(df)

        # Filtrer les règles applicables à cette Master Data
        applicable = [
            r for r in active_rules
            if (not r.get("master_data") or
                r.get("master_data") in ("Général", label))
        ]

        anomalies = validate_axe_d(df, applicable, sheet_name)
        result["by_sheet"][sheet_name] = anomalies
        result["all_anomalies"].extend(anomalies)

    result["total_anomalies"] = len(result["all_anomalies"])
    result["major"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Majeure")
    result["minor"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Mineure")
    result["info"]  = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Info")

    return result
