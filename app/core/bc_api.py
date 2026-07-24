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
import requests
from urllib.parse import quote


# ── Authentification ──────────────────────────────────────────────────────────

def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """
    Obtient un Bearer token OAuth2 Azure AD pour l'API BC.
    Raises requests.HTTPError si l'auth échoue.
    """
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
    return resp.json()["access_token"]


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
    field_name:  str,
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

    field_name : le NOM AL interne du champ (ex. "Gen. Bus. Posting
    Group"), PAS son numéro — résolu dynamiquement côté AL par réflexion
    (RecRef.FieldIndex, comparaison sur FldRef.Name). Ce nom est stable
    dans toutes les localisations BC, contrairement au numéro de champ qui
    peut varier — aucun numéro à connaître ou à coder en dur ici.

    Un enregistrement absent du résultat = champ vide pour cet
    enregistrement (mêmes conventions que tableValues).

    Raises requests.HTTPError si l'endpoint n'est pas encore publié (404),
    si field_name ne correspond à aucun champ de la table (page AL renvoie
    alors un résultat vide, pas une erreur — donc un dict vide ici est
    ambigu entre "rien de rempli" et "nom de champ introuvable" ; à
    diagnostiquer via le champ fieldNo=0 en retour si besoin), ou toute
    autre erreur BC — l'appelant doit capturer et retomber sur le repli
    persisté (app.db.metadata_db.get_gl_account_posting_fields) tant que
    l'extension AL n'a pas été republiée avec cette page.
    """
    # BUG CORRIGÉ (24/07) : field_name contient des espaces ("Gen. Bus.
    # Posting Group") — insérés tels quels dans l'URL, ils la rendent
    # invalide/fragile (un espace brut n'est pas un caractère URL valide).
    # C'est très probablement ce qui faisait échouer silencieusement le
    # filtre côté BC (résultat vide, pas d'erreur HTTP). quote() encode
    # l'espace en %20 — mais on garde l'apostrophe simple non encodée
    # (nécessaire à la syntaxe OData `eq '...'`) via safe="'".
    encoded_field_name = quote(field_name, safe="'")
    url = (
        f"{_qc_base(tenant_id, environment, company_id)}/recordValues"
        f"?$filter=tableId eq {table_id} and fieldNameFilter eq '{encoded_field_name}'"
    )
    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    values = resp.json().get("value", [])
    return {
        str(v.get("recordKey", "")).strip(): str(v.get("value", "")).strip()
        for v in values if v.get("recordKey")
    }


def get_gl_account_fields_live(
    tenant_id:   str,
    environment: str,
    company_id:  str,
    token:       str,
) -> dict:
    """
    Interroge en direct (via get_record_values_qc, table 15, par NOM de
    champ — jamais de numéro codé en dur) l'état RÉEL des champs Groupe
    compta. marché/produit de chaque compte GL — plus fiable qu'un repli
    en cache car jamais périmé (voir discussion du 24/07/2026 : un cache
    reste correct tant que personne ne modifie le plan comptable entre
    deux analyses, ce qui n'est pas garanti).

    Retourne le même format que
    app.db.metadata_db.get_gl_account_posting_fields() — remplacement
    direct côté appelant : {"<N° compte>": {"Groupe compta. marché": "...",
    "Groupe compta. produit": "..."}, ...}
    """
    bus = get_record_values_qc(
        tenant_id, environment, company_id, 15, "Gen. Bus. Posting Group", token,
    )
    prod = get_record_values_qc(
        tenant_id, environment, company_id, 15, "Gen. Prod. Posting Group", token,
    )
    accounts = set(bus) | set(prod)
    return {
        acc: {
            "Groupe compta. marché":  bus.get(acc, ""),
            "Groupe compta. produit": prod.get(acc, ""),
        }
        for acc in accounts
    }