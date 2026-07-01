"""
Page d'accueil — BC Data Quality Control.
Affichée quand aucun client n'est encore sélectionné,
ou comme landing page par défaut.
"""
import streamlit as st
from app.db.profiles_db import get_all_profiles

st.set_page_config(
    page_title="BC Data Quality Control — Talan",
    page_icon="🔍",
    layout="wide",
)

st.markdown("""
<style>
.hero {
    background: linear-gradient(135deg, #1B3A6B 0%, #2E6FBF 100%);
    border-radius: 14px; padding: 2.5rem 3rem;
    margin-bottom: 2rem; color: white;
}
.hero h1 { color: white; font-size: 2rem; margin: 0 0 .5rem; }
.hero p  { color: #A8C4E8; font-size: 1rem; margin: 0; }

.client-card {
    background: white; border: 1px solid #E2E8F0;
    border-radius: 10px; padding: 1.25rem 1.5rem;
    cursor: pointer; transition: all .15s;
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: .75rem;
}
.client-card:hover { border-color: #2E6FBF; box-shadow: 0 4px 12px rgba(46,111,191,.12); }
.client-icon {
    width: 44px; height: 44px; border-radius: 10px;
    background: #EEF4FD; display: flex; align-items: center;
    justify-content: center; font-size: 1.4rem; flex-shrink: 0;
}
.client-name { font-weight: 600; color: #1B3A6B; font-size: 1rem; margin: 0; }
.client-code { color: #94A3B8; font-size: .8rem; font-family: monospace; }

.feature-box {
    background: #F8FAFC; border: 1px solid #E2E8F0;
    border-radius: 8px; padding: 1rem 1.25rem;
    height: 100%;
}
.feature-box h4 { color: #1B3A6B; margin: 0 0 .4rem; font-size: .95rem; }
.feature-box p  { color: #64748B; font-size: .82rem; margin: 0; line-height: 1.5; }
</style>
""", unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <h1>🔍 BC Data Quality Control</h1>
    <p>Contrôle qualité des données avant import Business Central — Talan</p>
</div>
""", unsafe_allow_html=True)

# ── Clients ───────────────────────────────────────────────────────────────────
profiles = get_all_profiles()

col_clients, col_features = st.columns([5, 4], gap="large")

with col_clients:
    st.markdown("### Sélectionnez un client")

    if not profiles:
        st.info("Aucun profil client configuré. Allez dans **Profils Clients** pour commencer.")
    else:
        for p in profiles:
            code = p.get("code", "")
            name = p.get("name", "")
            env  = p.get("bc_environment", "")
            env_label = f" · `{env}`" if env else ""

            col_card, col_btn = st.columns([5, 2])
            with col_card:
                st.markdown(
                    f'<div class="client-card">'
                    f'<div class="client-icon">🏢</div>'
                    f'<div>'
                    f'<p class="client-name">{name}</p>'
                    f'<span class="client-code">{code}{env_label}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                st.markdown("<div style='padding-top:10px'>", unsafe_allow_html=True)
                if st.button(
                    "Ouvrir →",
                    key=f"open_{code}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state["active_client"]      = code
                    st.session_state["active_client_name"] = name
                    st.switch_page(f"pkg_{code}")
                st.markdown("</div>", unsafe_allow_html=True)

with col_features:
    st.markdown("### Ce que fait l'outil")
    st.markdown("""
<div class="feature-box" style="margin-bottom:.75rem">
    <h4>📦 Packages BC</h4>
    <p>Liste les packages de configuration directement depuis votre environnement BC.</p>
</div>
<div class="feature-box" style="margin-bottom:.75rem">
    <h4>✅ Validation des données</h4>
    <p>Axe A (format/type/longueur), Axe B (codes de référence), Axe C (IA Gemini).</p>
</div>
<div class="feature-box" style="margin-bottom:.75rem">
    <h4>🔄 Ordre d'intégration BC</h4>
    <p>Reproduit l'ordre exact BC (Processing Order + Table ID) pour détecter les erreurs FK en cascade.</p>
</div>
<div class="feature-box">
    <h4>📁 Historique par client</h4>
    <p>Toutes les sessions de validation archivées et accessibles par client.</p>
</div>
""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#94A3B8;font-size:.8rem'>"
    "BC Data Quality Control — Talan · Microsoft Dynamics 365 Business Central</p>",
    unsafe_allow_html=True,
)
