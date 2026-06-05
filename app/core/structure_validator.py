"""
Module de validation structurelle du fichier BC Configuration Package.
"""


def validate_file_structure(parse_result: dict) -> dict:
    """Valide la structure du fichier après auto-détection."""
    result = {
        "is_valid":        True,
        "blocking_errors": [],
        "warnings":        [],
        "data_tables":     [],
        "ref_tables":      [],
        "summary":         {},
    }

    if not parse_result.get("success"):
        result["is_valid"] = False
        result["blocking_errors"].extend(parse_result.get("errors", []))
        return result

    data_tables = parse_result.get("data_tables", [])
    ref_tables  = parse_result.get("ref_tables", [])
    metadata    = parse_result.get("metadata", {})
    sheets      = parse_result.get("sheets", {})
    total_rows  = parse_result.get("total_rows", {})

    # Vérification 1 : au moins une table de données
    if not data_tables:
        result["is_valid"] = False
        result["blocking_errors"].append(
            "Aucune table de données BC détectée dans ce fichier. "
            "Vérifiez que le fichier est bien un export de Package de "
            "Configuration BC (Clients, Fournisseurs, Articles...)."
        )
        return result

    # Vérification 2 : tables de données
    for sheet in data_tables:
        rows = total_rows.get(sheet, 0)
        meta = metadata.get(sheet, {})
        label = meta.get("label", sheet)
        cols  = len(sheets.get(sheet, {}).columns) if sheet in sheets else 0

        if rows == 0:
            result["warnings"].append(
                f"⚠ Table '{sheet}' ({label}) : aucune ligne de données."
            )
        else:
            result["data_tables"].append({
                "sheet":    sheet,
                "label":    label,
                "table_id": meta.get("table_id", "?"),
                "rows":     rows,
                "cols":     cols,
            })

    # Vérification 3 : tables de référence
    result["ref_tables"] = [
        {
            "sheet":    s,
            "label":    metadata.get(s, {}).get("label", s),
            "table_id": metadata.get(s, {}).get("table_id", "?"),
            "rows":     total_rows.get(s, 0),
        }
        for s in ref_tables
    ]

    if not ref_tables:
        result["warnings"].append(
            "⚠ Aucune table de référence. La validation des codes "
            "(pays, conditions paiement...) ne pourra pas être effectuée."
        )

    # Reprendre les avertissements du parsing
    for w in parse_result.get("warnings", []):
        result["warnings"].append(w)

    # Résumé
    nb_ok = len(result["data_tables"])
    result["summary"] = {
        "nb_data_tables":    len(data_tables),
        "nb_data_with_rows": nb_ok,
        "nb_ref_tables":     len(ref_tables),
        "status": (
            "✅ Fichier conforme — prêt pour l'analyse qualité"
            if result["is_valid"] and nb_ok > 0
            else "⚠️ Fichier conforme avec avertissements"
            if result["is_valid"]
            else "❌ Fichier non conforme"
        ),
    }

    return result
