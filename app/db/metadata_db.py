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


# ══════════════════════════════════════════════════════════════════════════════
# LOOKUP DYNAMIQUE PAR TABLE ID
# ══════════════════════════════════════════════════════════════════════════════

# Mapping refTableId → cache_key Supabase existant
# Couvre les tables BC standard les plus courantes.
# Complété automatiquement quand on découvre une nouvelle table.
_REF_TABLE_CACHE_KEYS: dict[int, str] = {
    3:    "paymentTerms",           # Conditions paiement
    4:    "currencies",             # Devises
    5:    "currencies",
    6:    "customerPriceGroups",    # Groupes prix client
    9:    "countriesRegions",       # Pays/Régions
    10:   "shipmentMethods",        # Conditions livraison
    13:   "salespeople",            # Vendeurs/Acheteurs
    14:   "locations",              # Magasins
    15:   "glAccounts",             # Comptes généraux
    18:   "customers",              # Clients
    23:   "vendors",                # Fournisseurs
    27:   "items",                  # Articles
    74:   "vatBusPostingGroups",    # Groupes compta. marché TVA
    76:   "resourceGroups",         # Groupes ressource
    91:   "customerPostingGroups",  # Groupes compta. client
    92:   "vendorPostingGroups",    # Groupes compta. fourn.
    94:   "inventoryPostingGroups", # Groupes compta. stock
    156:  "resources",              # Ressources
    204:  "unitsOfMeasure",         # Unités de mesure
    251:  "genProdPostingGroups",   # Groupes compta. produit
    289:  "paymentMethods",         # Modes de paiement
    308:  "noSeries",               # Souches de n°
    322:  "taxGroups",              # Groupes taxes
    325:  "vatProdPostingGroups",   # Groupes compta. produit TVA
    340:  "itemDiscountGroups",     # Groupes remises article
    5722: "itemCategories",         # Catégories article
    6502: "itemTrackingCodes",      # Codes traçabilité
}

# Mapping refTableId → BC API standard v2.0 (pour fetch à la demande)
_TABLE_BC_ENTITY: dict[int, tuple[str, str]] = {
    # (entity_name, code_field)
    3:    ("paymentTerms", "code"),
    4:    ("currencies", "code"),
    9:    ("countriesRegions", "code"),
    10:   ("shipmentMethods", "code"),
    13:   ("salespeople", "code"),
    14:   ("locations", "code"),
    18:   ("customers", "number"),
    23:   ("vendors", "number"),
    27:   ("items", "number"),
    204:  ("unitsOfMeasure", "code"),
    289:  ("paymentMethods", "code"),
    5722: ("itemCategories", "code"),
}


def get_reference_values_by_table_id(
    profile_code: str,
    company_id:   str,
    ref_table_id: int,
) -> tuple[set[str], bool]:
    """
    Retourne (valid_codes, found) pour une table référencée.

    Stratégie :
      1. Cache Supabase (cache_key connu)
      2. BC API standard v2.0 (entité connue) → mis en cache
      3. set() vide + found=False (table inconnue → INFO non vérifiable)

    Args:
        profile_code : code profil client
        company_id   : ID société BC
        ref_table_id : ID table BC référencée (depuis FldRef.Relation())

    Returns:
        (set[str], bool) — codes valides + indicateur de disponibilité
    """
    if not ref_table_id:
        return set(), False

    # 1. Cache Supabase via cache_key connu
    cache_key = _REF_TABLE_CACHE_KEYS.get(ref_table_id)
    if cache_key:
        try:
            cached = get_reference_values(profile_code, cache_key)
            if cached:
                return set(str(c).strip() for c in cached if c), True
        except Exception:
            pass

    # 2. BC API standard v2.0 → fetch + mise en cache
    entity_info = _TABLE_BC_ENTITY.get(ref_table_id)
    if entity_info and profile_code:
        try:
            codes = _fetch_codes_from_bc_api(
                profile_code, company_id, ref_table_id, entity_info
            )
            if codes:
                # Stocker en cache pour les prochaines validations
                if cache_key:
                    _store_reference_cache(profile_code, cache_key, codes)
                return codes, True
        except Exception:
            pass

    # 3. Table inconnue ou inaccessible
    return set(), False


def _fetch_codes_from_bc_api(
    profile_code:  str,
    company_id:    str,
    ref_table_id:  int,
    entity_info:   tuple[str, str],
) -> set[str]:
    """Fetch les codes valides depuis l'API BC standard v2.0."""
    try:
        from app.db.profiles_db import get_profile_by_code
        from app.core.bc_api import get_access_token
        import requests as _req

        p = get_profile_by_code(profile_code)
        if not p:
            return set()

        tid  = p.get("bc_tenant_id","").strip()
        cid  = p.get("bc_client_id","").strip()
        cs   = p.get("bc_client_secret","").strip()
        env  = p.get("bc_environment","").strip()
        if not all([tid, cid, cs, env, company_id]):
            return set()

        token  = get_access_token(tid, cid, cs)
        entity, code_field = entity_info
        url = (
            f"https://api.businesscentral.dynamics.com/v2.0/{tid}/{env}"
            f"/api/v2.0/companies({company_id})/{entity}"
            f"?$select={code_field}&$top=5000"
        )
        resp = _req.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        resp.raise_for_status()
        values = resp.json().get("value", [])
        return set(str(v.get(code_field,"")).strip() for v in values if v.get(code_field))

    except Exception:
        return set()


def _store_reference_cache(profile_code: str, cache_key: str, codes: set[str]) -> None:
    """Stocke les codes en cache Supabase pour réutilisation."""
    try:
        from app.db.supabase_client import get_supabase_client
        import json
        get_supabase_client().table("bc_metadata_cache").upsert({
            "profile_code": profile_code,
            "cache_key":    cache_key,
            "values":       json.dumps(sorted(codes)),
        }, on_conflict="profile_code,cache_key").execute()
    except Exception:
        pass
