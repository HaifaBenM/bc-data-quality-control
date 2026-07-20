import base64
import streamlit as st
from app.core.auth import login, get_role, get_display_name, logout


@st.cache_data
def _icon_b64() -> str:
    with open("image/d365businesscentral-1.ico", "rb") as f:
        return base64.b64encode(f.read()).decode()


st.markdown("""
<style>
.login-card {
    max-width: 420px; margin: 4rem auto;
    background: white; border: 1px solid #E2E8F0;
    border-radius: 14px; padding: 2.5rem;
    box-shadow: 0 4px 24px rgba(0,0,0,.06);
}
.login-logo {
    text-align: center; margin-bottom: 2rem;
}
.login-logo h1 {
    color: #1B3A6B; font-size: 1.5rem; margin: .5rem 0 0;
}
.login-logo p {
    color: #94A3B8; font-size: .85rem; margin: .25rem 0 0;
}
.session-info {
    max-width: 420px; margin: 4rem auto;
    background: #EEF4FD; border: 1px solid #BFDBFE;
    border-radius: 14px; padding: 2rem; text-align: center;
}
.session-info h2 { color: #1B3A6B; margin: 0 0 .5rem; }
.session-info p  { color: #475569; margin: 0; font-size: .9rem; }
</style>
""", unsafe_allow_html=True)

# ── Handle pending redirect ────────────────────────────────────────────────────
role = get_role()
if role and st.session_state.get("_pending_switch"):
    target = st.session_state.pop("_pending_switch")
    st.switch_page(target)

# ── Déjà connecté ─────────────────────────────────────────────────────────────
if role:
    name = get_display_name()
    role_label = "Consultant" if role == "consultant" else "Client"
    st.markdown(f"""
<div class="session-info">
    <h2>👋 Bonjour, {name}</h2>
    <p>{role_label} · Connecté</p>
</div>
""", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continuer →", type="primary", use_container_width=True):
            st.session_state["_pending_switch"] = "pages/1_Packages.py"
            st.rerun()
    with col2:
        if st.button("🚪 Déconnexion", use_container_width=True):
            logout()
            st.rerun()
    st.stop()

# ── Formulaire de connexion ───────────────────────────────────────────────────
st.markdown(f"""
<div class="login-card">
    <div class="login-logo">
        <div style="font-size:2.5rem"><img src="data:image/x-icon;base64,{_icon_b64()}" style="height:2.5rem;width:2.5rem;vertical-align:middle;"></div>
        <h1>BC Data Quality Control</h1>
        <p>Microsoft Dynamics 365 Business Central · Talan</p>
    </div>
</div>
""", unsafe_allow_html=True)

_, col, _ = st.columns([1, 2, 1])
with col:
    with st.form("login_form"):
        st.markdown("#### Connexion")
        username = st.text_input(
            "Identifiant",
            placeholder="votre identifiant",
            autocomplete="username",
        )
        password = st.text_input(
            "Mot de passe",
            type="password",
            placeholder="••••••••",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(
            "Se connecter",
            type="primary",
            use_container_width=True,
        )

if submitted:
    if not username or not password:
        with col:
            st.error("Saisissez votre identifiant et votre mot de passe.")
    else:
        ok, msg = login(username, password)
        if ok:
            st.rerun()
        else:
            with col:
                st.error(msg)

st.markdown(
    "<p style='text-align:center;color:#CBD5E1;font-size:.75rem;margin-top:2rem'>"
    "BC Data Quality Control — Talan</p>",
    unsafe_allow_html=True,
)