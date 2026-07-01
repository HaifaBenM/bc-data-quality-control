import os
"""
Point d'entrée principal — BC Data Quality Control.

Architecture navigation :
    st.navigation() génère des sections dynamiques par client chargé depuis Supabase.
    Chaque client obtient ses 3 sous-pages (Packages / Sessions / Dashboard)
    avec un url_path unique : pkg_CODE, ses_CODE, dash_CODE.

    Avant pg.run(), on extrait le client actif depuis pg.url_path et on l'injecte
    dans session_state — toutes les pages y ont accès sans render_sidebar().
"""
import streamlit as st
from app.db.profiles_db import get_all_profiles


@st.cache_data(ttl=60)
def _load_profiles() -> list:
    """Profils chargés avec cache 60s — évite un appel Supabase à chaque interaction."""
    return get_all_profiles()


st.set_page_config(
    page_title="BC Data Quality Control",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Chargement des profils clients ────────────────────────────────────────────
profiles = _load_profiles()

# ── Construction des sections dynamiques ──────────────────────────────────────
# Chaque profil client = une section dans la sidebar avec 3 sous-pages.
# url_path format : {type}_{CODE}  →  pkg_AQUA | ses_AQUA | dash_AQUA
# Séparateur "_" — les codes client ne doivent pas contenir d'underscore.
#
# st.switch_page(url_path) fonctionne en Streamlit 1.36+ :
#   st.switch_page("ses_AQUA")  →  navigue vers la page Sessions d'Aquachiara.

sections: dict = {
    # Page d'accueil — visible uniquement si aucun client n'est sélectionné
    # ou comme landing page par défaut (default=True)
    "": [
        st.Page(
            "pages/0_Home.py" if os.path.exists("pages/0_Home.py")
            else "pages/1_Packages.py",
            title="Accueil",
            icon="🏠",
            url_path="home",
            default=True,
        )
    ],
}

for p in profiles:
    code = p.get("code", "")
    name = p.get("name", code)

    sections[f"🏢 {name}"] = [
        st.Page(
            "pages/1_Packages.py",
            title="Packages",
            icon="📦",
            url_path=f"pkg_{code}",
        ),
        st.Page(
            "pages/2_Sessions_Integration.py",
            title="Sessions Intégration",
            icon="📁",
            url_path=f"ses_{code}",
        ),
        st.Page(
            "pages/3_Dashboard.py",
            title="Dashboard",
            icon="📊",
            url_path=f"dash_{code}",
        ),
    ]

# Profils Clients — hors section client (consultant uniquement, séparation future)
sections["⚙️ Configuration"] = [
    st.Page(
        "pages/4_Profils_Clients.py" if os.path.exists("pages/4_Profils_Clients.py")
        else "pages/3_Profils_Clients.py",
        title="Profils Clients",
        icon="👥",
        url_path="profils",
    ),
]

# ── Navigation ────────────────────────────────────────────────────────────────
pg = st.navigation(sections)

# ── Injection du client actif dans session_state ──────────────────────────────
# Lookup dict url_path → (code, name) pour correspondance exacte.
# Fallback : si l'URL ne correspond à aucun client (ex: page "profils" ou
# premier chargement), on garde le client déjà en session ou on prend le
# premier profil disponible.

_url_to_client: dict = {}
for p in profiles:
    code = p.get("code", "")
    name = p.get("name", code)
    _url_to_client[f"pkg_{code}"]  = (code, name)
    _url_to_client[f"ses_{code}"]  = (code, name)
    _url_to_client[f"dash_{code}"] = (code, name)

current_url = str(getattr(pg, "url_path", "") or "")

if current_url in _url_to_client:
    _code, _name = _url_to_client[current_url]
    st.session_state["active_client"]      = _code
    st.session_state["active_client_name"] = _name
elif not st.session_state.get("active_client") and profiles:
    # Premier chargement sans URL cliente → auto-sélectionner le 1er profil
    _first = profiles[0]
    st.session_state["active_client"]      = _first.get("code", "")
    st.session_state["active_client_name"] = _first.get("name", "")

# ── Lancement de la page sélectionnée ─────────────────────────────────────────
pg.run()
