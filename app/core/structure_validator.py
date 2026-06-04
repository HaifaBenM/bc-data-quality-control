"""
Module de validation structurelle.
Valide le format et la cohérence du fichier BC Configuration Package.
"""


def validate_file_structure(parse_result: dict) -> dict:
    """
    Valide la structure du fichier après auto-détection.
    Ne nécessite plus de liste d'onglets attendus — tout est auto-détecté.
    """
    result = {
        "is_valid":        True,
        "blocking_errors": [],
        "warnings":        [],
        "data_tables":     [],   # tables de données validées
        "ref_tables":      [],   # tables de référence détectées
        "summary":         {}
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

    # ── Vérification 1 : Le fichier contient-il des tables de données ? ───────
    if not data_tables:
        result["is_valid"] = False
        result["blocking_errors"].append(
            "Aucune table de données BC détectée dans ce fichier. "
            "Vérifiez que le fichier est bien un export de Package de Configuration BC "
            "(Clients, Fournisseurs, Articles, Plan comptable...)."
        )
        return result

    # ── Vérification 2 : Tables de données vides ─────────────────────────────
    empty_data = []
    for sheet in data_tables:
        rows = total_rows.get(sheet, 0)
        meta = metadata.get(sheet, {})
        label = meta.get("label", sheet)

        if rows == 0:
            empty_data.append(sheet)
            result["warnings"].append(
                f"⚠ Table de données '{sheet}' ({label}) : "
                "aucune ligne — le client n'a pas saisi de données sur cet onglet."
            )
        else:
            result["data_tables"].append({
                "sheet":    sheet,
                "label":    label,
                "table_id": meta.get("table_id", "?"),
                "rows":     rows,
                "cols":     len(sheets.get(sheet, {}).columns) if sheet in sheets else 0,
            })

    # ── Vérification 3 : Tables de référence présentes ? ─────────────────────
    result["ref_tables"] = [
        {
            "sheet":    sheet,
            "label":    metadata.get(sheet, {}).get("label", sheet),
            "table_id": metadata.get(sheet, {}).get("table_id", "?"),
            "rows":     total_rows.get(sheet, 0),
        }
        for sheet in ref_tables
    ]

    if not ref_tables:
        result["warnings"].append(
            "⚠ Aucune table de référence détectée. "
            "La validation des codes (pays, conditions paiement...) "
            "ne pourra pas être effectuée (Sprint 5)."
        )

    # ── Reprendre les warnings du parsing ─────────────────────────────────────
    for warning in parse_result.get("warnings", []):
        result["warnings"].append(warning)

    # ── Résumé ────────────────────────────────────────────────────────────────
    nb_data_ok = len(result["data_tables"])
    nb_data_empty = len(empty_data)

    result["summary"] = {
        "nb_data_tables":    len(data_tables),
        "nb_data_with_rows": nb_data_ok,
        "nb_data_empty":     nb_data_empty,
        "nb_ref_tables":     len(ref_tables),
        "status": (
            "✅ Fichier conforme — prêt pour l'analyse qualité"
            if result["is_valid"] and nb_data_ok > 0
            else "⚠️ Fichier conforme avec avertissements"
            if result["is_valid"]
            else "❌ Fichier non conforme"
        )
    }

    return result
