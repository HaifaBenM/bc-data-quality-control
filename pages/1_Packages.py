"""
Page Packages — Liste des Configuration Packages BC.
- Dropdown sociétés BC (chargées depuis l'API)
- Liste packages filtrée par société sélectionnée
- Sélection d'une ligne → bouton unique "Importer en Excel"
"""
import streamlit as st
import pandas as pd
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import get_access_token, get_companies, get_config_packages_for_company

st.set_page_config(
    page_title="Packages — BC Quality Control",
    page_icon="📦",
    layout="wide",
)

# ── Guard ─────────────────────────────────────────────────────────────────────
active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")

if not active_client:
    st.warning("⚠️ Sélectionnez un client depuis le menu latéral.")
    st.stop()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.toolbar {
    display: flex; align-items: center; gap: .75rem;
    margin-bottom: 1.25rem;
}
.badge-code {
    background: #EEF4FD; color: #1B3A6B; font-weight: 700;
    padding: .15rem .5rem; border-radius: 4px;
    font-family: monospace; font-size: .82rem;
}
</style>
""", unsafe_allow_html=True)

# ── En-tête ───────────────────────────────────────────────────────────────────
st.markdown(f"# 📦 Packages — {active_client_name}")
st.markdown("---")

# ── Chargement profil ─────────────────────────────────────────────────────────
profile = get_profile_by_code(active_client)
if not profile:
    st.error("Profil client introuvable.")
    st.stop()

tenant_id     = profile.get("bc_tenant_id", "").strip()
client_id     = profile.get("bc_client_id", "").strip()
client_secret = profile.get("bc_client_secret", "").strip()
environment   = profile.get("bc_environment", "Production").strip()

if not all([tenant_id, client_id, client_secret, environment]):
    st.error("Credentials BC incomplets. Vérifiez le profil client.")
    st.stop()

# ── Token (cache 55 min — expire avant les 60 min Azure AD) ──────────────────
@st.cache_data(ttl=3300, show_spinner=False)
def _get_token(tid: str, cid: str, cs: str) -> str:
    return get_access_token(tid, cid, cs)

try:
    token = _get_token(tenant_id, client_id, client_secret)
except Exception as e:
    st.error(f"❌ Authentification BC échouée\n\n{e}")
    st.stop()

# ── Sociétés (cache 10 min) ───────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _get_companies(tid: str, env: str, _token: str) -> list:
    return get_companies(tid, env, _token)

try:
    companies = _get_companies(tenant_id, environment, token)
except Exception as e:
    st.error(f"❌ Impossible de charger les sociétés BC\n\n{e}")
    st.stop()

if not companies:
    st.warning("Aucune société BC trouvée dans cet environnement.")
    st.stop()

# ── Toolbar : société + boutons ───────────────────────────────────────────────
company_options = {
    c.get("displayName") or c.get("name", c["id"]): c["id"]
    for c in companies
}

col_select, col_refresh, col_import = st.columns([4, 1.2, 1.8])

with col_select:
    selected_company_name = st.selectbox(
        "Société",
        options=list(company_options.keys()),
        label_visibility="collapsed",
    )
    selected_company_id = company_options[selected_company_name]

with col_refresh:
    if st.button("🔄 Rafraîchir", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Packages (cache 5 min par société) ───────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _get_packages(tid: str, env: str, company_id: str, _token: str) -> list:
    return get_config_packages_for_company(tid, env, company_id, _token)

with st.spinner("⏳ Chargement des packages..."):
    try:
        packages = _get_packages(tenant_id, environment, selected_company_id, token)
    except Exception as e:
        st.error(f"❌ {e}")
        st.stop()

# ── Bouton Importer (dans col_import, disabled si rien sélectionné) ───────────
# On le rend ici mais on active/désactive selon la sélection plus bas

if not packages:
    with col_import:
        st.button("📥 Exporter en Excel", disabled=True, use_container_width=True, type="primary")
    st.info(f"Aucun package dans la société **{selected_company_name}**.")
    st.stop()

# ── Tableau avec sélection ────────────────────────────────────────────────────
st.caption(
    f"**{len(packages)} package(s)** · "
    f"Environnement : `{environment}` · Société : `{selected_company_name}`"
)

df = pd.DataFrame([
    {
        "Code":        p.get("code", ""),
        "Nom package": p.get("packageName", ""),
        "Ordre":       p.get("processingOrder", 0),
        "Nb tables":   p.get("numberOfTables", 0),
        "Nb erreurs":  p.get("numberOfErrors", 0),
    }
    for p in packages
])

event = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Code":        st.column_config.TextColumn("Code",        width="small"),
        "Nom package": st.column_config.TextColumn("Nom package", width="large"),
        "Ordre":       st.column_config.NumberColumn("Ordre",     width="small"),
        "Nb tables":   st.column_config.NumberColumn("Nb tables", width="small"),
        "Nb erreurs":  st.column_config.NumberColumn("Nb erreurs",width="small"),
    },
)

# ── Sélection + bouton Importer ───────────────────────────────────────────────
selected_rows = event.selection.rows if event and event.selection else []
has_selection = len(selected_rows) > 0

if has_selection:
    idx = selected_rows[0]
    sel_pkg = packages[idx]
    sel_code = sel_pkg.get("code", "")
    sel_name = sel_pkg.get("packageName", "")

    st.markdown(
        f'<div style="background:#EEF4FD;border:1px solid #BFDBFE;border-radius:6px;'
        f'padding:.5rem 1rem;font-size:.88rem;color:#1B3A6B;margin:.5rem 0">'
        f'✅ Sélectionné : <span class="badge-code">{sel_code}</span> — <b>{sel_name}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.caption("👆 Cliquez sur une ligne pour sélectionner un package.")

with col_import:
    if st.button(
        "📥 Importer en Excel",
        disabled=not has_selection,
        use_container_width=True,
        type="primary",
        key="btn_import",
    ):
        st.session_state["active_package_code"] = sel_code
        st.session_state["active_package_name"] = sel_name
        for k in ["step", "config", "parse_result", "validation",
                  "merged_result", "axe_c_result", "saved_session_id"]:
            st.session_state[k] = 1 if k == "step" else ({} if k == "config" else None)
        st.switch_page(f"ses_{active_client}")
