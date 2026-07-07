import hashlib
import streamlit as st


# ── Vérification mot de passe ─────────────────────────────────────────────────

def check_password(password: str) -> bool:
    """
    Compare le hash SHA-256 du mot de passe saisi avec le secret Streamlit.

    Configuration requise dans Streamlit Cloud → Settings → Secrets :
        CONSULTANT_PASSWORD_HASH = "sha256_hexdigest_ici"

    Pour générer le hash localement :
        import hashlib; print(hashlib.sha256("ton_mdp".encode()).hexdigest())

    Retourne False si le secret n'est pas configuré (accès refusé par défaut).
    """
    try:
        expected = st.secrets["CONSULTANT_PASSWORD_HASH"]
    except (KeyError, AttributeError, FileNotFoundError):
        return False
    return hashlib.sha256(password.encode()).hexdigest() == expected


# ── Gestion du rôle en session ────────────────────────────────────────────────

def set_role(
    role: str,
    client_code: str = "",
    client_name: str = "",
) -> None:
    """
    Positionne le rôle en session_state.
    role : "consultant" | "client"
    À appeler depuis 0_Home.py uniquement — pas depuis les pages métier.
    """
    st.session_state["role"]               = role
    st.session_state["active_client"]      = client_code
    st.session_state["active_client_name"] = client_name


def get_role() -> str:
    """Retourne le rôle courant : "consultant" | "client" | ""."""
    return st.session_state.get("role", "")


def is_consultant() -> bool:
    return get_role() == "consultant"


def is_client() -> bool:
    return get_role() == "client"


def logout() -> None:
    """Réinitialise complètement la session."""
    st.session_state.clear()


# ── Guards ────────────────────────────────────────────────────────────────────

def require_role() -> None:
    """
    Stop la page si aucun rôle n'est sélectionné (session expirée ou accès direct).
    À appeler en début de chaque page métier après set_page_config.
    """
    if not get_role():
        st.warning("Session expirée ou accès direct. Retournez à l'accueil.")
        if st.button("← Retour à l'accueil", type="primary"):
            st.switch_page("home")
        st.stop()


def require_consultant() -> None:
    """
    Stop la page si l'utilisateur n'est pas consultant.
    À appeler en début des pages réservées (Profils Clients).
    """
    require_role()
    if not is_consultant():
        st.error("Accès réservé aux consultants Talan.")
        st.stop()
