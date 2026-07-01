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

sections: dict = {}

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
        "pages/4_Profils_Clients.py",
        title="Profils Clients",
        icon="👥",
        url_path="profils",
    ),
]

# ── Navigation ────────────────────────────────────────────────────────────────
pg = st.navigation(sections)

# ── Injection du client actif dans session_state ──────────────────────────────
# pg.url_path contient la page courante (ex: "pkg_AQUA", "ses_CLIENT2").
# On parse le suffixe pour identifier le client et on l'injecte AVANT pg.run()
# afin que toutes les pages y aient accès via st.session_state["active_client"].
#
# Si aucun profil ne correspond (ex: page "profils"), on ne modifie pas le
# client déjà en session — permet de revenir sur la dernière page cliente.

current_url = getattr(pg, "url_path", "") or ""

for p in profiles:
    code = p.get("code", "")
    # Le code suit le premier "_" dans l'url_path : pkg_AQUA → AQUA
    if current_url.endswith(f"_{code}") or current_url == f"pkg_{code}" \
            or current_url == f"ses_{code}" or current_url == f"dash_{code}":
        st.session_state["active_client"]      = code
        st.session_state["active_client_name"] = p.get("name", code)
        break

# ── Lancement de la page sélectionnée ─────────────────────────────────────────
pg.run()
