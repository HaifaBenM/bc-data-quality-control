"""
Opérations de cache metadata BC dans Supabase.
Cache cloisonné par (profile_code, company_id, entity_name).
TTL : 24 heures. Lazy load automatique depuis BC API si cache absent.
"""
import json
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import get_supabase_client


# ══════════════════════════════════════════════════════════════════════════════
# CRUD CACHE
# ══════════════════════════════════════════════════════════════════════════════

def save_metadata(
    profile_code: str,
    company_id:   str,
    entity_name:  str,
    entity_type:  str,
    fields:       list,
) -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        client.table("bc_metadata_cache").upsert({
            "profile_code": profile_code,
            "company_id":   company_id,
            "entity_name":  entity_name,
            "entity_type":  entity_type,
            "fields":       json.dumps(fields),
            "cached_at":    datetime.now(timezone.utc).isoformat(),
        }, on_conflict="profile_code,company_id,entity_name").execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def save_reference_data(
    profile_code: str,
    company_id:   str,
    entity_name:  str,
    label:        str,
    data:         list,
    record_count: int,
) -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        client.table("bc_metadata_cache").upsert({
            "profile_code": profile_code,
            "company_id":   company_id,
            "entity_name":  entity_name,
            "entity_type":  "reference",
            "fields":       json.dumps(data),
            "record_count": record_count,
            "cached_at":    datetime.now(timezone.utc).isoformat(),
        }, on_conflict="profile_code,company_id,entity_name").execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_cached_metadata(
    profile_code: str,
    company_id:   str,
    entity_name:  str,
) -> dict | None:
    try:
        client = get_supabase_client()
        res = (
            client.table("bc_metadata_cache")
            .select("*")
            .eq("profile_code", profile_code)
            .eq("company_id",   company_id)
            .eq("entity_name",  entity_name)
            .execute()
        )
        if res.data:
            row = res.data[0]
            if isinstance(row.get("fields"), str):
                row["fields"] = json.loads(row["fields"])
            return row
        return None
    except Exception:
        return None


def get_all_cached_entities(
    profile_code: str,
    company_id:   str,
) -> list:
    try:
        client = get_supabase_client()
        res = (
            client.table("bc_metadata_cache")
            .select("entity_name, entity_type, record_count, cached_at")
            .eq("profile_code", profile_code)
            .eq("company_id",   company_id)
            .order("entity_type")
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def is_cache_valid(
    profile_code: str,
    company_id:   str,
    entity_name:  str,
    hours:        int = 24,
) -> bool:
    row = get_cached_metadata(profile_code, company_id, entity_name)
    if not row:
        return False
    try:
        cached_at = datetime.fromisoformat(row["cached_at"])
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - cached_at < timedelta(hours=hours)
    except Exception:
        return False


def get_cache_summary(
    profile_code: str,
    company_id:   str = "",
) -> dict:
    entities = get_all_cached_entities(profile_code, company_id)
    if not entities:
        return {"total": 0, "data": 0, "reference": 0, "last_update": None}
    dates = []
    for e in entities:
        try:
            dates.append(datetime.fromisoformat(e["cached_at"]))
        except Exception:
            pass
    return {
        "total":       len(entities),
        "data":        sum(1 for e in entities if e.get("entity_type") == "data"),
        "reference":   sum(1 for e in entities if e.get("entity_type") == "reference"),
        "system":      sum(1 for e in entities if e.get("entity_type") == "system"),
        "last_update": max(dates).strftime("%d/%m/%Y %H:%M") if dates else None,
    }


def delete_cache(
    profile_code: str,
    company_id:   str = "",
) -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        q = client.table("bc_metadata_cache").delete().eq("profile_code", profile_code)
        if company_id:
            q = q.eq("company_id", company_id)
        q.execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_reference_values(
    profile_code: str,
    company_id:   str,
    entity_name:  str,
    code_field:   str = "code",
) -> list[str]:
    row = get_cached_metadata(profile_code, company_id, entity_name)
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


# ══════════════════════════════════════════════════════════════════════════════
# LOOKUP DYNAMIQUE — lazy load universel
# ══════════════════════════════════════════════════════════════════════════════

# Cache key Supabase par table ID — pour nommage cohérent
_REF_TABLE_CACHE_KEYS: dict[int, str] = {
    3:    "paymentTerms",
    4:    "currencies",
    5:    "currencies",
    6:    "customerPriceGroups",
    9:    "countriesRegions",
    10:   "shipmentMethods",
    13:   "salespeople",
    14:   "locations",
    15:   "glAccounts",
    18:   "customers",
    23:   "vendors",
    27:   "items",
    74:   "vatBusinessPostingGroups",
    76:   "resourceGroups",
    91:   "customerPostingGroups",
    92:   "vendorPostingGroups",
    94:   "inventoryPostingGroups",
    156:  "resources",
    204:  "unitsOfMeasure",
    251:  "generalProductPostingGroups",
    289:  "paymentMethods",
    308:  "noSeries",
    322:  "taxGroups",
    325:  "vatProductPostingGroups",
    340:  "itemDiscountGroups",
    5722: "itemCategories",
    6502: "itemTrackingCodes",
}

# Fallback BC API v2.0 pour tables standard
# Utilisé uniquement si refFieldId absent (plan par défaut)
_TABLE_BC_ENTITY: dict[int, tuple[str, str]] = {
    3:    ("paymentTerms",                 "code"),
    4:    ("currencies",                   "code"),
    9:    ("countriesRegions",             "code"),
    10:   ("shipmentMethods",              "code"),
    13:   ("salespeople",                  "code"),
    14:   ("locations",                    "code"),
    15:   ("glAccounts",                   "number"),
    18:   ("customers",                    "number"),
    23:   ("vendors",                      "number"),
    27:   ("items",                        "number"),
    74:   ("vatBusinessPostingGroups",     "code"),
    91:   ("customerPostingGroups",        "code"),
    92:   ("vendorPostingGroups",          "code"),
    94:   ("inventoryPostingGroups",       "code"),
    204:  ("unitsOfMeasure",              "code"),
    251:  ("generalProductPostingGroups", "code"),
    289:  ("paymentMethods",              "code"),
    325:  ("vatProductPostingGroups",     "code"),
    340:  ("itemDiscountGroups",          "code"),
    5722: ("itemCategories",              "code"),
}


def get_reference_values_by_table_id(
    profile_code: str,
    company_id:   str,
    ref_table_id: int,
    ref_field_id: int = 0,
) -> tuple[set[str], bool]:
    """
    Retourne (valid_codes, found) pour une table référencée.

    Stratégie (dans l'ordre) :
      1. Cache Supabase — (profile_code, company_id, entity_name)
      2. Lazy load via extension AL tableValues — universel, toutes tables
      3. Fallback BC API v2.0 — tables standard si refFieldId absent
      4. set() vide + found=False — INFO "non vérifiable"
    """
    if not ref_table_id:
        return set(), False

    cache_key = _REF_TABLE_CACHE_KEYS.get(ref_table_id, f"table_{ref_table_id}")

    # 1. Cache Supabase
    if company_id:
        try:
            cached = get_reference_values(profile_code, company_id, cache_key)
            if cached:
                return set(str(c).strip() for c in cached if c), True
        except Exception:
            pass

    # 2. Lazy load via extension AL (universel)
    if ref_field_id and profile_code and company_id:
        try:
            codes = _fetch_via_al_extension(
                profile_code, company_id, ref_table_id, ref_field_id
            )
            if codes:
                _store_reference_cache(profile_code, company_id, cache_key, codes)
                return codes, True
        except Exception:
            pass

    # 3. Fallback BC API v2.0 (tables standard sans refFieldId)
    entity_info = _TABLE_BC_ENTITY.get(ref_table_id)
    if entity_info and profile_code and company_id:
        try:
            codes = _fetch_codes_from_bc_api(
                profile_code, company_id, ref_table_id, entity_info
            )
            if codes:
                _store_reference_cache(profile_code, company_id, cache_key, codes)
                return codes, True
        except Exception:
            pass

    # 4. Non vérifiable
    return set(), False


def _fetch_via_al_extension(
    profile_code: str,
    company_id:   str,
    table_id:     int,
    field_no:     int,
) -> set[str]:
    """Fetch via endpoint générique AL — couvre toutes les tables BC."""
    try:
        from app.db.profiles_db import get_profile_by_code
        from app.core.bc_api import get_access_token, get_table_values

        p = get_profile_by_code(profile_code)
        if not p:
            return set()

        tid = p.get("bc_tenant_id",    "").strip()
        cid = p.get("bc_client_id",    "").strip()
        cs  = p.get("bc_client_secret","").strip()
        env = p.get("bc_environment",  "").strip()
        if not all([tid, cid, cs, env, company_id]):
            return set()

        token = get_access_token(tid, cid, cs)
        return get_table_values(tid, env, company_id, table_id, field_no, token)
    except Exception:
        return set()


def _fetch_codes_from_bc_api(
    profile_code: str,
    company_id:   str,
    ref_table_id: int,
    entity_info:  tuple[str, str],
) -> set[str]:
    """Fetch via BC API v2.0 standard — fallback tables connues."""
    try:
        from app.db.profiles_db import get_profile_by_code
        from app.core.bc_api import get_access_token
        import requests as _req

        p = get_profile_by_code(profile_code)
        if not p:
            return set()

        tid = p.get("bc_tenant_id",    "").strip()
        cid = p.get("bc_client_id",    "").strip()
        cs  = p.get("bc_client_secret","").strip()
        env = p.get("bc_environment",  "").strip()
        if not all([tid, cid, cs, env, company_id]):
            return set()

        token          = get_access_token(tid, cid, cs)
        entity, code_f = entity_info
        url = (
            f"https://api.businesscentral.dynamics.com/v2.0/{tid}/{env}"
            f"/api/v2.0/companies({company_id})/{entity}"
            f"?$select={code_f}&$top=5000"
        )
        resp = _req.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        resp.raise_for_status()
        values = resp.json().get("value", [])
        return set(
            str(v.get(code_f, "")).strip()
            for v in values if v.get(code_f)
        )
    except Exception:
        return set()


def _store_reference_cache(
    profile_code: str,
    company_id:   str,
    cache_key:    str,
    codes:        set[str],
) -> None:
    try:
        data = [{"code": c} for c in sorted(codes)]
        save_reference_data(
            profile_code=profile_code,
            company_id=company_id,
            entity_name=cache_key,
            label=cache_key,
            data=data,
            record_count=len(data),
        )
    except Exception:
        pass