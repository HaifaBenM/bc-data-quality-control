"""
Page Dashboard — Vue globale des sessions.
Sera complétée au Sprint 9.
"""
import streamlit as st

st.set_page_config(
    page_title="Dashboard — BC Quality Control",
    page_icon="📊",
    layout="wide"
)

st.markdown("# 📊 Dashboard")
st.markdown("Vue globale de toutes les sessions de contrôle qualité.")
st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Sessions actives", "—")
col2.metric("En attente client", "—")
col3.metric("Anomalies majeures", "—")
col4.metric("Fichiers prêts", "—")

st.markdown("---")
st.info("""
🚧 **Sprint 9** — Cette page affichera :
- La liste de toutes les sessions en cours (tous clients)
- Les statuts en temps réel
- Les indicateurs globaux du projet
- Les filtres par client, Master Data, consultant
""")
