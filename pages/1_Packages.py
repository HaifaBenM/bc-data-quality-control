import streamlit as st
import pandas as pd
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import (
    get_access_token, get_companies,
    get_config_packages_for_company,
    get_packages_qc,
)
from app.core.auth import require_role, is_consultant

require_role()

active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")

st.markdown(f"# 📦 Packages — {active_client_name}")
st.markdown("---")

profile = get_profile_by_code(active_client)
if not profile:
    st.error("Profil client introuvable.")
    st.stop()

tenant_id     = profile.get("bc_tenant_id", "").strip()
client_id_bc  = profile.get("bc_client_id", "").strip()
client_secret = profile.get("bc_client_secret", "").strip()
environment   = profile.get("bc_environment", "Production").strip()

if not all([tenant_id, client_id_bc, client_secret, environment]):
    st.error("Credentials BC incomplets dans le profil.")
    st.stop()

@st.cache_data(ttl=3300, show_spinner=False)
def _token(tid, cid, cs):
    return get_access_token(tid, cid, cs)

try:
    token = _token(tenant_id, client_id_bc, client_secret)
except Exception as e:
    st.error(f"Authentification BC échouée : {e}")
    st.stop()

@st.cache_data(ttl=600, show_spinner=False)
def _companies(tid, env, _tok):
    return get_companies(tid, env, _tok)

try:
    companies = _companies(tenant_id, environment, token)
except Exception as e:
    st.error(f"Impossible de charger les sociétés BC : {e}")
    st.stop()

if not companies:
    st.warning("Aucune société BC disponible.")
    st.stop()

company_opts = {
    c.get("displayName") or c.get("name", c["id"]): c["id"]
    for c in companies
}
col_soc, col_refresh = st.columns([5, 1])
with col_soc:
    sel_company_name = st.selectbox("Société", list(company_opts.keys()), label_visibility="collapsed")
    sel_company_id   = company_opts[sel_company_name]
with col_refresh:
    if st.button("🔄 Rafraîchir", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=300, show_spinner=False)
def _pkgs_automation(tid, env, cid, _tok):
    return get_config_packages_for_company(tid, env, cid, _tok)

@st.cache_data(ttl=300, show_spinner=False)
def _pkgs_qc(tid, env, cid, _tok, visible_only):
    return get_packages_qc(tid, env, cid, _tok, visible_only=visible_only)

with st.spinner("Chargement des packages..."):
    try:
        all_pkgs = _pkgs_automation(tenant_id, environment, sel_company_id, token)
        qc_pkgs  = _pkgs_qc(tenant_id, environment, sel_company_id, token, False)
        vis_map  = {p["code"]: p.get("qcVisibleClient", False) for p in qc_pkgs}
        for pkg in all_pkgs:
            pkg["qcVisibleClient"] = vis_map.get(pkg.get("code", ""), False)
        displayed = [p for p in all_pkgs if p.get("qcVisibleClient", False)]
    except Exception as e:
        err = str(e)
        if "talan/qctools" in err or "404" in err:
            st.error("L'extension **Talan QC Tools** n'est pas déployée sur cet environnement.")
        else:
            st.error(f"Erreur chargement packages : {e}")
        st.stop()

if not displayed:
    st.info("Aucun package disponible.")
    st.stop()

st.caption(f"**{len(displayed)} package(s)** · `{environment}` · `{sel_company_name}`")

df = pd.DataFrame([{
    "Code":        p.get("code", ""),
    "Nom package": p.get("packageName", ""),
    "Nb tables":   p.get("numberOfTables", 0),
    "Nb erreurs":  p.get("numberOfErrors", 0),
} for p in displayed])

event = st.dataframe(
    df, use_container_width=True, hide_index=True,
    on_select="rerun", selection_mode="single-row",
    column_config={
        "Code":        st.column_config.TextColumn(width="small"),
        "Nom package": st.column_config.TextColumn(width="large"),
        "Nb tables":   st.column_config.NumberColumn(width="small"),
        "Nb erreurs":  st.column_config.NumberColumn(width="small"),
    },
)

sel_rows = event.selection.rows if event and event.selection else []
has_sel  = len(sel_rows) > 0

if has_sel:
    idx      = sel_rows[0]
    sel_pkg  = displayed[idx]
    sel_code = sel_pkg.get("code", "")
    sel_name = sel_pkg.get("packageName", "")
    st.markdown(
        f'<div style="background:#EEF4FD;border:1px solid #BFDBFE;border-radius:6px;'
        f'padding:.5rem 1rem;font-size:.88rem;color:#1B3A6B;margin:.5rem 0">'
        f'<b style="font-family:monospace">{sel_code}</b> — {sel_name}</div>',
        unsafe_allow_html=True,
    )

col_ses, _ = st.columns([2, 6])
with col_ses:
    if st.button("📁 Ouvrir dans Sessions", disabled=not has_sel, use_container_width=True, type="primary"):
        st.session_state["active_package_code"] = sel_code
        st.session_state["active_package_name"] = sel_name
        st.session_state["active_company_id"]   = sel_company_id
        st.session_state["active_company_name"] = sel_company_name
        for k in ["step","config","parse_result","validation","merged_result","axe_c_result","saved_session_id"]:
            st.session_state[k] = 1 if k == "step" else ({} if k == "config" else None)
        st.switch_page("pages/2_Sessions_Integration.py")