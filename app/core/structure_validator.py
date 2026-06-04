"""
Module de validation structurelle du fichier.
Vérifie que la structure du fichier correspond au template BC attendu.
"""


def validate_file_structure(
    parse_result: dict,
    expected_sheets: list,
    master_data_name: str = ""
) -> dict:
    """
    Valide la structure du fichier par rapport aux onglets attendus.

    Args:
        parse_result   : résultat du parsing (depuis file_parser.py)
        expected_sheets: liste des onglets attendus (sélectionnés par l'équipe BC)
        master_data_name: nom de la Master Data (pour les messages)

    Retourne un dict avec :
    - is_valid (bool)         : True si aucune erreur bloquante
    - blocking_errors (list)  : erreurs qui empêchent l'analyse
    - warnings (list)         : avertissements non bloquants
    - missing_sheets (list)   : onglets attendus mais absents
    - extra_sheets (list)     : onglets présents mais non attendus
    - conforming_sheets (list): onglets présents et conformes
    - details (dict)          : détail par onglet
    """
    result = {
        "is_valid": True,
        "blocking_errors": [],
        "warnings": [],
        "missing_sheets": [],
        "extra_sheets": [],
        "conforming_sheets": [],
        "details": {}
    }

    # Si le parsing a échoué, on ne peut pas valider
    if not parse_result.get("success"):
        result["is_valid"] = False
        result["blocking_errors"].extend(parse_result.get("errors", []))
        return result

    # Récupérer les onglets présents dans le fichier
    file_sheets = list(parse_result.get("sheet_names", []))

    # ── Vérification 1 : Onglets attendus présents ? ─────────────────────────
    for expected in expected_sheets:
        if expected not in file_sheets:
            result["blocking_errors"].append(
                f"Onglet manquant : '{expected}' — "
                "cet onglet était présent dans le template envoyé au client."
            )
            result["missing_sheets"].append(expected)
            result["is_valid"] = False
        else:
            result["conforming_sheets"].append(expected)
            result["details"][expected] = {"status": "ok", "issues": []}

    # ── Vérification 2 : Onglets supplémentaires non prévus ──────────────────
    for sheet in file_sheets:
        if sheet not in expected_sheets:
            result["warnings"].append(
                f"Onglet non attendu : '{sheet}' — "
                "cet onglet ne fait pas partie du template. Il sera ignoré lors du contrôle."
            )
            result["extra_sheets"].append(sheet)

    # ── Vérification 3 : Onglets présents mais vides ─────────────────────────
    for sheet in result["conforming_sheets"]:
        df = parse_result["sheets"].get(sheet)
        if df is not None and df.empty:
            result["warnings"].append(
                f"Onglet '{sheet}' : présent mais vide — "
                "aucune donnée à contrôler."
            )
            result["details"][sheet]["status"] = "empty"
            result["details"][sheet]["issues"].append("Onglet vide")

    # ── Reprendre les warnings du parsing (formules, colonnes sans nom) ───────
    for warning in parse_result.get("warnings", []):
        result["warnings"].append(warning)

    # ── Résumé ────────────────────────────────────────────────────────────────
    nb_ok = len(result["conforming_sheets"])
    nb_missing = len(result["missing_sheets"])
    nb_extra = len(result["extra_sheets"])

    result["summary"] = {
        "total_expected": len(expected_sheets),
        "conforming": nb_ok,
        "missing": nb_missing,
        "extra": nb_extra,
        "status": (
            "✅ Structure conforme"
            if result["is_valid"] and nb_ok > 0
            else "❌ Structure non conforme" if not result["is_valid"]
            else "⚠️ Structure avec avertissements"
        )
    }

    return result


def get_validation_color(is_valid: bool) -> str:
    """Retourne la couleur selon le statut de validation."""
    return "green" if is_valid else "red"
