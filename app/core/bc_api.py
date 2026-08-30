"""
Client API Business Central.

Auth   : OAuth2 Client Credentials — Azure AD (tenant/client_id/client_secret)
Base   : https://api.businesscentral.dynamics.com/v2.0/{tenant}/{environment}
Packages : /api/microsoft/automation/v2.0/companies({id})/configurationPackages
Scope  : https://api.businesscentral.dynamics.com/.default

Credentials lus depuis la table client_profiles (Supabase) :
    bc_tenant_id, bc_client_id, bc_client_secret,
    bc_environment, bc_company_id, bc_url
"""
import time
import requests
from urllib.parse import quote


# ── Authentification ──────────────────────────────────────────────────────────

# AJOUTÉ (07/08/2026) — cache mémoire process du token OAuth2, keyed par
# (tenant_id, client_id). Corrige un vrai problème de performance : chaque
# vérification de niveau (check_table_filled, résolution de libellé de
# table...) redemandait un token Azure AD FRAIS, un aller-retour réseau
# complet par niveau — jusqu'à 13+ échanges OAuth2 séquentiels pour
# afficher une seule roadmap. Le token BC est valide ~1h (voir
# "expires_in" de la réponse) ; on le réutilise avec une marge de sécurité
# de 60s avant expiration plutôt que de le renouveler à chaque appel.
_TOKEN_CACHE: dict[tuple[str, str], tuple[str, float]] = {}


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """
    Obtient un Bearer token OAuth2 Azure AD pour l'API BC — réutilisé depuis
    le cache mémoire tant qu'il n'est pas expiré (voir _TOKEN_CACHE
    ci-dessus). Raises requests.HTTPError si l'auth échoue.
    """
    cache_key = (tenant_id, client_id)
    cached = _TOKEN_CACHE.get(cache_key)
    if cached is not None:
        token, expires_at = cached
        if time.time() < expires_at:
            return token

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(
        url,
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
            "scope":         "https://api.businesscentral.dynamics.com/.default",
        },
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()
    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _TOKEN_CACHE[cache_key] = (token, time.time() + expires_in - 60)
    return token


def _base_url(tenant_id: str, environment: str) -> str:
    """Construit l'URL de base BC API."""
    return (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}/api/v2.0"
    )


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


# ── Configuration Packages ────────────────────────────────────────────────────

def get_companies(tenant_id: str, environment: str, token: str) -> list[dict]:
    """
    Retourne la liste des sociétés BC disponibles.
    Champs utiles : id, name, displayName.
    """
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}/api/v2.0/companies"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    return resp.json().get("value", [])


def diagnose_standard_api_account(
    tenant_id: str, environment: str, company_id: str, account_no: str, token: str
) -> dict:
    """
    AJOUTÉ (04/08/2026) — diagnostic ponctuel, pas un helper métier réutilisé
    ailleurs. Interroge l'API BC STANDARD (/api/v2.0/companies({id})/accounts),
    PAS l'extension custom talan/qctools, pour isoler si un écart constaté
    (ex. TEST-GL-VALIDATION retournant un plan comptable différent de celui
    vu dans le client web BC) vient de la plateforme (délai de réplication
    API tier après restauration d'environnement) ou spécifiquement de
    l'extension AL. Si ce endpoint standard voit aussi le mauvais compte
    (ou rien), le souci est côté plateforme, pas côté code talan/qctools.

    Retourne {"found": bool, "raw": <réponse JSON complète>}.
    """
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}/api/v2.0"
        f"/companies({company_id})/accounts"
        f"?$filter=number eq '{account_no}'"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {"found": bool(data.get("value")), "raw": data}


def resolve_company_id(profile: dict, token: str) -> str:
    """
    Retourne le company_id à utiliser :
      1. Si bc_company_id est renseigné → l'utiliser directement
      2. Sinon → chercher par bc_company_name dans la liste des sociétés BC
      3. Si une seule société → la prendre automatiquement

    Raises:
        Exception si aucune société ne correspond.
    """
    tenant_id   = profile.get("bc_tenant_id", "").strip()
    environment = profile.get("bc_environment", "Production").strip()
    company_id  = profile.get("bc_company_id", "").strip()
    company_name = profile.get("bc_company_name", "").strip()

    # Cas 1 : ID déjà connu
    if company_id:
        return company_id

    # Cas 2 & 3 : auto-détection
    companies = get_companies(tenant_id, environment, token)

    if not companies:
        raise Exception(
            "Aucune société BC trouvée dans cet environnement. "
            "Vérifiez bc_environment dans le profil."
        )

    # Une seule société → la prendre
    if len(companies) == 1:
        return companies[0]["id"]

    # Plusieurs sociétés → chercher par nom
    if company_name:
        for c in companies:
            if (c.get("name", "").lower() == company_name.lower()
                    or c.get("displayName", "").lower() == company_name.lower()):
                return c["id"]

    # Ambiguïté : lister les sociétés disponibles pour aider
    names = ", ".join(
        f"'{c.get('displayName') or c.get('name', '?')}'"
        for c in companies
    )
    raise Exception(
        f"Plusieurs sociétés disponibles : {names}. "
        "Renseignez bc_company_name (ou bc_company_id) dans le profil client."
    )


def get_config_packages(profile: dict) -> tuple[list[dict], str]:
    """
    Charge la liste des Configuration Packages depuis BC.

    Args:
        profile : ligne client_profiles avec les champs BC
                  (bc_tenant_id, bc_client_id, bc_client_secret,
                   bc_environment, bc_company_id OU bc_company_name)

    Returns:
        (packages, company_name) — packages = liste de dicts BC :
            code, packageName, processingOrder,
            numberOfTables, numberOfRecords, numberOfErrors

    Raises:
        Exception avec message lisible si auth ou appel API échoue.
    """
    tenant_id     = profile.get("bc_tenant_id", "").strip()
    client_id     = profile.get("bc_client_id", "").strip()
    client_secret = profile.get("bc_client_secret", "").strip()
    environment   = profile.get("bc_environment", "Production").strip()

    if not all([tenant_id, client_id, client_secret, environment]):
        raise ValueError(
            "Credentials BC incomplets dans le profil client. "
            "Vérifiez : bc_tenant_id, bc_client_id, bc_client_secret, bc_environment."
        )

    # Auth
    try:
        token = get_access_token(tenant_id, client_id, client_secret)
    except requests.HTTPError as e:
        raise Exception(
            f"Échec authentification Azure AD ({e.response.status_code}) "
            "— vérifiez bc_client_id et bc_client_secret."
        ) from e

    # Résolution company_id (auto si non renseigné)
    company_id = resolve_company_id(profile, token)

    # Récupérer le displayName pour l'affichage
    companies = get_companies(tenant_id, environment, token)
    company_display = next(
        (c.get("displayName") or c.get("name", "") for c in companies if c["id"] == company_id),
        profile.get("bc_company_name", company_id),
    )

    # Appel Configuration Packages (Automation API)
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}"
        f"/api/microsoft/automation/v2.0"
        f"/companies({company_id})/configurationPackages"
    )

    try:
        resp = requests.get(url, headers=_headers(token), timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = e.response.status_code
        if status == 404:
            raise Exception(
                f"Endpoint introuvable (404).\n"
                f"URL testée : {url}\n"
                "Vérifiez bc_environment dans le profil."
            ) from e
        if status == 401:
            raise Exception(
                "Non autorisé (401) — l'app Azure AD doit avoir la permission "
                "Automation.ReadWrite.All sur Business Central."
            ) from e
        if status == 403:
            raise Exception(
                "Accès refusé (403) — l'utilisateur BC associé doit avoir "
                "le rôle D365 AUTOMATION."
            ) from e
        raise Exception(f"Erreur BC API {status} : {e.response.text[:300]}") from e

    return resp.json().get("value", []), company_display


def get_config_packages_for_company(
    tenant_id: str,
    environment: str,
    company_id: str,
    token: str,
) -> list[dict]:
    """
    Charge les packages de configuration pour une société BC donnée.
    Utilisé quand le company_id est déjà connu (sélection depuis la liste des sociétés).
    """
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}"
        f"/api/microsoft/automation/v2.0"
        f"/companies({company_id})/configurationPackages"
    )
    try:
        resp = requests.get(url, headers=_headers(token), timeout=30)
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = e.response.status_code
        if status == 401:
            raise Exception("Non autorisé (401) — permission Automation.ReadWrite.All requise.")
        if status == 403:
            raise Exception("Accès refusé (403) — rôle D365 AUTOMATION requis sur l'utilisateur BC.")
        raise Exception(f"Erreur BC API {status} : {e.response.text[:300]}")
    return resp.json().get("value", [])


def get_package_tables(
    tenant_id: str,
    environment: str,
    company_id: str,
    package_id: str,
    token: str,
) -> list[dict]:
    """
    Retourne les tables d'un package de configuration.
    Champs utiles : tableId, tableName, processingOrder, skipTableTriggers,
                    deleteBeforeProcessing.
    """
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}"
        f"/api/microsoft/automation/v2.0"
        f"/companies({company_id})/configurationPackages({package_id})"
        f"/configurationPackageTables"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def get_package_fields(
    tenant_id: str,
    environment: str,
    company_id: str,
    package_id: str,
    table_no: int,
    token: str,
) -> list[dict]:
    """
    Retourne les champs inclus dans une table de package.
    Champs utiles : fieldNo, fieldName, includeField, validateField.
    """
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}"
        f"/api/microsoft/automation/v2.0"
        f"/companies({company_id})/configurationPackages({package_id})"
        f"/configurationPackageTables({table_no})/configurationPackageFields"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return [f for f in resp.json().get("value", []) if f.get("includeField", True)]


def get_field_definitions(
    tenant_id: str,
    environment: str,
    company_id: str,
    table_no: int,
    token: str,
) -> list[dict]:
    """
    Tente de récupérer les définitions de champs (type, libellé, obligatoire).
    Endpoint : /tableDefinitions/{tableNo}/fieldDefinitions (pas garanti en v2.0).
    Retourne [] si l'endpoint n'existe pas — l'appelant doit gérer le fallback.
    """
    url = (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}/api/v2.0"
        f"/companies({company_id})/tableDefinitions({table_no})/fieldDefinitions"
    )
    try:
        resp = requests.get(url, headers=_headers(token), timeout=15)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("value", [])
    except Exception:
        return []




# ══════════════════════════════════════════════════════════════════════════════
# EXTENSION TALAN QC TOOLS — endpoints custom
# Publisher: talan · Group: qctools · Version: v1.0
# ══════════════════════════════════════════════════════════════════════════════

def _qc_base(tenant_id: str, environment: str, company_id: str) -> str:
    return (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}"
        f"/api/talan/qctools/v1.0"
        f"/companies({company_id})"
    )


def get_table_caption(
    tenant_id: str, environment: str, company_id: str, table_id: int, token: str
) -> str | None:
    """
    AJOUTÉ (07/08/2026) — résolution dynamique du libellé BC d'une table via
    la nouvelle page 50107 "Talan QC Table Caption API" (RecRef.Caption,
    français forcé côté AL). Remplace côté Python le dictionnaire statique
    master_data_config.REFERENCE_TABLES comme source prioritaire —
    voir metadata_db.get_table_caption_cached() pour la version avec cache
    Supabase + résolution auth/profil, utilisée par
    correction_classifier.build_prerequisites_report().

    Retourne None si la table n'existe pas / n'est pas accessible, ou en cas
    d'erreur réseau — l'appelant doit alors retomber sur le dictionnaire
    statique.
    """
    url = f"{_qc_base(tenant_id, environment, company_id)}/tableCaptions?$filter=tableId eq {int(table_id)}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    values = resp.json().get("value", [])
    if not values:
        return None
    caption = values[0].get("tableCaption", "")
    return caption or None


def get_packages_qc(
    tenant_id: str,
    environment: str,
    company_id: str,
    token: str,
    visible_only: bool = False,
) -> list[dict]:
    """
    Retourne les packages depuis l'extension Talan QC Tools.
    visible_only=True → $filter=qcVisibleClient eq true (vue client).
    Champs : code, packageName, qcVisibleClient.
    """
    url = f"{_qc_base(tenant_id, environment, company_id)}/packages"
    if visible_only:
        url += "?$filter=qcVisibleClient eq true"
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def set_package_visibility_bc(
    tenant_id: str,
    environment: str,
    company_id: str,
    package_code: str,
    visible: bool,
    token: str,
) -> None:
    """
    Met à jour le flag qcVisibleClient sur le package BC via PATCH.
    If-Match: * évite de gérer l'ETag manuellement.
    """
    url = f"{_qc_base(tenant_id, environment, company_id)}/packages('{package_code}')"
    resp = requests.patch(
        url,
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/json",
            "If-Match":       "*",
        },
        json={"qcVisibleClient": visible},
        timeout=15,
    )
    resp.raise_for_status()


def get_package_tables_qc(
    tenant_id: str,
    environment: str,
    company_id: str,
    package_code: str,
    token: str,
) -> list[dict]:
    """
    Retourne les tables d'un package triées par processingOrder.
    Champs : packageCode, tableId, tableName, processingOrder,
             skipTableTriggers, deleteBeforeProcessing.
    """
    url = (
        f"{_qc_base(tenant_id, environment, company_id)}/packageTables"
        f"?$filter=packageCode eq '{package_code}'"
        f"&$orderby=processingOrder asc"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def get_package_fields_qc(
    tenant_id: str,
    environment: str,
    company_id: str,
    package_code: str,
    table_id: int,
    token: str,
) -> list[dict]:
    """
    Retourne les champs inclus (includeField=true) d'une table de package.
    Champs : packageCode, tableId, fieldId, fieldName,
             includeField, validateField.
    """
    url = (
        f"{_qc_base(tenant_id, environment, company_id)}/packageFields"
        f"?$filter=packageCode eq '{package_code}'"
        f" and tableId eq {table_id}"
        f" and includeField eq true"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])
def get_table_values(
    tenant_id:   str,
    environment: str,
    company_id:  str,
    table_id:    int,
    field_no:    int,
    token:       str,
) -> set[str]:
    """
    Retourne l'ensemble des codes valides pour (table_id, field_no)
    via l'endpoint générique AL /tableValues (page 50106).
    Champ BC : 'code' (Rec."Code Value").
    Raises requests.HTTPError si l'appel échoue — laisse remonter
    l'erreur réelle pour que l'appelant puisse la logger.
    """
    url = (
        f"{_qc_base(tenant_id, environment, company_id)}/tableValues"
        f"?$filter=tableId eq {table_id} and fieldNo eq {field_no}"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    values = resp.json().get("value", [])
    return set(
        str(v.get("code", "")).strip()
        for v in values if v.get("code")
    )

def build_tables_data_for_export(
    tenant_id: str,
    environment: str,
    company_id: str,
    package_code: str,
    token: str,
) -> list[dict]:
    """
    Construit la structure complète pour generate_package_template()
    en lisant tables + champs depuis l'extension Talan QC Tools.

    Enrichit avec FIELD_DEFS (type, obligatoire, description)
    pour les tables BC standard connues.

    Returns:
        [{table_id, table_name, fields: [{field_no, field_name,
          field_caption, data_type, required, is_custom,
          validate_field, example, description}]}]
    """
    pkg_tables = get_package_tables_qc(
        tenant_id, environment, company_id, package_code, token
    )

    try:
        from app.core.validator_axe_a import FIELD_DEFS
    except ImportError:
        FIELD_DEFS = {}

    result = []
    for pt in pkg_tables:
        table_id   = pt.get("tableId", 0)
        table_name = pt.get("tableName", str(table_id))

        try:
            pkg_fields = get_package_fields_qc(
                tenant_id, environment, company_id, package_code, table_id, token
            )
        except Exception:
            pkg_fields = []

        if not pkg_fields:
            continue

        # Enrichissement depuis FIELD_DEFS (type, requis, description)
        fd_table = FIELD_DEFS.get(str(table_id), {})

        fields = []
        for pf in pkg_fields:
            fname    = pf.get("fieldName", "")
            field_id = pf.get("fieldId", 0)
            fd       = fd_table.get(fname, {})
            dtype    = fd.get("type", "Text")
            req      = fd.get("req", False)

            fields.append({
                "field_no":       field_id,
                "field_name":     fname,
                "field_caption":  fname,
                "data_type":      dtype,
                "required":       req,
                "is_custom":      field_id >= 50000,
                "validate_field": pf.get("validateField", False),
                "example":        "",
                "description": (
                    f"Type : {dtype}"
                    + (f" · Max : {fd['max']} car." if fd.get("max") else "")
                    + (" · OBLIGATOIRE" if req else "")
                ) if fd else "",
            })

        result.append({
            "table_id":   table_id,
            "table_name": table_name,
            "fields":     fields,
        })

    return result


def get_record_values_qc(
    tenant_id:   str,
    environment: str,
    company_id:  str,
    table_id:    int,
    field_no:    int,
    token:       str,
) -> dict[str, str]:
    """
    Retourne {"<clé primaire>": "<valeur du champ>"} pour CHAQUE
    enregistrement d'une table BC — via l'endpoint générique AL
    /recordValues (page 50104, extension talan/qctools, voir
    PageAPI.RecordValues.al dans HaifaBenM/bc-QC-Tool).

    Contrairement à get_table_values() (page 50106, tableValues) qui ne
    retourne que l'ensemble DÉDUPLIQUÉ des valeurs présentes dans un champ
    sur toute la table, celle-ci retourne une ligne par enregistrement —
    permet de savoir si UN compte GL précis a bien tel champ rempli, pas
    seulement si la valeur existe quelque part dans la table.

    BUG AL CONFIRMÉ (24/07/2026) : le filtre fieldNameFilter (résolution
    par nom de champ, ex. "Gen. Bus. Posting Group") retourne
    systématiquement 0 résultat, confirmé en URL brute (donc pas un bug
    Python) — la comparaison FldRef.Name côté AL ne fonctionne pas comme
    attendu, cause exacte non identifiée. En attendant un correctif AL,
    cette fonction n'accepte plus que field_no (numéro), dont le
    fonctionnement est confirmé fiable sur un test réel. Pour rester
    dynamique sans coder de numéro en dur côté appelant, voir
    resolve_field_no_via_package() ci-dessous qui résout le numéro via
    l'endpoint packageFields déjà existant et fonctionnel.

    Un enregistrement absent du résultat = champ vide pour cet
    enregistrement (mêmes conventions que tableValues).

    Raises requests.HTTPError si l'endpoint n'est pas encore publié (404)
    ou toute autre erreur BC — l'appelant doit capturer et retomber sur le
    repli persisté (app.db.metadata_db.get_gl_account_posting_fields) tant
    que l'extension AL n'a pas été republiée avec cette page.
    """
    url = (
        f"{_qc_base(tenant_id, environment, company_id)}/recordValues"
        f"?$filter=tableId eq {table_id} and fieldNo eq {field_no}"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    values = resp.json().get("value", [])
    return {
        str(v.get("recordKey", "")).strip(): str(v.get("value", "")).strip()
        for v in values if v.get("recordKey")
    }


def resolve_field_no_via_package(
    tenant_id:   str,
    environment: str,
    company_id:  str,
    table_id:    int,
    field_name:  str,
    token:       str,
) -> int | None:
    """
    Résout dynamiquement le numéro d'un champ (ex. "Gen. Bus. Posting
    Group" sur la table 15) en cherchant dans tous les packages BC de la
    société un package qui inclut cette table, via l'endpoint packageFields
    déjà existant et fonctionnel (get_package_fields_qc) — aucun numéro
    codé en dur, contrairement à une constante Python (objection légitime
    de Rami le 24/07/2026), et sans dépendre du filtre fieldNameFilter de
    recordValues, actuellement buggé côté AL (voir get_record_values_qc).

    Retourne None si aucun package ne contient ce champ pour cette table —
    l'appelant doit alors traiter ça comme "impossible à résoudre pour
    l'instant", pas comme une erreur bloquante.
    """
    packages = get_packages_qc(tenant_id, environment, company_id, token, visible_only=False)
    for pkg in packages:
        package_code = pkg.get("code", "")
        if not package_code:
            continue
        try:
            fields = get_package_fields_qc(tenant_id, environment, company_id, package_code, table_id, token)
        except Exception:
            continue
        for f in fields:
            if f.get("fieldName", "").strip() == field_name:
                try:
                    return int(f.get("fieldId"))
                except (TypeError, ValueError):
                    continue
    return None


def get_gl_account_fields_live(
    tenant_id:   str,
    environment: str,
    company_id:  str,
    token:       str,
) -> dict:
    """
    Interroge en direct l'état RÉEL des champs Groupe compta. marché/
    produit de chaque compte GL — plus fiable qu'un repli en cache car
    jamais périmé (voir discussion du 24/07/2026 : un cache reste correct
    tant que personne ne modifie le plan comptable entre deux analyses, ce
    qui n'est pas garanti).

    Résout les numéros de champ dynamiquement via
    resolve_field_no_via_package() (packageFields, déjà fonctionnel) au
    lieu de fieldNameFilter (recordValues), actuellement buggé côté AL —
    confirmé le 24/07/2026 par un test réel isolant le problème (fieldNo=1
    en brut fonctionne, fieldNameFilter='No.' en brut retourne 0 dans les
    deux cas, Python et URL directe). Toujours aucun numéro codé en dur :
    la résolution se refait à chaque appel.

    BUG CORRIGÉ précédemment : get_record_values_qc (comme tableValues) ne
    matérialise QUE les valeurs non vides — un compte dont le champ est
    vide n'apparaissait donc jamais dans bus/prod. Correctif : on récupère
    d'abord l'univers de TOUS les comptes existants (champ "No.", résolu
    dynamiquement lui aussi), puis on construit un dict DENSE où chaque
    compte a une entrée, vide ou non.

    Retourne le même format que
    app.db.metadata_db.get_gl_account_posting_fields(), ENRICHI (04/08/2026)
    d'une clé "Gen. Posting Type" par compte quand ce champ a pu être
    résolu — utilisée par
    app.core.correction_classifier._gl_account_requires_gen_prod_group()
    pour déterminer dynamiquement si Groupe compta. produit est requis,
    au lieu du mapping statique GL_ACCOUNT_FIELD_REQUIREMENTS :
    {"<N° compte>": {"Groupe compta. marché": "...",
    "Groupe compta. produit": "...", "Gen. Posting Type": "..."}, ...}
    La clé "Gen. Posting Type" est ABSENTE (pas vide) pour tous les
    comptes si ce champ n'a pu être résolu dans aucun package BC — voir
    _gen_prod_no ci-dessous. L'appelant (check_gl_account_prerequisites)
    traite déjà ce cas comme "indisponible -> repli sur le mapping
    statique", pas comme "vide -> rien à exiger" (distinction volontaire,
    ne pas fusionner ces deux cas).

    Raises ValueError si un des 3 champs HISTORIQUES (No., Gen. Bus./Prod.
    Posting Group) n'a pu être résolu — comportement inchangé. La
    résolution de "Gen. Posting Type" est volontairement NON bloquante :
    un échec dessus ne doit pas casser le repli live existant, déjà
    fiable sur les 2 champs historiques.

    À VÉRIFIER CÔTÉ BC avant de faire confiance à ce nouveau champ : il
    doit figurer dans la sélection de champs d'AU MOINS un Config Package
    existant pour la table 15 (Compte général), sinon
    resolve_field_no_via_package() retourne None silencieusement pour lui
    (pas d'exception) et le repli statique reste utilisé partout — pas de
    régression, mais pas de bénéfice tant que ce n'est pas confirmé.
    """
    no_field_no  = resolve_field_no_via_package(tenant_id, environment, company_id, 15, "No.", token)
    bus_field_no = resolve_field_no_via_package(tenant_id, environment, company_id, 15, "Gen. Bus. Posting Group", token)
    prod_field_no = resolve_field_no_via_package(tenant_id, environment, company_id, 15, "Gen. Prod. Posting Group", token)

    if no_field_no is None or bus_field_no is None or prod_field_no is None:
        raise ValueError(
            f"Résolution dynamique des champs impossible (No.={no_field_no}, "
            f"Gen. Bus.={bus_field_no}, Gen. Prod.={prod_field_no}) — aucun package "
            f"BC ne contient ces champs pour la table 15 dans cette société."
        )

    universe = get_record_values_qc(tenant_id, environment, company_id, 15, no_field_no, token)
    bus      = get_record_values_qc(tenant_id, environment, company_id, 15, bus_field_no, token)
    prod     = get_record_values_qc(tenant_id, environment, company_id, 15, prod_field_no, token)

    # Résolution NON bloquante du nouveau champ — un échec ici ne doit
    # jamais faire perdre le repli historique (bus/prod), voir docstring.
    gen_posting = {}
    try:
        gen_field_no = resolve_field_no_via_package(
            tenant_id, environment, company_id, 15, "Gen. Posting Type", token
        )
        if gen_field_no is not None:
            gen_posting = get_record_values_qc(
                tenant_id, environment, company_id, 15, gen_field_no, token
            )
    except Exception:
        gen_posting = {}  # Gen. Posting Type indisponible — repli statique côté appelant

    result = {
        acc: {
            "Groupe compta. marché":  bus.get(acc, ""),
            "Groupe compta. produit": prod.get(acc, ""),
        }
        for acc in universe
    }
    if gen_posting:
        for acc in result:
            if acc in gen_posting:
                result[acc]["Gen. Posting Type"] = gen_posting[acc]
    return result

# ── Intégration directe BC — création/import/apply Configuration Package ──────
# AJOUTÉ (27/08/2026) — demande Rami, chantiers post-démo (points 2, 3, 6).
# Réutilise l'API Automation v2.0 déjà en place pour get_config_packages()
# (même URL de base, même style de gestion d'erreurs). Vérifié via la
# documentation officielle Microsoft (learn.microsoft.com) : le flux réel
# est create -> upload file -> import (calcule les erreurs SANS écrire dans
# les vraies tables BC) -> apply (écrit réellement). "Valider" dans
# l'interface BC correspond à l'étape import seule, avant tout apply —
# permet d'obtenir le nombre d'erreurs réel sans engager quoi que ce soit.
#
# ⚠️ NON TESTÉ contre un vrai environnement BC au moment de l'écriture —
# à valider en priorité par Rami avant de construire les écrans dessus,
# en particulier : est-ce qu'un package vide créé par API, une fois le
# fichier Excel déposé, détecte automatiquement les tables/champs comme le
# ferait BC via l'interface manuelle (comportement documenté, jamais
# vérifié ici en conditions réelles).

def _automation_base_url(tenant_id: str, environment: str, company_id: str) -> str:
    return (
        f"https://api.businesscentral.dynamics.com"
        f"/v2.0/{tenant_id}/{environment}"
        f"/api/microsoft/automation/v2.0"
        f"/companies({company_id})"
    )


def create_configuration_package(
    tenant_id: str, environment: str, company_id: str, token: str,
    code: str, package_name: str,
) -> dict:
    """
    Crée un nouveau Configuration Package vide dans BC (POST configurationPackages).
    Retourne le package créé (dict, inclut son "id" GUID interne BC — nécessaire
    pour les appels suivants file/import/apply, DIFFÉRENT du "code" lisible).
    Lève une Exception avec message lisible si le code existe déjà (409) ou
    en cas d'échec d'autorisation, même style que get_config_packages().

    RÉVISÉ (27/08/2026) — bug réel rencontré : BC limite "packageName" à 50
    caractères (Application_StringExceededLength) et "code" à 20 (champ BC
    standard Code[20]) — tronqués défensivement ici, à la source, plutôt
    que de compter sur chaque appelant pour respecter ces limites.
    """
    code         = (code or "")[:20]
    package_name = (package_name or "")[:50]
    url = f"{_automation_base_url(tenant_id, environment, company_id)}/configurationPackages"
    try:
        resp = requests.post(
            url, headers={**_headers(token), "Content-Type": "application/json"},
            json={"code": code, "packageName": package_name}, timeout=30,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = e.response.status_code
        if status == 409:
            raise Exception(f"Un package avec le code « {code} » existe déjà dans BC.") from e
        if status == 401:
            raise Exception("Non autorisé (401) — permission Automation.ReadWrite.All requise.") from e
        if status == 403:
            raise Exception("Accès refusé (403) — rôle D365 AUTOMATION requis sur l'utilisateur BC.") from e
        raise Exception(f"Erreur BC API {status} lors de la création du package : {e.response.text[:300]}") from e
    return resp.json()


def upload_configuration_package_file(
    tenant_id: str, environment: str, company_id: str, token: str,
    package_id: str, package_code: str, file_bytes: bytes,
) -> None:
    """
    Dépose le fichier Excel (contenu binaire) dans un package déjà créé
    (PATCH .../configurationPackages({id})/file('{code}')/content).
    package_id = le GUID interne BC (retourné par create_configuration_package
    ou par un GET existant) ; package_code = le code lisible du package.

    RÉVISÉ (27/08/2026) — même fix que import/apply_configuration_package :
    le corps réel de la réponse BC est maintenant inclus dans le message
    d'erreur (raise_for_status() seul ne le montrait jamais).
    """
    url = (
        f"{_automation_base_url(tenant_id, environment, company_id)}"
        f"/configurationPackages({package_id})/file('{package_code}')/content"
    )
    resp = requests.patch(
        url,
        headers={**_headers(token), "Content-Type": "application/octet-stream", "If-Match": "*"},
        data=file_bytes, timeout=60,
    )
    if not resp.ok:
        raise Exception(f"Erreur BC API {resp.status_code} (dépôt fichier) : {resp.text[:500]}")
    resp.raise_for_status()


def import_configuration_package(
    tenant_id: str, environment: str, company_id: str, token: str, package_id: str,
) -> None:
    """
    Importe le fichier déposé dans le package (POST bound action Microsoft.NAV.import).
    Calcule les erreurs de validation SANS écrire dans les vraies tables BC —
    c'est l'équivalent de "Valider" dans l'interface BC. Réponse 204 sans corps
    si succès.

    RÉVISÉ (27/08/2026) — bug trouvé : raise_for_status() seul ne montre
    jamais le corps de la réponse BC (souvent le détail précis de l'échec en
    JSON), seulement "400 Bad Request for url: ..." — inutile pour
    diagnostiquer. Le corps réel est maintenant inclus dans le message.
    """
    url = (
        f"{_automation_base_url(tenant_id, environment, company_id)}"
        f"/configurationPackages({package_id})/Microsoft.NAV.import"
    )
    resp = requests.post(url, headers=_headers(token), timeout=120)
    if not resp.ok:
        raise Exception(f"Erreur BC API {resp.status_code} (import) : {resp.text[:500]}")


def apply_configuration_package(
    tenant_id: str, environment: str, company_id: str, token: str, package_id: str,
) -> None:
    """
    Applique le package importé (POST bound action Microsoft.NAV.apply) —
    ÉCRIT RÉELLEMENT dans les vraies tables BC, contrairement à import().
    À n'appeler qu'après confirmation explicite de l'utilisateur (action
    irréversible côté BC, comme "Appliquer" dans l'interface).

    RÉVISÉ (27/08/2026) — même fix que import_configuration_package : le
    corps réel de la réponse BC est maintenant inclus dans le message
    d'erreur (raise_for_status() seul ne le montrait jamais).
    """
    url = (
        f"{_automation_base_url(tenant_id, environment, company_id)}"
        f"/configurationPackages({package_id})/Microsoft.NAV.apply"
    )
    resp = requests.post(url, headers=_headers(token), timeout=180)
    if not resp.ok:
        raise Exception(f"Erreur BC API {resp.status_code} (apply) : {resp.text[:500]}")


def get_configuration_package_status(
    tenant_id: str, environment: str, company_id: str, token: str, package_code: str,
) -> dict | None:
    """
    Récupère l'état actuel d'un package par son code lisible (numberOfErrors,
    numberOfTables, numberOfRecords, importStatus, applyStatus, importError,
    applyError) — via $filter sur la liste complète (même endpoint que
    get_config_packages), pas de GET direct par code exposé par cette API.
    Retourne None si aucun package ne correspond à ce code.
    """
    url = (
        f"{_automation_base_url(tenant_id, environment, company_id)}"
        f"/configurationPackages?$filter=code eq '{package_code}'"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    results = resp.json().get("value", [])
    return results[0] if results else None


def run_bc_import_check(
    tenant_id: str, environment: str, company_id: str, token: str,
    package_code: str, package_name: str, file_bytes: bytes,
) -> dict:
    """
    AJOUTÉ (27/08/2026) — orchestration complète pour les points 2/3/6 :
    crée le package s'il n'existe pas déjà (confirmé fonctionnel par Rami
    le 27/08 — BC détecte seul les tables/champs à partir du fichier
    Excel, même en partant d'un package vide), dépose le fichier, importe
    (calcule les erreurs SANS rien écrire dans les vraies tables BC —
    équivalent de "Valider" dans l'interface).

    Ne fait JAMAIS l'étape "apply" (écriture réelle) — volontairement
    séparée, à déclencher explicitement ailleurs après confirmation de
    l'utilisateur.

    Retourne un dict :
        {"success": bool, "package_id": str, "status": dict|None, "error": str}
    "status" est le résultat de get_configuration_package_status (contient
    numberOfErrors, importError, etc.) si l'import a réussi à s'exécuter
    (même si BC y trouve des erreurs de données — ça reste un succès
    technique de l'appel). "error" n'est renseigné qu'en cas d'échec
    technique (auth, réseau, package déjà existant sous un autre état...).
    """
    # RÉVISÉ (27/08/2026) — package_code tronqué UNE FOIS ici, dès l'entrée,
    # pour que le même code (≤20 car.) serve à la fois à create/upload et
    # aux deux relectures de statut (avant et après) — évite tout décalage
    # si l'appelant passe un code trop long (create_configuration_package
    # tronque déjà en interne, mais get_configuration_package_status non).
    package_code = (package_code or "")[:20]
    result = {"success": False, "package_id": "", "status": None, "error": ""}
    try:
        existing = get_configuration_package_status(tenant_id, environment, company_id, token, package_code)
        if existing:
            package_id = existing["id"]
        else:
            created = create_configuration_package(
                tenant_id, environment, company_id, token, package_code, package_name
            )
            package_id = created["id"]

        upload_configuration_package_file(
            tenant_id, environment, company_id, token, package_id, package_code, file_bytes
        )
        import_configuration_package(tenant_id, environment, company_id, token, package_id)

        # RÉVISÉ (27/08/2026) — bug réel rencontré : "Import Status is not
        # completed. You must import the package before you apply it."
        # L'import BC est asynchrone — le POST répond immédiatement (204),
        # mais le traitement réel se termine un peu après. Lire le statut
        # tout de suite après pouvait donc remonter un importStatus encore
        # "InProgress", faisant croire l'import terminé alors qu'il ne
        # l'était pas encore côté BC. Sonde le statut jusqu'à confirmation
        # réelle (importStatus == "Completed"), jusqu'à 20s, avant de
        # considérer l'import comme fini.
        status = None
        for _ in range(10):
            status = get_configuration_package_status(tenant_id, environment, company_id, token, package_code)
            if status and str(status.get("importStatus", "")).lower() == "completed":
                break
            time.sleep(2)

        result["success"]    = True
        result["package_id"] = package_id
        result["status"]     = status
    except requests.HTTPError as e:
        result["error"] = f"Erreur BC API {e.response.status_code} : {e.response.text[:300]}"
    except Exception as e:
        result["error"] = f"{type(e).__name__} : {e}"
    return result