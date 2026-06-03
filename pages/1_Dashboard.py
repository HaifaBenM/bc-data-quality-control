"""
Page Dashboard — Vue globale de toutes les sessions de contrôle.
Cette page sera complétée au Sprint 9.
"""
import streamlit as st

st.set_page_config(
    page_title="Dashboard — BC Quality Control",
    page_icon="📊",
    layout="wide"
)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 📊 Dashboard")
st.markdown("Vue globale de toutes les sessions de contrôle qualité.")
st.markdown("---")

# ── Indicateurs (placeholder) ────────────────────────────────────────────────
st.markdown("### Indicateurs globaux")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Sessions actives", value="—", delta=None)
with col2:
    st.metric(label="En attente client", value="—", delta=None)
with col3:
    st.metric(label="Anomalies majeures", value="—", delta=None)
with col4:
    st.metric(label="Fichiers prêts", value="—", delta=None)

st.markdown("---")

# ── Placeholder ──────────────────────────────────────────────────────────────
st.info("""
🚧 **Sprint 9** — Cette page affichera :
- La liste de toutes les sessions en cours pour tous les clients
- Les statuts en temps réel (En cours / En attente client / Terminée)
- Les indicateurs globaux du projet
- Les filtres par client, Master Data, consultant responsable
""")
