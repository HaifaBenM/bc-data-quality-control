"""
Opérations CRUD pour les règles métier dans Supabase.
"""
from app.db.supabase_client import get_supabase_client

RULE_TYPES = [
    "Valeur par défaut",
    "Transformation",
    "Table de correspondance",
    "Condition métier",
    "Format obligatoire",
    "Plage de valeurs",
    "Exclusion de ligne",
    "Détection doublon",
]

RULE_TYPES_HELP = {
    "Valeur par défaut":       "Si un champ est vide → mettre une valeur fixe",
    "Transformation":          "Remplacer une valeur par une autre (ex : 'M.' → 'Mr.')",
    "Table de correspondance": "Mapper plusieurs valeurs vers leurs codes BC",
    "Condition métier":        "Vérifier la cohérence entre deux champs",
    "Format obligatoire":      "Vérifier que la valeur respecte un format défini",
    "Plage de valeurs":        "Vérifier qu'une valeur est dans un intervalle",
    "Exclusion de ligne":      "Marquer une ligne à ne pas importer",
    "Détection doublon":       "Signaler des lignes potentiellement dupliquées",
}

SEVERITIES = ["Mineure", "Majeure", "Info"]

AUTO_CORRECT_TYPES = [
    "Valeur par défaut",
    "Transformation",
    "Table de correspondance",
    "Exclusion de ligne",
]


def get_rules_for_profile(profile_code: str) -> list:
    """Retourne toutes les règles d'un profil."""
    try:
        client = get_supabase_client()
        res = (
            client.table("business_rules")
            .select("*")
            .eq("profile_code", profile_code)
            .order("exec_order")
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def get_active_rules_for_profile(profile_code: str) -> list:
    """Retourne uniquement les règles actives d'un profil."""
    return [r for r in get_rules_for_profile(profile_code) if r.get("active", True)]


def create_rule(data: dict) -> tuple[bool, str]:
    """Crée une nouvelle règle."""
    try:
        client = get_supabase_client()
        existing = get_rules_for_profile(data.get("profile_code", ""))
        max_order = max((r.get("exec_order", 0) for r in existing), default=0)
        data["exec_order"] = max_order + 10
        client.table("business_rules").insert(data).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def update_rule(rule_id: str, data: dict) -> tuple[bool, str]:
    """Met à jour une règle."""
    try:
        client = get_supabase_client()
        client.table("business_rules").update(data).eq("id", rule_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def delete_rule(rule_id: str) -> tuple[bool, str]:
    """Supprime une règle."""
    try:
        client = get_supabase_client()
        client.table("business_rules").delete().eq("id", rule_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def toggle_rule(rule_id: str, active: bool) -> tuple[bool, str]:
    """Active ou désactive une règle."""
    return update_rule(rule_id, {"active": active})


def copy_rules_to_profile(source_code: str, target_code: str) -> tuple[bool, str, int]:
    """Copie toutes les règles d'un profil vers un autre."""
    try:
        client = get_supabase_client()
        rules = get_rules_for_profile(source_code)
        if not rules:
            return False, "Le profil source n'a aucune règle.", 0
        copied = 0
        for rule in rules:
            new_rule = {k: v for k, v in rule.items() if k != "id"}
            new_rule["profile_code"] = target_code
            client.table("business_rules").insert(new_rule).execute()
            copied += 1
        return True, f"{copied} règle(s) copiée(s) avec succès.", copied
    except Exception as e:
        return False, f"Erreur : {str(e)}", 0


def get_rules_by_master_data(profile_code: str) -> dict:
    """Retourne les règles groupées par Master Data."""
    rules = get_rules_for_profile(profile_code)
    grouped = {}
    for rule in rules:
        md = rule.get("master_data", "Général")
        grouped.setdefault(md, []).append(rule)
    return grouped
