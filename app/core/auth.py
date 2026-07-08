import streamlit as st
from app.db.users_db import check_login


def login(username: str, password: str) -> tuple[bool, str]:
    """
    Authentifie un utilisateur.
    Retourne (True, "") ou (False, message_erreur).
    Positionne session_state si succès.
    """
    user = check_login(username, password)
    if not user:
        return False, "Identifiant ou mot de passe incorrect."

    st.session_state["role"]               = user["role"]
    st.session_state["display_name"]       = user["display_name"]
    st.session_state["active_client"]      = user.get("profile_code") or ""
    st.session_state["active_client_name"] = user.get("display_name", "")
    return True, ""


def get_role() -> str:
    return st.session_state.get("role", "")


def get_display_name() -> str:
    return st.session_state.get("display_name", "")


def is_consultant() -> bool:
    return get_role() == "consultant"


def is_client() -> bool:
    return get_role() == "client"


def logout() -> None:
    st.session_state.clear()


def require_role() -> None:
    """Bloque la page si non authentifié."""
    if not get_role():
        st.warning("Session expirée. Reconnectez-vous.")
        if st.button("← Retour à l'accueil", type="primary"):
            st.switch_page("pages/0_Home.py")
        st.stop()


def require_consultant() -> None:
    require_role()
    if not is_consultant():
        st.error("Accès réservé aux consultants.")
        st.stop()
