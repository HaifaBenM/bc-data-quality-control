import streamlit as st
import pandas as pd
from app.db.profiles_db import get_profile_by_code
from app.db.package_visibility_db import (
    get_visibility_map, set_visibility,
    filter_visible_packages, is_first_export, mark_exported,
)
from app.core.bc_api import (
    get_access_token, get_companies,
    get_config_packages_for_company, build_tables_data_for_export,
)
from app.core.excel_exporter import generate_package_template
from app.core.auth import require_role, is_consultant

st.set_page_config(
    page_title="Packages — BC Quality Control",
    page_icon="📦",
    layout="wide",
)

require_role()

# ── Guard ─────────────────────────────────────────────────────────────────────
active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")


# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.vis-row {
    display:flex; align-items:center; justify-content:space-between;
    padding:.4rem .75rem; border-radius:6px; margin:.2rem 0;
    background:white; border:1px solid #F1F5F9;
}
.vis-code {
    font-family:monospace; font-weight:700; font-size:.82rem;
    background:#EEF4FD; color:#1B3A6B;
    padding:.1rem .4rem; border-radius:3px;
}
.vis-name { font-size:.88rem; color:#334155; }
.vis-hidden { opacity:.5; }
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
col_soc, col_refresh, col_export = st.columns([4, 1.2, 1.8])

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

# ── Packages BC (cache 5 min) ─────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _packages(tid, env, cid, _tok):
    return get_config_packages_for_company(tid, env, cid, _tok)

with st.spinner("Chargement des packages..."):
    try:
        all_packages = _packages(tenant_id, environment, sel_company_id, token)
    except Exception as e:
        st.error(f"{e}")
        st.stop()

if not all_packages:
    st.info("Aucun package dans cette société.")
    st.stop()

# ── Onglets Consultant ────────────────────────────────────────────────────────
tab_list, tab_visiblity = st.tabs(["📋 Liste", "👁 Visibilité client"])

# ════════════════════════════════════════════════════════════════════════════
# ONGLET 1 — LISTE DES PACKAGES
# ════════════════════════════════════════════════════════════════════════════
with tab_list:
    st.caption(
        f"**{len(all_packages)} package(s)** · "
        f"Environnement : `{environment}` · Société : `{sel_company_name}`"
    )

    df = pd.DataFrame([
        {
            "Code":        p.get("code", ""),
            "Nom package": p.get("packageName", ""),
            "Nb tables":   p.get("numberOfTables", 0),
            "Nb erreurs":  p.get("numberOfErrors", 0),
        }
        for p in all_packages
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
            "Nb tables":   st.column_config.NumberColumn("Nb tables", width="small"),
            "Nb erreurs":  st.column_config.NumberColumn("Nb erreurs",width="small"),
        },
    )

    # ── Sélection ─────────────────────────────────────────────────────────────
    sel_rows = event.selection.rows if event and event.selection else []
    has_sel  = len(sel_rows) > 0

    if has_sel:
        idx      = sel_rows[0]
        sel_pkg  = all_packages[idx]
        sel_code = sel_pkg.get("code", "")
        sel_name = sel_pkg.get("packageName", "")
        sel_id   = sel_pkg.get("id", "")

        st.markdown(
            f'<div style="background:#EEF4FD;border:1px solid #BFDBFE;border-radius:6px;'
            f'padding:.5rem 1rem;font-size:.88rem;color:#1B3A6B;margin:.5rem 0">'
            f'Sélectionné : <b style="font-family:monospace">{sel_code}</b>'
            f' — {sel_name}</div>',
            unsafe_allow_html=True,
        )

    # ── Bouton Exporter / Sessions ─────────────────────────────────────────────
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
            st.switch_page(f"ses_{active_client}")

    # ── Panel d'export ────────────────────────────────────────────────────────
    if do_export and has_sel:
        st.session_state["export_pkg"] = sel_pkg

    if st.session_state.get("export_pkg") and has_sel:
        ep = st.session_state["export_pkg"]
        if ep.get("code") != sel_code:
            st.session_state.pop("export_pkg", None)
            st.rerun()

        st.markdown('<div class="export-panel">', unsafe_allow_html=True)
        st.markdown(f"### Options d'export — `{sel_code}`")

        first_time = is_first_export(active_client, sel_code)

        c1, c2, c3 = st.columns(3)
        with c1:
            inc_desc = st.checkbox(
                "Inclure les descriptions", value=True, key="exp_desc"
            )
        with c2:
            inc_ex = st.checkbox(
                "Inclure les exemples",
                value=first_time,
                key="exp_ex",
                help="Coché automatiquement pour le premier export.",
            )
        with c3:
            inc_custom = st.checkbox(
                "Champs personnalisés", value=True, key="exp_custom",
                help="Champs ajoutés par extensions (No. ≥ 50000).",
            )

        role = st.radio(
            "Vue",
            ["Consultant", "Client"],
            horizontal=True,
            key="exp_role",
            help=(
                "Client : champs obligatoires + références uniquement.\n"
                "Consultant : tous les champs inclus dans le package."
            ),
        )

        if st.button("⚙ Générer le fichier", type="primary", key="btn_gen"):
            with st.spinner("Interrogation BC + génération Excel..."):
                try:
                    tables_data = build_tables_data_for_export(
                        tenant_id, environment, sel_company_id, ep, token
                    )
                    options = {
                        "include_descriptions":  inc_desc,
                        "include_examples":      inc_ex,
                        "include_custom_fields": inc_custom,
                        "role":                  role.lower(),
                    }
                    excel_bytes = generate_package_template(ep, tables_data, options)
                    st.session_state["excel_ready"]      = excel_bytes
                    st.session_state["excel_pkg_code"]   = sel_code
                    st.session_state["excel_role"]       = role.lower()
                    mark_exported(active_client, sel_code)
                except Exception as err:
                    st.error(f"Erreur lors de la génération : {err}")

        if st.session_state.get("excel_ready") and \
                st.session_state.get("excel_pkg_code") == sel_code:
            role_suffix = "_client" if st.session_state.get("excel_role") == "client" else ""
            st.download_button(
                label="📥 Télécharger le template",
                data=st.session_state["excel_ready"],
                file_name=f"{sel_code}{role_suffix}_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# ONGLET 2 — VISIBILITÉ CLIENT (consultant uniquement)
# ════════════════════════════════════════════════════════════════════════════
if is_consultant():
    with tab_visiblity:
        st.caption(
            "Configurez quels packages sont visibles pour ce client. "
            "Les packages masqués n'apparaissent pas dans la vue client."
        )

        vis_map = get_visibility_map(active_client)
        changed = False

        for pkg in all_packages:
            code       = pkg.get("code", "")
            name       = pkg.get("packageName", "")
            is_visible = vis_map.get(code, True)

            col_info, col_toggle = st.columns([5, 1])
            with col_info:
                opacity = "" if is_visible else " vis-hidden"
                st.markdown(
                    f'<div class="vis-row{opacity}">'
                    f'<span><span class="vis-code">{code}</span> '
                    f'<span class="vis-name">{name}</span></span>'
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
                    set_visibility(active_client, code, new_val)
                    changed = True

        if changed:
            st.success("Visibilité mise à jour.")
            st.rerun()
