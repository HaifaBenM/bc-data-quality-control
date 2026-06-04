import streamlit as st
from app.db.supabase_client import test_connection

st.set_page_config(
    page_title="BC Data Quality Control",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    :root { --navy: #1B3A6B; --blue: #2E6FBF; --green: #0F6E56; }
    .main-header {
        background: linear-gradient(135deg, #1B3A6B 0%, #2E6FBF 100%);
        padding: 2rem; border-radius: 12px; margin-bottom: 2rem; color: white;
    }
    .main-header h1 { color: white; margin: 0; font-size: 2rem; }
    .main-header p  { color: #A8C4E8; margin: 0.5rem 0 0 0; font-size: 1rem; }
    .nav-card {
        background: white; border: 1px solid #E2E8F0; border-radius: 10px;
        padding: 1.5rem; text-align: center; transition: all 0.2s;
        height: 160px; display: flex; flex-direction: column;
        align-items: center; justify-content: center;
    }
    .nav-card:hover { border-color: #2E6FBF; box-shadow: 0 4px 12px rgba(46,111,191,.15); }
    .nav-card .icon { font-size: 2.5rem; margin-bottom: 0.5rem; }
    .nav-card h3    { color: #1B3A6B; margin: 0; font-size: 1rem; }
    .nav-card p     { color: #64748B; margin: 0.25rem 0 0 0; font-size: 0.8rem; }
    .status-badge {
        display: inline-block; padding: 0.25rem 0.75rem;
        border-radius: 20px; font-size: 0.8rem; font-weight: 500;
    }
    .status-ok      { background: #E1F5EE; color: #0F6E56; }
    .status-error   { background: #FAECE7; color: #993C1D; }
    .status-warning { background: #FAEEDA; color: #854F0B; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>🔍 BC Data Quality Control</h1>
    <p>Outil de contrôle qualité des données Master Data — Microsoft Dynamics 365 Business Central</p>
</div>
""", unsafe_allow_html=True)

col_status, col_version, col_empty = st.columns([2, 2, 6])

with col_status:
    connected, message = test_connection()
    if connected:
        st.markdown('<span class="status-badge status-ok">✅ Base de données connectée</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="status-badge status-error">❌ Base de données : {message}</span>',
                    unsafe_allow_html=True)

with col_version:
    st.markdown('<span class="status-badge status-warning">🚧 Sprint 1 — Upload & Validation</span>',
                unsafe_allow_html=True)

st.markdown("---")
st.markdown("### Navigation")
st.markdown("Choisissez une section depuis la barre latérale ou cliquez sur une carte.")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""<div class="nav-card"><div class="icon">📊</div>
    <h3>Dashboard</h3><p>Vue globale de toutes les sessions</p></div>""",
    unsafe_allow_html=True)

with col2:
    st.markdown("""<div class="nav-card"><div class="icon">📁</div>
    <h3>Sessions</h3><p>Créer et gérer les sessions de contrôle</p></div>""",
    unsafe_allow_html=True)

with col3:
    st.markdown("""<div class="nav-card"><div class="icon">👥</div>
    <h3>Profils Clients</h3><p>Gérer les profils et règles par client</p></div>""",
    unsafe_allow_html=True)

with col4:
    st.markdown("""<div class="nav-card"><div class="icon">⚙️</div>
    <h3>Règles Métier</h3><p>Configurer les règles de validation</p></div>""",
    unsafe_allow_html=True)

st.markdown("---")

col_left, col_right = st.columns(2)
with col_left:
    st.markdown("""
    **Objectif** : Garantir que les fichiers de données clients peuvent être importés
    dans Business Central sans erreur, en combinant :
    - ✅ Validation des contraintes BC standard
    - ✅ Vérification des références croisées BC
    - ✅ Suggestions de correction par IA
    - ✅ Règles métier spécifiques par client
    """)

with col_right:
    st.markdown("""
    **Nouveautés Sprint 1** :
    - 📁 Upload du fichier Excel client
    - 🔍 Vérification structurelle automatique
    - 👀 Prévisualisation des données par onglet
    - ✅ Détection des onglets manquants ou non conformes
    """)

st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#94A3B8;font-size:0.8rem;'>"
    "BC Data Quality Control v0.2 — Sprint 1</p>",
    unsafe_allow_html=True
)
