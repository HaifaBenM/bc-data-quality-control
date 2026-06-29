"""
Page d'accueil — BC Data Quality Control.
"""
import streamlit as st
from app.db.supabase_client import test_connection

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1B3A6B 0%, #2E6FBF 100%);
        padding: 2rem; border-radius: 12px;
        margin-bottom: 2rem; color: white;
    }
    .main-header h1 { color: white; margin: 0; font-size: 2rem; }
    .main-header p  { color: #A8C4E8; margin: .5rem 0 0; font-size: 1rem; }
    .nav-card {
        background: white; border: 1px solid #E2E8F0;
        border-radius: 10px; padding: 1.5rem;
        text-align: center; height: 160px;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        transition: all 0.2s;
    }
    .nav-card:hover {
        border-color: #2E6FBF;
        box-shadow: 0 4px 12px rgba(46,111,191,.15);
    }
    .nav-card .icon { font-size: 2.5rem; margin-bottom: .5rem; }
    .nav-card h3    { color: #1B3A6B; margin: 0; font-size: 1rem; }
    .nav-card p     { color: #64748B; margin: .25rem 0 0; font-size: .8rem; }
    .status-badge {
        display: inline-block; padding: .25rem .75rem;
        border-radius: 20px; font-size: .8rem; font-weight: 500;
    }
    .status-ok      { background: #E1F5EE; color: #0F6E56; }
    .status-error   { background: #FAECE7; color: #993C1D; }
    .status-warning { background: #FAEEDA; color: #854F0B; }
</style>
""", unsafe_allow_html=True)

# ── En-tête ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🔍 BC Data Quality Control</h1>
    <p>Outil de contrôle qualité des données — Microsoft Dynamics 365 Business Central</p>
</div>
""", unsafe_allow_html=True)

# ── Statut connexion ──────────────────────────────────────────────────────────
col_status, _ = st.columns([3, 7])
with col_status:
    connected, message = test_connection()
    if connected:
        st.markdown(
            '<span class="status-badge status-ok">✅ Base de données connectée</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<span class="status-badge status-error">❌ BDD : {message}</span>',
            unsafe_allow_html=True
        )

st.markdown("---")

# ── Cartes de navigation ──────────────────────────────────────────────────────
st.markdown("### Navigation")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("""<div class="nav-card"><div class="icon">👥</div>
    <h3>Profils Clients</h3><p>Configurer les credentials BC</p></div>""",
    unsafe_allow_html=True)
with col2:
    st.markdown("""<div class="nav-card"><div class="icon">📁</div>
    <h3>Sessions</h3><p>Contrôle qualité des fichiers</p></div>""",
    unsafe_allow_html=True)
with col3:
    st.markdown("""<div class="nav-card"><div class="icon">📊</div>
    <h3>Dashboard</h3><p>Vue globale de la progression</p></div>""",
    unsafe_allow_html=True)

st.markdown("---")

# ── Description ───────────────────────────────────────────────────────────────
col_l, col_r = st.columns(2)
with col_l:
    st.markdown("""
**Objectif** : Garantir que les fichiers clients s'importent dans BC sans erreur.
- ✅ Validation des contraintes BC (type, longueur, format)
- ✅ Vérification des codes de référence
- ✅ Suggestions de correction par IA (Gemini)
- ✅ Niveaux d'intégration séquentiels (N0 → N4)
""")
with col_r:
    st.markdown("""
**Niveaux d'intégration** :
- 📊 N0 — Plan Comptable
- ⚙️ N1 — Operational Setup
- 📚 N2 — Reference Data
- 🏢 N3 — Master Data (par module)
- 📄 N4 — Transactional Data
""")

st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#94A3B8;font-size:.8rem;'>"
    "BC Data Quality Control — Talan</p>",
    unsafe_allow_html=True
)