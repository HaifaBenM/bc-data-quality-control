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


def build_tables_data_for_export(
    tenant_id: str,
    environment: str,
    company_id: str,
    package: dict,
    token: str,
) -> list[dict]:
    """
    Construit la structure complète pour la génération Excel :
    [{table_id, table_name, fields: [{field_no, field_name, field_caption,
      data_type, required, is_custom, validate_field, example}]}]

    Stratégie :
      1. Charger les tables du package
      2. Pour chaque table : charger les champs inclus
      3. Tenter de récupérer les définitions (type, caption) via fieldDefinitions
      4. Fallback sur field_name si fieldDefinitions non disponible
    """
    package_id = package.get("id", "")
    if not package_id:
        raise ValueError("Package ID manquant.")

    pkg_tables = get_package_tables(tenant_id, environment, company_id, package_id, token)
    result = []

    for pt in pkg_tables:
        table_no   = pt.get("tableId") or pt.get("tableNo", 0)
        table_name = pt.get("tableName", str(table_no))

        # Champs inclus dans le package
        try:
            pkg_fields = get_package_fields(
                tenant_id, environment, company_id, package_id, table_no, token
            )
        except Exception:
            pkg_fields = []

        if not pkg_fields:
            continue

        # Définitions de champs (type, caption) — best effort
        field_defs = get_field_definitions(
            tenant_id, environment, company_id, table_no, token
        )
        def_map = {
            d.get("fieldNo") or d.get("number", 0): d
            for d in field_defs
        }

        fields = []
        for pf in pkg_fields:
            field_no = pf.get("fieldNo") or pf.get("number", 0)
            fd = def_map.get(field_no, {})

            caption  = fd.get("caption") or fd.get("name") or pf.get("fieldName", "")
            dtype    = fd.get("type", "")
            required = fd.get("notBlank", False) or (field_no < 10)  # heuristique PK

            fields.append({
                "field_no":      field_no,
                "field_name":    pf.get("fieldName", ""),
                "field_caption": caption,
                "data_type":     dtype,
                "required":      required,
                "is_custom":     field_no >= 50000,
                "validate_field": pf.get("validateField", False),
                "example":       "",
                "description":   fd.get("description", ""),
            })

        result.append({
            "table_id":   table_no,
            "table_name": table_name,
            "fields":     fields,
        })

    return result
