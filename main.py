"""
Point d'entrée principal — BC Data Quality Control.
Utilise st.navigation() pour contrôler les labels de la sidebar.
"""
import streamlit as st
from app.db.supabase_client import test_connection

st.set_page_config(
    page_title="BC Data Quality Control",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Définition des pages avec labels personnalisés ────────────────────────────
# st.navigation() permet de contrôler le nom affiché dans la sidebar
# indépendamment du nom du fichier — résout le problème des accents.
pages = st.navigation([
    st.Page("pages/0_Accueil.py",          title="Accueil",         icon="🏠"),
    st.Page("pages/1_Dashboard.py",        title="Dashboard",       icon="📊"),
    st.Page("pages/2_Sessions.py",         title="Sessions",        icon="📁"),
    st.Page("pages/3_Profils_Clients.py",  title="Profils Clients", icon="👥"),
    st.Page("pages/4_Regles_Metier.py",    title="Règles Métier",   icon="⚙️"),
])

pages.run()
