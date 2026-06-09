"""
Opérations de cache metadata BC dans Supabase.
Evite de relire la metadata BC à chaque session.
TTL : 24 heures par défaut.
"""
import json
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import get_supabase_client


# ── CACHE METADATA (champs/types) ─────────────────────────────────────────────

def save_metadata(
    profile_code: str,
    entity_name:  str,
    entity_type:  str,
    fields:       list,
) -> tuple[bool, str]:
    """Sauvegarde ou met à jour la metadata d'une entité BC."""
    try:
        client = get_supabase_client()
        client.table("bc_metadata_cache").upsert({
            "profile_code": profile_code,
            "entity_name":  entity_name,
            "entity_type":  entity_type,
            "fields":       json.dumps(fields),
            "cached_at":    datetime.now(timezone.utc).isoformat(),
        }, on_conflict="profile_code,entity_name").execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def save_reference_data(
    profile_code:  str,
    entity_name:   str,
    label:         str,
    data:          list,
    record_count:  int,
) -> tuple[bool, str]:
    """Sauvegarde les données d'une table de référence BC."""
    try:
        client = get_supabase_client()
        client.table("bc_metadata_cache").upsert({
            "profile_code": profile_code,
            "entity_name":  entity_name,
            "entity_type":  "reference",
            "fields":       json.dumps(data),   # données réelles
            "record_count": record_count,
            "cached_at":    datetime.now(timezone.utc).isoformat(),
        }, on_conflict="profile_code,entity_name").execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_cached_metadata(
    profile_code: str,
    entity_name:  str,
) -> dict | None:
    """Retourne la metadata mise en cache, ou None si absente."""
    try:
        client = get_supabase_client()
        res = (
            client.table("bc_metadata_cache")
            .select("*")
            .eq("profile_code", profile_code)
            .eq("entity_name", entity_name)
            .execute()
        )
        if res.data:
            row = res.data[0]
            # Désérialiser le JSON
            if isinstance(row.get("fields"), str):
                row["fields"] = json.loads(row["fields"])
            return row
        return None
    except Exception:
        return None


def get_all_cached_entities(profile_code: str) -> list:
    """Retourne toutes les entités en cache pour un profil."""
    try:
        client = get_supabase_client()
        res = (
            client.table("bc_metadata_cache")
            .select("entity_name, entity_type, record_count, cached_at")
            .eq("profile_code", profile_code)
            .order("entity_type")
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def is_cache_valid(
    profile_code: str,
    entity_name:  str,
    hours:        int = 24,
) -> bool:
    """Vérifie si le cache est encore valide (moins de X heures)."""
    row = get_cached_metadata(profile_code, entity_name)
    if not row:
        return False
    try:
        cached_at = datetime.fromisoformat(row["cached_at"])
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - cached_at
        return age < timedelta(hours=hours)
    except Exception:
        return False


def get_cache_summary(profile_code: str) -> dict:
    """Retourne un résumé du cache pour un profil."""
    entities = get_all_cached_entities(profile_code)
    if not entities:
        return {
            "total":      0,
            "data":       0,
            "reference":  0,
            "last_update": None,
        }

    data_count = sum(1 for e in entities if e.get("entity_type") == "data")
    ref_count  = sum(1 for e in entities if e.get("entity_type") == "reference")
    sys_count  = sum(1 for e in entities if e.get("entity_type") == "system")

    # Trouver la date du dernier chargement
    dates = []
    for e in entities:
        try:
            dates.append(datetime.fromisoformat(e["cached_at"]))
        except Exception:
            pass

    last_update = max(dates).strftime("%d/%m/%Y %H:%M") if dates else None

    return {
        "total":       len(entities),
        "data":        data_count,
        "reference":   ref_count,
        "system":      sys_count,
        "last_update": last_update,
    }


def delete_cache(profile_code: str) -> tuple[bool, str]:
    """Supprime tout le cache d'un profil."""
    try:
        client = get_supabase_client()
        client.table("bc_metadata_cache").delete().eq(
            "profile_code", profile_code
        ).execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_reference_values(
    profile_code: str,
    entity_name:  str,
    code_field:   str = "code",
) -> list[str]:
    """
    Retourne la liste des codes valides d'une table de référence.
    Utilisé pour la validation Axe B (Sprint 5).
    """
    row = get_cached_metadata(profile_code, entity_name)
    if not row:
        return []
    try:
        data = row.get("fields", [])
        return [
            str(item.get(code_field, "")).strip()
            for item in data
            if item.get(code_field)
        ]
    except Exception:
        return []
