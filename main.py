import os
import streamlit as st
from app.db.profiles_db import get_all_profiles

st.set_page_config(
    page_title="BC Data Quality Control",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=60)
def _load_profiles() -> list:
    return get_all_profiles()


profiles = _load_profiles()
role     = st.session_state.get("role", "")

# ── Construction navigation selon le rôle ─────────────────────────────────────
sections: dict = {}

_home_page = st.Page(
    "pages/0_Home.py",
    title="Accueil",
    icon="🏠",
    url_path="home",
    default=True,
)

if role == "":
    # Aucun rôle → accueil uniquement
    sections[""] = [_home_page]

elif role == "consultant":
    # Toutes les sections clients + accueil + configuration
    sections[""] = [_home_page]
    for p in profiles:
        code = p.get("code", "")
        name = p.get("name", code)
        sections[f"🏢 {name}"] = [
            st.Page("pages/1_Packages.py",            title="Packages",             icon="📦", url_path=f"pkg_{code}"),
            st.Page("pages/2_Sessions_Integration.py", title="Sessions Intégration", icon="📁", url_path=f"ses_{code}"),
            st.Page("pages/3_Dashboard.py",           title="Dashboard",            icon="📊", url_path=f"dash_{code}"),
        ]
    sections["⚙️ Configuration"] = [
        st.Page(
            "pages/4_Profils_Clients.py" if os.path.exists("pages/4_Profils_Clients.py")
            else "pages/3_Profils_Clients.py",
            title="Profils Clients",
            icon="👥",
            url_path="profils",
        )
    ]

elif role == "client":
    # Uniquement la section du client connecté
    client_code    = st.session_state.get("active_client", "")
    client_profile = next((p for p in profiles if p.get("code") == client_code), None)

    sections[""] = [_home_page]

    if client_profile:
        name = client_profile.get("name", client_code)
        sections[f"🏢 {name}"] = [
            st.Page("pages/1_Packages.py",            title="Packages",             icon="📦", url_path=f"pkg_{client_code}"),
            st.Page("pages/2_Sessions_Integration.py", title="Sessions Intégration", icon="📁", url_path=f"ses_{client_code}"),
            st.Page("pages/3_Dashboard.py",           title="Dashboard",            icon="📊", url_path=f"dash_{client_code}"),
        ]

# ── Injection active_client depuis l'URL ──────────────────────────────────────
_url_to_client: dict = {}
for p in profiles:
    code = p.get("code", "")
    name = p.get("name", code)
    _url_to_client[f"pkg_{code}"]  = (code, name)
    _url_to_client[f"ses_{code}"]  = (code, name)
    _url_to_client[f"dash_{code}"] = (code, name)

pg          = st.navigation(sections)
current_url = str(getattr(pg, "url_path", "") or "")

if current_url in _url_to_client:
    _code, _name = _url_to_client[current_url]
    st.session_state["active_client"]      = _code
    st.session_state["active_client_name"] = _name
elif not st.session_state.get("active_client") and profiles:
    _first = profiles[0]
    st.session_state.setdefault("active_client",      _first.get("code", ""))
    st.session_state.setdefault("active_client_name", _first.get("name", ""))

# ── Bouton déconnexion dans la sidebar (si rôle actif) ───────────────────────
if role:
    with st.sidebar:
        st.markdown(
            "<hr style='border:none;border-top:1px solid #E2E8F0;margin:.5rem 0'>",
            unsafe_allow_html=True,
        )
        role_label = (
            "👔 Consultant"
            if role == "consultant"
            else f"🏢 {st.session_state.get('active_client_name', '')}"
        )
        st.caption(role_label)
        if st.button("🚪 Déconnexion", use_container_width=True, key="sidebar_logout"):
            st.session_state.clear()
            _load_profiles.clear()
            st.rerun()

pg.run()
