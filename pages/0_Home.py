import streamlit as st
from app.db.profiles_db import get_all_profiles
from app.core.auth import check_password, set_role, get_role, is_consultant

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

.role-card {
    border-radius: 10px; padding: 1.5rem;
    height: 100%; border: 1px solid #E2E8F0;
}
.role-card.consultant { background: #EEF4FD; border-color: #BFDBFE; }
.role-card.client     { background: #F0FBF5; border-color: #BBF7D0; }
.role-card h3 { margin: 0 0 .75rem; }

.client-row {
    display: flex; align-items: center; justify-content: space-between;
    background: white; border: 1px solid #E2E8F0; border-radius: 8px;
    padding: .6rem 1rem; margin: .4rem 0;
}
.client-name { font-weight: 600; color: #1B3A6B; font-size: .95rem; }
.client-env  { font-size: .78rem; color: #94A3B8; font-family: monospace; }

.session-banner {
    background: #E1F5EE; border: 1px solid #0F6E56; border-radius: 8px;
    padding: .75rem 1.25rem; margin-bottom: 1.5rem;
    display: flex; align-items: center; justify-content: space-between;
}
</style>
""", unsafe_allow_html=True)

# ── Query param : lien client direct (?client=CODE) ───────────────────────────
params = st.query_params
if "client" in params and not get_role():
    code = params["client"]
    profiles = get_all_profiles()
    match = next((p for p in profiles if p["code"] == code), None)
    if match:
        set_role("client", match["code"], match["name"])
        st.query_params.clear()
        st.session_state["_pending_switch"] = f"pkg_{code}"
        st.rerun()

# ── Déjà connecté → bannière + continuer ─────────────────────────────────────
role = get_role()

# Redirect différé : set_role() + rerun() → navigation reconstruite → switch possible
if role and st.session_state.get("_pending_switch"):
    target = st.session_state.pop("_pending_switch")
    st.switch_page(target)

if role:
    label = (
        "👔 Connecté en tant que **Consultant**"
        if role == "consultant"
        else f"🏢 Connecté en tant que client — **{st.session_state.get('active_client_name', '')}**"
    )
    col_msg, col_btn = st.columns([5, 2])
    with col_msg:
        st.markdown(
            f'<div class="session-banner">{label}</div>',
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("🚪 Changer de session", use_container_width=True):
            from app.core.auth import logout
            logout()
            st.rerun()
    st.stop()

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <h1>🔍 BC Data Quality Control</h1>
    <p>Contrôle qualité des données avant import — Microsoft Dynamics 365 Business Central · Talan</p>
</div>
""", unsafe_allow_html=True)

col_consultant, col_client = st.columns(2, gap="large")

# ════════════════════════════════════════════════════════════════════════════
# COLONNE GAUCHE — Accès Consultant
# ════════════════════════════════════════════════════════════════════════════
with col_consultant:
    st.markdown("""
<div class="role-card consultant">
    <h3>👔 Accès Consultant</h3>
</div>
""", unsafe_allow_html=True)

    st.markdown("")
    password = st.text_input(
        "Mot de passe",
        type="password",
        placeholder="••••••••",
        key="consultant_pwd",
        label_visibility="collapsed",
    )

    if st.button("Se connecter", type="primary", use_container_width=True):
        if not password:
            st.error("Saisissez le mot de passe.")
        elif check_password(password):
            set_role("consultant")
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")

    st.caption("Accès réservé aux consultants Talan.")

# ════════════════════════════════════════════════════════════════════════════
# COLONNE DROITE — Accès Client
# ════════════════════════════════════════════════════════════════════════════
with col_client:
    st.markdown("""
<div class="role-card client">
    <h3>🏢 Accès Client</h3>
</div>
""", unsafe_allow_html=True)

    st.markdown("")
    profiles = get_all_profiles()

    if not profiles:
        st.info("Aucun client configuré. Contactez votre consultant Talan.")
    else:
        for p in profiles:
            code = p.get("code", "")
            name = p.get("name", "")
            env  = p.get("bc_environment", "")

            col_info, col_btn = st.columns([5, 2])
            with col_info:
                st.markdown(
                    f'<div class="client-row">'
                    f'<div>'
                    f'<div class="client-name">{name}</div>'
                    f'<div class="client-env">{env}</div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                st.markdown("<div style='padding-top:6px'>", unsafe_allow_html=True)
                if st.button(
                    "Ouvrir →",
                    key=f"open_{code}",
                    use_container_width=True,
                ):
                    set_role("client", code, name)
                    # Ne pas switch_page ici : la navigation n'est pas encore
                    # reconstruite avec les pages client. On stocke la cible
                    # et on rerun → main.py reconstruit → 0_Home.py intercepte.
                    st.session_state["_pending_switch"] = f"pkg_{code}"
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#94A3B8;font-size:.8rem'>"
    "BC Data Quality Control — Talan · Microsoft Dynamics 365 Business Central</p>",
    unsafe_allow_html=True,
)
