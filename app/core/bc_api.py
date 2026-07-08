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
