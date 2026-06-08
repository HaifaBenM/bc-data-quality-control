"""
Module de connexion à Business Central via OAuth 2.0.
Utilise les credentials propres à chaque client (stockés dans son profil).
"""
import requests


def get_bc_token(
    tenant_id:     str,
    client_id:     str,
    client_secret: str
) -> tuple[bool, str]:
    """
    Obtient un token OAuth pour l'API BC du client.
    Utilise les 3 credentials du profil client.
    Retourne (True, access_token) ou (False, message_erreur).
    """
    if not tenant_id or not tenant_id.strip():
        return False, "Tenant ID manquant."
    if not client_id or not client_id.strip():
        return False, "Client ID manquant."
    if not client_secret or not client_secret.strip():
        return False, "Client Secret manquant."

    token_url = (
        f"https://login.microsoftonline.com/"
        f"{tenant_id.strip()}/oauth2/v2.0/token"
    )
    payload = {
        "client_id":     client_id.strip(),
        "client_secret": client_secret.strip(),
        "grant_type":    "client_credentials",
        "scope":         "https://api.businesscentral.dynamics.com/.default",
    }

    try:
        resp = requests.post(token_url, data=payload, timeout=15)
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            if token:
                return True, token
            return False, "Token vide dans la reponse Azure."
        else:
            data  = resp.json()
            error = data.get(
                "error_description",
                data.get("error", "Erreur inconnue")
            )
            return False, f"Authentification echouee : {error}"

    except requests.exceptions.ConnectionError:
        return False, "Impossible de joindre login.microsoftonline.com."
    except requests.exceptions.Timeout:
        return False, "Delai d'attente depasse."
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def test_bc_connection(
    tenant_id:     str,
    client_id:     str,
    client_secret: str,
    environment:   str = ""
) -> tuple[bool, str]:
    """
    Teste la connexion complete a un environnement BC.
    Utilise les 3 credentials du profil client.

    Etape 1 : Obtenir un token OAuth
    Etape 2 : Appeler l'API BC pour lister les societes

    Retourne (True, message_succes) ou (False, message_erreur).
    """
    # Etape 1 - Token OAuth
    ok, result = get_bc_token(tenant_id, client_id, client_secret)
    if not ok:
        return False, result

    token = result

    # Etape 2 - Appel API BC
    if environment and environment.strip():
        bc_url = (
            f"https://api.businesscentral.dynamics.com/v2.0/"
            f"{tenant_id.strip()}/{environment.strip()}/api/v2.0/companies"
        )
    else:
        bc_url = (
            f"https://api.businesscentral.dynamics.com/v2.0/"
            f"{tenant_id.strip()}/api/v2.0/companies"
        )

    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.get(bc_url, headers=headers, timeout=15)

        if resp.status_code == 200:
            companies = resp.json().get("value", [])
            nb    = len(companies)
            names = ", ".join(c.get("name", "?") for c in companies[:3])
            extra = f" ... +{nb - 3} autres" if nb > 3 else ""
            return True, (
                f"Connexion reussie - {nb} societe(s) : {names}{extra}"
            )

        elif resp.status_code == 401:
            return False, (
                "Acces refuse (401). Verifiez les credentials "
                "et le consentement administrateur BC."
            )
        elif resp.status_code == 404:
            env_info = f"'{environment}'" if environment else "par defaut"
            return False, (
                f"Environnement {env_info} introuvable (404). "
                "Verifiez le nom exact de l'environnement BC."
            )
        else:
            return False, f"Erreur API BC ({resp.status_code})."

    except requests.exceptions.ConnectionError:
        return False, "Impossible de joindre l'API Business Central."
    except requests.exceptions.Timeout:
        return False, "Delai d'attente depasse lors de l'appel BC."
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def get_bc_companies(
    tenant_id:     str,
    client_id:     str,
    client_secret: str,
    environment:   str = ""
) -> list:
    """Retourne la liste des societes BC du client."""
    ok, result = get_bc_token(tenant_id, client_id, client_secret)
    if not ok:
        return []

    token = result
    if environment and environment.strip():
        url = (
            f"https://api.businesscentral.dynamics.com/v2.0/"
            f"{tenant_id.strip()}/{environment.strip()}/api/v2.0/companies"
        )
    else:
        url = (
            f"https://api.businesscentral.dynamics.com/v2.0/"
            f"{tenant_id.strip()}/api/v2.0/companies"
        )

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json().get("value", [])
    except Exception:
        pass
    return []
