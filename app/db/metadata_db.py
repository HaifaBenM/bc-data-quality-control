"""
Opérations de cache metadata BC dans Supabase.
Cache cloisonné par (profile_code, company_id, entity_name).
TTL : 24 heures. Lazy load automatique depuis BC API si cache absent.
"""
import json
import streamlit as st
from datetime import datetime, timezone, timedelta
from app.db.supabase_client import get_supabase_client


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


def save_roadmap_table_history(profile_code: str, company_id: str, pkg_code: str, table_ids) -> tuple[bool, str]:
    """AJOUTÉ (23/08/2026) — demande Rami : forcer TOUTES les tables déjà
    résolues (✓ vert) à rester affichées dans la roadmap en permanence,
    même après un "▶️ Reprendre" (qui vide session_state et donc perd la
    mémoire in-memory `previous_table_ids` déjà en place pour la même
    session de travail continue). Réutilise le mécanisme générique
    bc_metadata_cache (save_metadata/get_cached_metadata, déjà utilisé
    pour gl_account_posting_fields et table_captions) plutôt qu'une
    nouvelle table/migration Supabase — clé synthétique par package
    (entity_name=f"roadmap_tables_{pkg_code}"), aucune expiration
    (contrairement au TTL des valeurs de référence : une table une fois
    vue dans la roadmap d'un package doit y rester indéfiniment)."""
    return save_metadata(
        profile_code, company_id, f"roadmap_tables_{pkg_code}",
        "roadmap_history", sorted(set(table_ids)),
    )


def get_roadmap_table_history(profile_code: str, company_id: str, pkg_code: str) -> set:
    """Voir save_roadmap_table_history. set() si rien de persisté encore."""
    row = get_cached_metadata(profile_code, company_id, f"roadmap_tables_{pkg_code}")
    if not row:
        return set()
    try:
        return set(int(t) for t in row.get("fields", []))
    except (TypeError, ValueError):
        return set()


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


def clear_reference_cache(
    profile_code: str,
    company_id:   str,
    ref_table_id: int | None = None,
) -> tuple[bool, str]:
    """
    AJOUTÉ (19/08/2026) : vide le cache Supabase (bc_metadata_cache,
    entity_type='reference') d'une table référencée précise, ou de TOUTES
    les tables référencées si ref_table_id est None.

    Pourquoi : get_reference_values_by_table_id() n'a AUCUNE expiration
    (TTL) — une fois une entrée en cache, elle reste utilisée indéfiniment,
    même si BC a changé depuis (mêmes symptômes que le cache
    gl_account_posting_fields périmé du 28/07, ici sur les tables de
    référence Axe B/Trigger Simulator : ex. table 251 Groupe compta.
    produit répondant "introuvable" pour des groupes pourtant créés dans
    BC après la mise en cache initiale). Pas de solution automatique de
    fraîcheur pour l'instant — vidage manuel à la demande, même logique que
    le bouton "🔄 Recharger classification niveaux" déjà en place pour
    level_config.
    """
    try:
        client = get_supabase_client()
        query = (
            client.table("bc_metadata_cache")
            .delete()
            .eq("profile_code", profile_code)
            .eq("company_id",   company_id)
            .eq("entity_type",  "reference")
        )
        if ref_table_id is not None:
            cache_key = _REF_TABLE_CACHE_KEYS.get(ref_table_id, f"table_{ref_table_id}")
            query = query.eq("entity_name", cache_key)
        query.execute()
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
    204:  ("unitsOfMeasure",               "code"),
    251:  ("generalProductPostingGroups",  "code"),
    289:  ("paymentMethods",               "code"),
    325:  ("vatProductPostingGroups",      "code"),
    340:  ("itemDiscountGroups",           "code"),
    5722: ("itemCategories",               "code"),
}


def get_reference_values_by_table_id(
    profile_code: str,
    company_id:   str,
    ref_table_id: int,
    ref_field_id: int = 0,
    cache_ttl_hours: float = 6.0,
) -> tuple[set[str], bool]:
    """
    Retourne (valid_codes, found) pour une table référencée.

    Stratégie :
      1. Cache Supabase (si encore frais — voir cache_ttl_hours ci-dessous)
      2. Lazy load via AL tableValues — refFieldId ou fallback field 1
      3. Fallback BC API v2.0
      4. set() vide + found=False → INFO

    AJOUTÉ (22/08/2026) — cache_ttl_hours : jusqu'ici cette entrée de cache
    n'avait AUCUNE expiration (seul un clic manuel sur "Vider le cache"
    la rafraîchissait), ce qui a déjà causé un faux blocage confirmé le
    19/08 (table 251 "introuvable" alors que les groupes existaient dans
    BC depuis leur création après la mise en cache). Un TTL réduit ce
    risque sans reproduire le coût mesuré du 18/08 (354s→7s).

    RÉVISÉ (23/08/2026) — 1h abaissait trop souvent le cache pendant une
    session de test rapprochée (plusieurs analyses par heure) : chaque
    expiration force un aller-retour BC en direct sur TOUTES les tables de
    référence du fichier, pas une seule, d'où l'Étape 3 perçue comme
    "beaucoup plus lente" dès qu'une heure s'était écoulée depuis le
    dernier passage. Remonté à 6h — assez long pour ne pas pénaliser des
    tests rapprochés, assez court pour rester loin des délais de plusieurs
    jours qui ont causé le faux blocage du 19/08. Le bouton manuel "Vider
    le cache" (Étape 1) reste la bonne réponse pour un rafraîchissement
    immédiat juste après une modif BC, plutôt que de redescendre encore le
    TTL.
    """
    if not ref_table_id:
        return set(), False

    cache_key   = _REF_TABLE_CACHE_KEYS.get(ref_table_id, f"table_{ref_table_id}")
    entity_info = _TABLE_BC_ENTITY.get(ref_table_id)

    # 1. Cache Supabase — seulement si encore frais (cache_ttl_hours)
    if company_id:
        try:
            if is_cache_valid(profile_code, company_id, cache_key, hours=cache_ttl_hours):
                cached = get_reference_values(profile_code, company_id, cache_key)
                if cached:
                    return set(str(c).strip() for c in cached if c), True
        except Exception:
            pass

    # Trace si au moins UN appel a techniquement réussi (HTTP 200 / pas d'exception),
    # même si le résultat est vide. Ça distingue "table vide" (found=True, valider
    # quand même — toute valeur non vide devient une anomalie) de "source inaccessible"
    # (found=False — vraiment non vérifiable, pas de faux positifs).
    source_reachable = False

    # AJOUTÉ (19/08/2026) — table 349 (Dimension Value / Section analytique) :
    # le champ 1 standard BC est "Dimension Code" (le code de l'AXE parent,
    # ex. "SECTION"), PAS la valeur elle-même — "Code" (la vraie valeur, ex.
    # "LOCATIONS DIVERSES") est le champ 2. Le repli générique "champ 1 si
    # ref_field_id non résolu" (juste en dessous) est donc faux spécifiquement
    # pour cette table : "Code Axe analytique principal 2" est une relation
    # filtrée/composite (TableRelation = "Dimension Value".Code WHERE
    # ("Dimension Code"=...)), et packageFields ne résout pas toujours un
    # numéro de champ propre pour ce genre de relation — ref_field_id retombe
    # à 0, et le champ 1 (le mauvais) est utilisé par défaut. Confirmé en
    # direct (diagnostic Rami, 19/08) : la table 349 retournait "SECTION"
    # (le code d'axe) au lieu des 3 valeurs réellement créées. Champ 2 forcé
    # ici uniquement quand ref_field_id n'a pas pu être résolu autrement —
    # un ref_field_id explicite et non nul (ex. venant vraiment de BC) reste
    # toujours prioritaire, cette table n'est qu'un repli ciblé.
    _DIMENSION_VALUE_TABLE_ID = 349
    _DIMENSION_VALUE_CODE_FIELD_NO = 2

    # 2. Lazy load via AL tableValues
    if ref_field_id > 0:
        _field_no = ref_field_id
    elif ref_table_id == _DIMENSION_VALUE_TABLE_ID:
        _field_no = _DIMENSION_VALUE_CODE_FIELD_NO
    else:
        _field_no = 1
    if profile_code and company_id:
        codes, al_error = _fetch_via_al_extension(
            profile_code, company_id, ref_table_id, _field_no
        )
        if codes:
            _store_reference_cache(profile_code, company_id, cache_key, codes)
            return codes, True
        elif not al_error:
            source_reachable = True

    # 3. Fallback BC API v2.0
    if entity_info and profile_code and company_id:
        try:
            codes = _fetch_codes_from_bc_api(
                profile_code, company_id, ref_table_id, entity_info
            )
            if codes:
                _store_reference_cache(profile_code, company_id, cache_key, codes)
                return codes, True
            else:
                source_reachable = True
        except Exception:
            pass

    if source_reachable:
        # Table interrogée avec succès mais réellement vide côté BC (société de test
        # non peuplée, par ex.) → found=True avec 0 codes valides. Le validateur
        # traitera alors toute valeur non vide dans ce champ comme une anomalie,
        # exactement comme le ferait BC nativement sur une relation vers table vide.
        _store_reference_cache(profile_code, company_id, cache_key, set())
        return set(), True

    return set(), False

def _fetch_via_al_extension(
    profile_code: str,
    company_id:   str,
    table_id:     int,
    field_no:     int,
) -> tuple[set[str], str | None]:
    """Fetch via endpoint générique AL tableValues. Retourne (values, error_msg)."""
    try:
        from app.db.profiles_db import get_profile_by_code
        from app.core.bc_api import get_access_token, get_table_values

        p = get_profile_by_code(profile_code)
        if not p:
            return set(), "profil introuvable"

        tid = p.get("bc_tenant_id",    "").strip()
        cid = p.get("bc_client_id",    "").strip()
        cs  = p.get("bc_client_secret","").strip()
        env = p.get("bc_environment",  "").strip()
        if not all([tid, cid, cs, env, company_id]):
            return set(), "credentials incomplets"

        token  = get_access_token(tid, cid, cs)
        result = get_table_values(tid, env, company_id, table_id, field_no, token)
        return result, None
    except Exception as e:
        return set(), f"{type(e).__name__} — {str(e)}"


def _fetch_codes_from_bc_api(
    profile_code: str,
    company_id:   str,
    ref_table_id: int,
    entity_info:  tuple[str, str],
) -> set[str]:
    """
    Fetch via BC API v2.0 standard — fallback tables connues.
    Ne catch plus les exceptions ici : elles remontent à l'appelant
    (get_reference_values_by_table_id) qui doit distinguer un échec
    technique réel d'un résultat vide légitime.
    """
    from app.db.profiles_db import get_profile_by_code
    from app.core.bc_api import get_access_token
    import requests as _req

    p = get_profile_by_code(profile_code)
    if not p:
        raise ValueError("profil introuvable")

    tid = p.get("bc_tenant_id",    "").strip()
    cid = p.get("bc_client_id",    "").strip()
    cs  = p.get("bc_client_secret","").strip()
    env = p.get("bc_environment",  "").strip()
    if not all([tid, cid, cs, env, company_id]):
        raise ValueError("credentials incomplets")

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

# ── Repli persisté pour check_gl_account_prerequisites (24/07/2026) ────────
# Réutilise le cache générique existant (bc_metadata_cache / save_reference_data
# / get_cached_metadata) — pas de nouvelle table Supabase. Nécessaire car un
# fichier 92/93/94 testé seul (workflow sessions mère/fille de Rami) ne
# contient pas l'onglet GL Account, donc le contrôle croisé
# (correction_classifier.check_gl_account_prerequisites) n'a rien à comparer
# sans cette image persistée du dernier fichier qui contenait réellement la
# table 15. Confirmé nécessaire par test réel du 24/07/2026 : BC a rejeté
# l'import 92 (compte 77110001) alors que l'outil affichait "fichier correct"
# faute de cette référence.

GL_ACCOUNT_POSTING_FIELDS_ENTITY = "gl_account_posting_fields"


def persist_gl_account_posting_fields(
    profile_code: str,
    company_id:   str,
    gl_accounts:  dict,
) -> tuple[bool, str]:
    """
    Persiste, pour chaque compte GL Account présent dans le dernier fichier
    analysé contenant l'onglet 15, l'état de ses champs Groupe compta.
    marché/produit. Écrasé à chaque nouvelle analyse (reflète toujours le
    dernier état connu, pas un instantané figé dans le temps) — cohérent
    avec la décision actée le 23/07 : le socle est figé dans sa structure,
    mais ses données peuvent être modifiées/complétées dans le temps.

    gl_accounts : {"<N° compte>": {"Groupe compta. marché": "...",
                                    "Groupe compta. produit": "..."}, ...}
    """
    data = [{"N°": acc_no, **fields} for acc_no, fields in gl_accounts.items()]
    return save_reference_data(
        profile_code=profile_code,
        company_id=company_id,
        entity_name=GL_ACCOUNT_POSTING_FIELDS_ENTITY,
        label="GL Account — Groupe compta. marché/produit",
        data=data,
        record_count=len(data),
    )


def get_gl_account_posting_fields(
    profile_code: str,
    company_id:   str,
) -> dict:
    """
    Relit le dernier état persisté par persist_gl_account_posting_fields().
    Retourne {} si rien n'a jamais été persisté pour cette société (aucun
    fichier avec l'onglet GL Account n'a encore été analysé pour ce
    profile_code/company_id) — l'appelant doit alors traiter ça comme
    "rien à vérifier", pas comme une erreur.
    """
    row = get_cached_metadata(profile_code, company_id, GL_ACCOUNT_POSTING_FIELDS_ENTITY)
    if not row:
        return {}
    fields = row.get("fields") or []
    return {
        str(r.get("N°", "")).strip(): {k: v for k, v in r.items() if k != "N°"}
        for r in fields if r.get("N°")
    }

TABLE_CAPTIONS_ENTITY = "table_captions"


def get_table_caption_cached(
    profile_code: str,
    company_id:   str,
    table_id:     str,
) -> str | None:
    """
    AJOUTÉ (07/08/2026) — résolution dynamique du libellé BC d'une table,
    avec cache Supabase (TTL 30 jours : un libellé de table BC ne change
    quasiment jamais, pas besoin du TTL 24h générique). Un seul enregistrement
    Supabase par (profile_code, company_id) regroupe TOUTES les tables déjà
    résolues (dict table_id -> caption), pour éviter de multiplier les lignes
    de cache table par table.

    Appelée par correction_classifier.build_prerequisites_report() en
    source prioritaire, AVANT le repli sur le dictionnaire statique
    master_data_config.REFERENCE_TABLES. Retourne None si la résolution live
    échoue (BC injoignable, table inexistante, profil BC mal configuré) —
    l'appelant retombe alors sur le dictionnaire statique, jamais d'erreur
    remontée ici.
    """
    table_id = str(table_id)

    cached_row = get_cached_metadata(profile_code, company_id, TABLE_CAPTIONS_ENTITY)
    cached_captions = {}
    if cached_row:
        raw = cached_row.get("fields")
        if isinstance(raw, dict):
            cached_captions = raw
        elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
            # save_metadata() sérialise toujours en JSON ; si jamais stocké
            # comme liste de paires par un appelant futur, on gère aussi ce cas.
            cached_captions = {r.get("table_id"): r.get("caption") for r in raw if r.get("table_id")}

    if table_id in cached_captions and is_cache_valid(
        profile_code, company_id, TABLE_CAPTIONS_ENTITY, hours=24 * 30
    ):
        return cached_captions[table_id] or None

    try:
        from app.db.profiles_db import get_profile_by_code
        from app.core.bc_api import get_access_token, get_table_caption

        profile = get_profile_by_code(profile_code)
        tenant_id     = (profile.get("bc_tenant_id") or "").strip()
        client_id     = (profile.get("bc_client_id") or "").strip()
        client_secret = (profile.get("bc_client_secret") or "").strip()
        environment   = (profile.get("bc_environment") or "").strip()
        if not (tenant_id and client_id and client_secret and environment and company_id):
            return None

        token = get_access_token(tenant_id, client_id, client_secret)
        caption = get_table_caption(tenant_id, environment, company_id, int(table_id), token)
        if not caption:
            return None

        cached_captions[table_id] = caption
        save_metadata(profile_code, company_id, TABLE_CAPTIONS_ENTITY, "reference", cached_captions)
        return caption
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# AJOUTÉ (20/08/2026) — MÉMOIRE INTER-SESSIONS (architecture proposée
# Rami/Claude, 20/08, cf. PV démo du 19/08). Principe : une valeur créée
# dans le fichier d'une session, même si cette session n'a pas encore été
# intégrée dans BC, doit être reconnue comme "connue" par les AUTRES
# sessions de la même société — pas seulement l'état BC en direct.
#
# ⚠️ Nécessite la création d'une table Supabase avant déploiement :
#    CREATE TABLE session_pending_codes (
#        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
#        session_id    text NOT NULL,
#        profile_code  text NOT NULL,
#        company_id    text NOT NULL,
#        table_id      integer NOT NULL,
#        code          text NOT NULL,
#        created_at    timestamptz NOT NULL DEFAULT now(),
#        UNIQUE (session_id, table_id, code)
#    );
#    CREATE INDEX idx_session_pending_codes_lookup
#        ON session_pending_codes (profile_code, company_id, table_id);
#
# Design volontairement séparé du cache de référence BC (bc_metadata_cache)
# ci-dessus, plutôt que fusionné dedans : sémantique différente (données
# BC confirmées vs codes en attente d'intégration, jamais la même garantie
# — voir distinction visuelle prévue côté UI), et durée de vie différente
# (une entrée ici doit pouvoir être retirée quand une session est
# supprimée/régénérée, sans toucher au cache BC réel).
# ══════════════════════════════════════════════════════════════════════════

def save_pending_codes(
    session_id:   str,
    profile_code: str,
    company_id:   str,
    codes_by_table: dict[int, set[str]],
) -> tuple[bool, str]:
    """
    Remplace intégralement les codes en attente d'UNE session (delete puis
    insert) — pas un ajout incrémental. Appelée à chaque régénération du
    fichier corrigé d'une session : si une correction change entre-temps,
    les anciens codes de cette session ne doivent pas persister à tort.
    """
    try:
        client = get_supabase_client()
        client.table("session_pending_codes").delete().eq("session_id", session_id).execute()
        rows = [
            {
                "session_id":   session_id,
                "profile_code": profile_code,
                "company_id":   company_id,
                "table_id":     table_id,
                "code":         code,
            }
            for table_id, codes in codes_by_table.items()
            for code in codes
        ]
        if rows:
            # Supabase/PostgREST limite raisonnablement la taille d'un
            # insert — découpe en lots de 500 lignes par sécurité (un
            # fichier MDD-Stock réel peut dépasser 700 codes sur une seule
            # table, voir extract_key_values_by_table).
            for i in range(0, len(rows), 500):
                client.table("session_pending_codes").insert(rows[i:i + 500]).execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_pending_codes(
    profile_code: str,
    company_id:   str,
    table_id:     int,
    exclude_session_id: str | None = None,
) -> set[str]:
    """
    Codes en attente d'intégration BC pour une table, toutes sessions de la
    société confondues (hors une session à exclure explicitement — utile
    pour ne pas se compter soi-même en train de revalider son propre
    fichier). Best-effort : une erreur retourne un ensemble vide plutôt que
    de faire planter le contrôle qualité qui l'appelle (même principe que
    get_reference_values_by_table_id — la mémoire inter-sessions est un
    complément, jamais un point de défaillance bloquant).
    """
    try:
        client = get_supabase_client()
        query = (
            client.table("session_pending_codes")
            .select("code")
            .eq("profile_code", profile_code)
            .eq("company_id",   company_id)
            .eq("table_id",     table_id)
        )
        if exclude_session_id:
            query = query.neq("session_id", exclude_session_id)
        res = query.execute()
        return {row["code"] for row in (res.data or [])}
    except Exception:
        return set()


def delete_pending_codes_for_session(session_id: str) -> tuple[bool, str]:
    """Nettoyage explicite — à appeler quand une session est supprimée, ou
    marquée « intégrée » si on décide de ne plus la compter comme en
    attente (choix laissé à l'appelant, cette fonction ne fait qu'exécuter
    le retrait demandé)."""
    try:
        client = get_supabase_client()
        client.table("session_pending_codes").delete().eq("session_id", session_id).execute()
        return True, ""
    except Exception as e:
        return False, str(e)