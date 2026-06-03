"""
Page Sessions — Créer et gérer les sessions de contrôle qualité.
Cette page sera développée aux Sprints 1, 8 et 9.
"""
import streamlit as st

st.set_page_config(
    page_title="Sessions — BC Quality Control",
    page_icon="📁",
    layout="wide"
)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 📁 Sessions de contrôle")
st.markdown("Créer une nouvelle session ou reprendre une session existante.")
st.markdown("---")

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

with tab1:
    st.markdown("### Créer une nouvelle session de contrôle")

    st.info("""
    🚧 **Sprint 1** — Ce formulaire permettra de :
    - Sélectionner le client et charger ses règles métier automatiquement
    - Choisir la Master Data concernée (Clients, Fournisseurs, Articles...)
    - Sélectionner les tables liées à inclure
    - Charger le fichier Excel reçu du client
    - Lancer l'analyse de qualité automatiquement
    """)

    # Aperçu du formulaire qui sera créé
    with st.expander("👀 Aperçu du formulaire (non fonctionnel)"):
        st.selectbox("Client", ["— Sélectionner un client —"], disabled=True)
        st.selectbox("Master Data", ["— Sélectionner une Master Data —"], disabled=True)
        st.multiselect("Tables liées", [], disabled=True)
        st.file_uploader("Fichier Excel client (.xlsx)", type=["xlsx"], disabled=True)
        st.button("🚀 Lancer l'analyse", disabled=True)

with tab2:
    st.markdown("### Sessions existantes")

    st.info("""
    🚧 **Sprint 9** — Cette section affichera la liste de toutes vos sessions
    avec leur statut, les anomalies restantes et la possibilité de reprendre
    une session interrompue.
    """)
