import streamlit as st
import pandas as pd
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import (
    get_access_token, get_companies,
    get_config_packages_for_company,
    get_packages_qc, set_package_visibility_bc,
    build_tables_data_for_export,
)
from app.core.excel_exporter import generate_package_template
from app.core.auth import require_role, is_consultant

st.set_page_config(
    page_title="Packages — BC Quality Control",
    page_icon="📦",
    layout="wide",
)

require_role()

# ── Contexte ──────────────────────────────────────────────────────────────────
active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.vis-row {
    display:flex; align-items:center; justify-content:space-between;
    padding:.45rem .75rem; border-radius:6px; margin:.2rem 0;
    background:white; border:1px solid #F1F5F9; font-size:.88rem;
}
.vis-code {
    font-family:monospace; font-weight:700; font-size:.82rem;
    background:#EEF4FD; color:#1B3A6B;
    padding:.1rem .4rem; border-radius:3px; margin-right:.5rem;
}
.vis-hidden { opacity:.45; }
.export-panel {
    background:#F8FAFC; border:1px solid #E2E8F0;
    border-radius:8px; padding:1.25rem 1.5rem; margin-top:1rem;
}
</style>
""", unsafe_allow_html=True)

# ── En-tête ───────────────────────────────────────────────────────────────────
st.markdown(f"# 📦 Packages — {active_client_name}")
st.markdown("---")

# ── Profil BC ─────────────────────────────────────────────────────────────────
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

# ── Token BC (cache 55 min) ───────────────────────────────────────────────────
@st.cache_data(ttl=3300, show_spinner=False)
def _token(tid, cid, cs):
    return get_access_token(tid, cid, cs)

try:
    token = _token(tenant_id, client_id_bc, client_secret)
except Exception as e:
    st.error(f"Authentification BC échouée : {e}")
    st.stop()

# ── Sociétés (cache 10 min) ───────────────────────────────────────────────────
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

# ── Toolbar ───────────────────────────────────────────────────────────────────
company_opts = {
    c.get("displayName") or c.get("name", c["id"]): c["id"]
    for c in companies
}
col_soc, col_refresh = st.columns([5, 1])
with col_soc:
    sel_company_name = st.selectbox(
        "Société", list(company_opts.keys()),
        label_visibility="collapsed",
    )
    sel_company_id = company_opts[sel_company_name]
with col_refresh:
    if st.button("🔄 Rafraîchir", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Chargement packages ───────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _pkgs_automation(tid, env, cid, _tok):
    """Tous les packages depuis Automation API (consultant)."""
    return get_config_packages_for_company(tid, env, cid, _tok)

@st.cache_data(ttl=300, show_spinner=False)
def _pkgs_qc(tid, env, cid, _tok, visible_only):
    """Packages depuis extension Talan QC (avec flag visibilité)."""
    return get_packages_qc(tid, env, cid, _tok, visible_only=visible_only)

with st.spinner("Chargement des packages..."):
    try:
        if is_consultant():
            # Automation API → données complètes (nb tables, nb erreurs)
            all_packages = _pkgs_automation(
                tenant_id, environment, sel_company_id, token
            )
            # Extension Talan QC → flags de visibilité
            qc_packages = _pkgs_qc(
                tenant_id, environment, sel_company_id, token, False
            )
            vis_map = {p["code"]: p.get("qcVisibleClient", False) for p in qc_packages}
            for pkg in all_packages:
                pkg["qcVisibleClient"] = vis_map.get(pkg.get("code", ""), False)
            displayed_packages = all_packages

        else:
            # Client : extension Talan QC filtrée côté BC (visible_only=True)
            displayed_packages = _pkgs_qc(
                tenant_id, environment, sel_company_id, token, True
            )

    except Exception as e:
        err = str(e)
        if "talan/qctools" in err or "404" in err:
            st.error(
                "L'extension **Talan QC Tools** n'est pas déployée sur cet environnement.\n\n"
                "Déployez le fichier `talan-qctools.app` via BC Admin Center."
            )
        else:
            st.error(f"Erreur chargement packages : {e}")
        st.stop()

if not displayed_packages:
    st.info("Aucun package disponible.")
    st.stop()

# ── Onglets (consultant : Liste + Visibilité / client : Liste seule) ──────────
if is_consultant():
    tab_list, tab_vis = st.tabs(["📋 Liste", "👁 Visibilité client"])
else:
    tab_list = st.container()

# ════════════════════════════════════════════════════════════════════════════
# ONGLET 1 — LISTE DES PACKAGES
# ════════════════════════════════════════════════════════════════════════════
with tab_list:
    st.caption(
        f"**{len(displayed_packages)} package(s)** · "
        f"Environnement : `{environment}` · Société : `{sel_company_name}`"
    )

    # Colonnes selon le rôle
    if is_consultant():
        df = pd.DataFrame([{
            "Code":           p.get("code", ""),
            "Nom package":    p.get("packageName", ""),
            "Nb tables":      p.get("numberOfTables", 0),
            "Nb erreurs":     p.get("numberOfErrors", 0),
            "Visible client": "✅" if p.get("qcVisibleClient") else "—",
        } for p in displayed_packages])
        col_cfg = {
            "Code":           st.column_config.TextColumn(width="small"),
            "Nom package":    st.column_config.TextColumn(width="large"),
            "Nb tables":      st.column_config.NumberColumn(width="small"),
            "Nb erreurs":     st.column_config.NumberColumn(width="small"),
            "Visible client": st.column_config.TextColumn(width="small"),
        }
    else:
        df = pd.DataFrame([{
            "Code":        p.get("code", ""),
            "Nom package": p.get("packageName", ""),
        } for p in displayed_packages])
        col_cfg = {
            "Code":        st.column_config.TextColumn(width="small"),
            "Nom package": st.column_config.TextColumn(width="large"),
        }

    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config=col_cfg,
    )

    sel_rows = event.selection.rows if event and event.selection else []
    has_sel  = len(sel_rows) > 0

    if has_sel:
        idx      = sel_rows[0]
        sel_pkg  = displayed_packages[idx]
        sel_code = sel_pkg.get("code", "")
        sel_name = sel_pkg.get("packageName", "")

        st.markdown(
            f'<div style="background:#EEF4FD;border:1px solid #BFDBFE;'
            f'border-radius:6px;padding:.5rem 1rem;font-size:.88rem;'
            f'color:#1B3A6B;margin:.5rem 0">'
            f'Sélectionné : <b style="font-family:monospace">{sel_code}</b>'
            f' — {sel_name}</div>',
            unsafe_allow_html=True,
        )

    # ── Boutons ───────────────────────────────────────────────────────────────
    col_exp, col_ses, _ = st.columns([2, 2, 4])

    with col_exp:
        do_export = st.button(
            "📤 Exporter en Excel",
            disabled=not has_sel,
            use_container_width=True,
            type="primary",
        )

    with col_ses:
        if st.button(
            "📁 Importer dans Sessions",
            disabled=not has_sel,
            use_container_width=True,
        ):
            st.session_state["active_package_code"] = sel_code
            st.session_state["active_package_name"] = sel_name
            for k in ["step", "config", "parse_result", "validation",
                      "merged_result", "axe_c_result", "saved_session_id"]:
                st.session_state[k] = 1 if k == "step" else (
                    {} if k == "config" else None
                )
            st.switch_page("pages/2_Sessions_Integration.py")

    # ── Panel export ──────────────────────────────────────────────────────────
    if do_export and has_sel:
        st.session_state["export_pkg"] = sel_pkg

    if st.session_state.get("export_pkg") and has_sel:
        ep = st.session_state["export_pkg"]
        if ep.get("code") != sel_code:
            st.session_state.pop("export_pkg", None)
            st.rerun()

        st.markdown('<div class="export-panel">', unsafe_allow_html=True)
        st.markdown(f"### Options d'export — `{sel_code}`")

        c1, c2, c3 = st.columns(3)
        with c1:
            inc_desc = st.checkbox("Descriptions", value=True, key="exp_desc")
        with c2:
            inc_ex = st.checkbox("Exemples", value=True, key="exp_ex")
        with c3:
            inc_custom = st.checkbox(
                "Champs personnalisés", value=True, key="exp_custom",
                help="Champs N° ≥ 50000.",
            )

        if is_consultant():
            exp_role_sel = st.radio(
                "Vue", ["Consultant", "Client"],
                horizontal=True, key="exp_role",
            )
        else:
            exp_role_sel = "Client"

        if st.button("⚙ Générer le fichier", type="primary", key="btn_gen"):
            with st.spinner("Lecture structure BC + génération Excel..."):
                try:
                    tables_data = build_tables_data_for_export(
                        tenant_id, environment, sel_company_id,
                        sel_code, token,
                    )
                    if not tables_data:
                        st.warning(
                            "Aucune table trouvée dans ce package. "
                            "Vérifiez la configuration dans BC."
                        )
                    else:
                        options = {
                            "include_descriptions":  inc_desc,
                            "include_examples":      inc_ex,
                            "include_custom_fields": inc_custom,
                            "role":                  exp_role_sel.lower(),
                        }
                        excel_bytes = generate_package_template(
                            sel_pkg, tables_data, options
                        )
                        st.session_state["excel_ready"]    = excel_bytes
                        st.session_state["excel_pkg_code"] = sel_code
                        st.session_state["excel_role"]     = exp_role_sel.lower()
                except Exception as err:
                    st.error(f"Erreur lors de la génération : {err}")

        if st.session_state.get("excel_ready") and \
                st.session_state.get("excel_pkg_code") == sel_code:
            role_sfx = "_client" if st.session_state.get("excel_role") == "client" else ""
            st.download_button(
                label="📥 Télécharger",
                data=st.session_state["excel_ready"],
                file_name=f"{sel_code}{role_sfx}_template.xlsx",
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                use_container_width=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# ONGLET 2 — VISIBILITÉ CLIENT (consultant uniquement)
# ════════════════════════════════════════════════════════════════════════════
if is_consultant():
    with tab_vis:
        st.caption(
            "Le flag est enregistré directement dans BC sur chaque package. "
            "Le client ne voit que les packages cochés ✅."
        )

        for pkg in all_packages:
            code       = pkg.get("code", "")
            name       = pkg.get("packageName", "")
            is_visible = pkg.get("qcVisibleClient", False)

            col_info, col_toggle = st.columns([5, 1])
            with col_info:
                cls = "" if is_visible else " vis-hidden"
                st.markdown(
                    f'<div class="vis-row{cls}">'
                    f'<span class="vis-code">{code}</span>{name}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col_toggle:
                new_val = st.toggle(
                    "Visible",
                    value=is_visible,
                    key=f"vis_{code}",
                    label_visibility="collapsed",
                )
                if new_val != is_visible:
                    try:
                        set_package_visibility_bc(
                            tenant_id, environment, sel_company_id,
                            code, new_val, token,
                        )
                        _pkgs_qc.clear()
                        _pkgs_automation.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur mise à jour visibilité : {e}")
