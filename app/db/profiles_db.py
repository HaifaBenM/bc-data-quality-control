"""
Opérations CRUD pour les profils clients dans Supabase.
"""
from app.db.supabase_client import get_supabase_client


def get_all_profiles() -> list:
    """Retourne tous les profils clients."""
    try:
        client = get_supabase_client()
        res = client.table("client_profiles").select("*").order("name").execute()
        return res.data or []
    except Exception:
        return []


def get_profile_by_code(code: str) -> dict:
    """Retourne un profil par son code."""
    try:
        client = get_supabase_client()
        res = client.table("client_profiles").select("*").eq("code", code).execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


def create_profile(data: dict) -> tuple[bool, str]:
    """Crée un nouveau profil client."""
    try:
        client = get_supabase_client()
        client.table("client_profiles").insert(data).execute()
        return True, ""
    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "unique" in err.lower():
            return False, f"Le code client '{data.get('code', '')}' existe déjà."
        return False, f"Erreur : {err}"


def update_profile(code: str, data: dict) -> tuple[bool, str]:
    """Met à jour un profil existant."""
    try:
        client = get_supabase_client()
        client.table("client_profiles").update(data).eq("code", code).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def delete_profile(code: str) -> tuple[bool, str]:
    """Supprime un profil et toutes ses règles."""
    try:
        client = get_supabase_client()
        client.table("business_rules").delete().eq("profile_code", code).execute()
        client.table("client_profiles").delete().eq("code", code).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def get_profile_stats(code: str) -> dict:
    """Retourne le nombre de règles actives/totales d'un profil."""
    try:
        client = get_supabase_client()
        res = client.table("business_rules").select("active").eq("profile_code", code).execute()
        rules = res.data or []
        return {
            "total_rules":  len(rules),
            "active_rules": sum(1 for r in rules if r.get("active", True)),
        }
    except Exception:
        return {"total_rules": 0, "active_rules": 0}


def get_profiles_for_select() -> list[dict]:
    """Retourne la liste simplifiée pour les listes déroulantes."""
    profiles = get_all_profiles()
    return [
        {
            "code":  p["code"],
            "name":  p["name"],
            "label": f"{p['name']} ({p['code']})",
        }
        for p in profiles
    ]
