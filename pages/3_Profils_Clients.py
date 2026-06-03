"""
Page Profils Clients — Gérer les profils et règles métier par client.
Cette page sera développée au Sprint 2.
"""
import streamlit as st
from app.db.supabase_client import test_connection

st.set_page_config(
    page_title="Profils Clients — BC Quality Control",
    page_icon="👥",
    layout="wide"
)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 👥 Profils Clients")
st.markdown("Créer et gérer les profils clients avec leurs règles métier.")
st.markdown("---")

# ── Vérification connexion ───────────────────────────────────────────────────
connected, message = test_connection()
if not connected:
    st.error(f"❌ Base de données non connectée : {message}")
    st.stop()

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["👥 Liste des profils", "➕ Nouveau profil"])

with tab1:
    st.markdown("### Profils existants")
    st.info("""
    🚧 **Sprint 2** — Cette section affichera :
    - La liste de tous les profils clients
    - Le nombre de règles métier par client
    - L'accès rapide aux règles de chaque client
    - La possibilité de copier des règles entre clients
    """)

with tab2:
    st.markdown("### Créer un nouveau profil client")
    st.info("""
    🚧 **Sprint 2** — Ce formulaire permettra de créer un profil client avec :
    - Code client, Nom, Secteur d'activité
    - URL de l'environnement BC cible
    - Langue des données (aide l'IA pour les suggestions)
    - Notes sur le projet
    """)

    # Aperçu du formulaire
    with st.expander("👀 Aperçu du formulaire (non fonctionnel)"):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Code client", placeholder="CLT-ABC-001", disabled=True)
            st.text_input("Nom client", placeholder="ABC Distribution SARL", disabled=True)
            st.text_input("Secteur", placeholder="Distribution B2B", disabled=True)
        with col2:
            st.text_input("URL BC", placeholder="https://abc.businesscentral.dynamics.com", disabled=True)
            st.selectbox("Langue des données", ["Français", "Anglais", "Arabe"], disabled=True)
        st.text_area("Notes projet", placeholder="Contexte du projet...", disabled=True)
        st.button("💾 Enregistrer le profil", disabled=True)
