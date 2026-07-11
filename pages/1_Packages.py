import streamlit as st
import pandas as pd
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import (
    get_access_token, get_companies,
    get_config_packages_for_company,
    get_packages_qc,
)
from app.core.bc_excel_processor import validate_bc_excel, clear_bc_excel_data, extract_sheets_info
from app.db.excel_template_db import (
    save_excel_template, get_excel_template,
    has_excel_template, delete_excel_template,
)
from app.core.auth import require_role, is_consultant
from app.core.bc_api import build_tables_data_for_export


# ── Générateur Excel template ─────────────────────────────────────────────────
def _reinject_bc_xml(excel_bytes: bytes, xml_files: dict) -> bytes:
    """Ré-injecte les fichiers XML BC dans un Excel généré par openpyxl."""
    import re as _re
    _BC_FILES_SET = {"xl/xmlMaps.xml", "xl/connections.xml"}
    _BC_RELS_TYPES = {"xmlMaps", "connections"}

    extra_rels, extra_ct = [], []
    orig_rels = xml_files.get("xl/_rels/workbook.xml.rels", b"").decode("utf-8", errors="replace")
    orig_ct   = xml_files.get("[Content_Types].xml", b"").decode("utf-8", errors="replace")

    for tag in _re.findall(r'<Relationship[^/]*/>', orig_rels):
        if any(t in tag for t in _BC_RELS_TYPES):
            extra_rels.append(tag)
    for tag in _re.findall(r'<Override[^/]*/>', orig_ct):
        if "xmlMaps" in tag or "connections" in tag.lower():
            extra_ct.append(tag)

    in_buf, out_buf = io.BytesIO(excel_bytes), io.BytesIO()
    with zipfile.ZipFile(in_buf) as zin:
        existing = set(zin.namelist())
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "xl/_rels/workbook.xml.rels" and extra_rels:
                    s = data.decode("utf-8", errors="replace")
                    inserts = [r for r in extra_rels if r.split('Type="')[1].split('"')[0].split("/")[-1] not in s]
                    if inserts:
                        s = s.replace("</Relationships>", "\n".join(inserts) + "\n</Relationships>")
                    data = s.encode("utf-8")
                elif item.filename == "[Content_Types].xml" and extra_ct:
                    s = data.decode("utf-8", errors="replace")
                    inserts = [o for o in extra_ct if o.split('PartName="')[1].split('"')[0] not in s]
                    if inserts:
                        s = s.replace("</Types>", "\n".join(inserts) + "\n</Types>")
                    data = s.encode("utf-8")
                zout.writestr(item, data)
            for fname, fdata in xml_files.items():
                if fname.startswith("xl/xml") or fname.startswith("xl/conn"):
                    if fname not in existing:
                        zout.writestr(fname, fdata)
    return out_buf.getvalue()

_EXAMPLES = {
    18: {"N°": ["CLI-001","CLI-002"], "Nom": ["Société Test","Client Exemple"]},
    23: {"N°": ["FRN-001","FRN-002"], "Nom": ["Fournisseur Test","Autre Fournisseur"]},
    27: {"N°": ["ART-001","ART-002"], "Description": ["Article Test 1","Article Test 2"]},
}
_TYPE_EX = {"Code":"EX-001","Text":"Exemple","Decimal":"0.00","Integer":"0","Date":"01/01/2025","Boolean":"Non"}


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
    if st.button("🔄 Rafraîchir", width='stretch'):
        st.cache_data.clear()
        st.rerun()

# ── Chargement packages ───────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _pkgs_automation(tid, env, cid, _tok):
    """Tous les packages depuis Automation API (données complètes)."""
    return get_config_packages_for_company(tid, env, cid, _tok)

@st.cache_data(ttl=300, show_spinner=False)
def _pkgs_qc(tid, env, cid, _tok, visible_only):
    """Packages depuis extension Talan QC (avec flag visibilité)."""
    return get_packages_qc(tid, env, cid, _tok, visible_only=visible_only)

with st.spinner("Chargement des packages..."):
    try:
        # Automation API → données complètes (nb tables, nb erreurs)
        all_pkgs_full = _pkgs_automation(
            tenant_id, environment, sel_company_id, token
        )
        # Custom Talan QC → flags de visibilité
        qc_pkgs = _pkgs_qc(
            tenant_id, environment, sel_company_id, token, False
        )
        vis_map = {p["code"]: p.get("qcVisibleClient", False) for p in qc_pkgs}
        # Merge : injecter qcVisibleClient dans les données complètes
        for pkg in all_pkgs_full:
            pkg["qcVisibleClient"] = vis_map.get(pkg.get("code", ""), False)

        # Consultant ET client : uniquement les packages visibles
        displayed_packages = [
            p for p in all_pkgs_full if p.get("qcVisibleClient", False)
        ]
        # all_packages_qc pour l'onglet visibilité (tous les packages)
        all_packages_qc = all_pkgs_full

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
    # Même colonnes pour consultant et client (nb tables + nb erreurs)
    df = pd.DataFrame([{
        "Code":        p.get("code", ""),
        "Nom package": p.get("packageName", ""),
        "Nb tables":   p.get("numberOfTables", 0),
        "Nb erreurs":  p.get("numberOfErrors", 0),
    } for p in displayed_packages])
    col_cfg = {
        "Code":        st.column_config.TextColumn(width="small"),
        "Nom package": st.column_config.TextColumn(width="large"),
        "Nb tables":   st.column_config.NumberColumn(width="small"),
        "Nb erreurs":  st.column_config.NumberColumn(width="small"),
    }

    event = st.dataframe(
        df,
        width='stretch',
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
            width='stretch',
            type="primary",
        )

    with col_ses:
        if st.button(
            "📁 Importer dans Sessions",
            disabled=not has_sel,
            width='stretch',
        ):
            st.session_state["active_package_code"]   = sel_code
            st.session_state["active_package_name"]   = sel_name
            st.session_state["active_company_id"]     = sel_company_id
            st.session_state["active_company_name"]   = sel_company_name
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
        st.markdown(f"### `{sel_code}` — {sel_name}")

        tpl_ok = has_excel_template(active_client, sel_code)

        if not tpl_ok:
            st.warning(
                "Template non configuré pour ce package. "
                "Exportez le package depuis BC (**Exporter vers Excel** "
                "sur la fiche package), puis uploadez-le ici."
            )
            uploaded_tpl = st.file_uploader(
                f"Fichier BC — {sel_code}",
                type=["xlsx"], key="tpl_upload",
            )
            if uploaded_tpl:
                raw = uploaded_tpl.read()
                ok_val, err_val = validate_bc_excel(raw)
                if not ok_val:
                    st.error(f"❌ {err_val}")
                else:
                    si = extract_sheets_info(raw)
                    ok_save, err_save = save_excel_template(
                        active_client, sel_code, raw, si
                    )
                    if ok_save:
                        n_sheets = len([s for s in si if s.get("table_id")])
                        st.success(
                            f"✅ Template configuré — {n_sheets} onglet(s) : "
                            f"{', '.join(s['sheet_name'] for s in si if s.get('table_id'))}"
                        )
                        st.rerun()
                    else:
                        st.error(f"Erreur : {err_save}")
        else:
            tpl_bytes, _ = get_excel_template(active_client, sel_code)
            if tpl_bytes:
                st.success("Template configuré — prêt à télécharger.")
                col_dl, col_del = st.columns([3, 1])
                with col_dl:
                    st.download_button(
                        label="📥 Télécharger le template",
                        data=tpl_bytes,
                        file_name=f"{sel_code}_template.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width='stretch',
                        type="primary",
                    )
                with col_del:
                    if st.button("🔄 Reconfigurer", width='stretch'):
                        delete_excel_template(active_client, sel_code)
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
