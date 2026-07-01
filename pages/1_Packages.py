"""
Page Packages — Liste des packages de configuration BC pour le client actif.
Reproduit la vue BC : Code · Nom · Nb tables · Nb enregistrements · Nb erreurs.
"""
import streamlit as st
from app.db.packages_db import get_packages, create_package, delete_package

st.set_page_config(
    page_title="Packages — BC Quality Control",
    page_icon="📦",
    layout="wide",
)

# ── Guard : client actif requis ───────────────────────────────────────────────
active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")

if not active_client:
    st.warning("⚠️ Sélectionnez un client depuis le menu latéral.")
    st.stop()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.pkg-table { width:100%; border-collapse:collapse; font-size:.88rem; }
.pkg-table th {
    background:#F8FAFC; color:#475569; font-weight:600;
    padding:.6rem .8rem; text-align:left; border-bottom:2px solid #E2E8F0;
    white-space:nowrap;
}
.pkg-table td {
    padding:.55rem .8rem; border-bottom:1px solid #F1F5F9;
    vertical-align:middle;
}
.pkg-table tr:hover td { background:#F8FAFC; }
.badge-code {
    background:#EEF4FD; color:#1B3A6B; font-weight:700;
    padding:.2rem .6rem; border-radius:4px; font-size:.82rem;
    font-family:monospace;
}
.badge-error { color:#993C1D; font-weight:600; }
.badge-ok    { color:#0F6E56; }
.section-header {
    background:#EEF4FD; border-left:4px solid #2E6FBF;
    padding:.5rem 1rem; border-radius:4px;
    font-weight:600; color:#1B3A6B; margin-bottom:1rem;
}
</style>
""", unsafe_allow_html=True)

# ── En-tête ───────────────────────────────────────────────────────────────────
st.markdown(f"# 📦 Packages — {active_client_name}")
st.caption(f"Client : **{active_client_name}** ({active_client})")
st.markdown("---")

# ── Init états ────────────────────────────────────────────────────────────────
for k, v in [
    ("show_new_pkg", False),
    ("confirm_delete_pkg", None),
    ("pkg_import_id", None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Toolbar ───────────────────────────────────────────────────────────────────
col_btn1, col_btn2, _ = st.columns([2, 2, 6])
with col_btn1:
    if st.button("➕ Nouveau package", use_container_width=True):
        st.session_state["show_new_pkg"] = not st.session_state["show_new_pkg"]
        st.rerun()

# ── Formulaire nouveau package ────────────────────────────────────────────────
if st.session_state["show_new_pkg"]:
    st.markdown('<div class="section-header">Nouveau package</div>', unsafe_allow_html=True)
    f1, f2 = st.columns(2)
    with f1:
        new_code = st.text_input("Code *", placeholder="PK001", max_chars=10)
        new_name = st.text_input("Nom du package *", placeholder="MDD - Vente")
    with f2:
        new_nb_tables = st.number_input("Nombre de tables", min_value=0, value=0)

    fa, fb, _ = st.columns([2, 2, 6])
    with fa:
        if st.button("💾 Créer", type="primary", use_container_width=True):
            if not new_code.strip() or not new_name.strip():
                st.error("Code et Nom obligatoires.")
            else:
                ok, res = create_package({
                    "client_code": active_client,
                    "code":        new_code.strip(),
                    "nom_package": new_name.strip(),
                    "nb_tables":   new_nb_tables,
                })
                if ok:
                    st.success("✅ Package créé.")
                    st.session_state["show_new_pkg"] = False
                    st.rerun()
                else:
                    st.error(f"❌ {res}")
    with fb:
        if st.button("Annuler", use_container_width=True):
            st.session_state["show_new_pkg"] = False
            st.rerun()
    st.markdown("---")

# ── Liste des packages ────────────────────────────────────────────────────────
packages = get_packages(active_client)

if not packages:
    st.info("Aucun package configuré pour ce client. Cliquez sur **➕ Nouveau package** pour commencer.")
else:
    st.markdown(f"**{len(packages)} package(s)**")

    # En-tête tableau
    st.markdown("""
<table class="pkg-table">
<thead><tr>
    <th>Code</th>
    <th>Nom package</th>
    <th style="text-align:center">Nb tables</th>
    <th style="text-align:center">Nb enregistrements</th>
    <th style="text-align:center">Nb erreurs</th>
    <th>Actions</th>
</tr></thead>
</table>
""", unsafe_allow_html=True)

    for pkg in packages:
        pkg_id   = pkg["id"]
        err_cls  = "badge-error" if pkg.get("nb_errors", 0) > 0 else "badge-ok"
        err_val  = pkg.get("nb_errors", 0)

        col_code, col_name, col_t, col_r, col_e, col_act = st.columns(
            [1.2, 3, 1.2, 1.8, 1.2, 2.5]
        )
        with col_code:
            st.markdown(
                f'<span class="badge-code">{pkg.get("code","")}</span>',
                unsafe_allow_html=True,
            )
        with col_name:
            st.markdown(f'<span style="font-weight:500">{pkg.get("nom_package","")}</span>', unsafe_allow_html=True)
        with col_t:
            st.markdown(f'<div style="text-align:center">{pkg.get("nb_tables",0)}</div>', unsafe_allow_html=True)
        with col_r:
            st.markdown(f'<div style="text-align:center">{pkg.get("nb_records",0)}</div>', unsafe_allow_html=True)
        with col_e:
            st.markdown(
                f'<div style="text-align:center" class="{err_cls}">{err_val}</div>',
                unsafe_allow_html=True,
            )
        with col_act:
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("📥 Importer", key=f"imp_{pkg_id}", use_container_width=True, type="primary"):
                    # Pré-sélectionner ce package pour la session d'intégration
                    st.session_state["active_package_id"]   = pkg_id
                    st.session_state["active_package_code"] = pkg.get("code", "")
                    st.session_state["active_package_name"] = pkg.get("nom_package", "")
                    st.session_state["active_page"]         = "sessions"
                    # Réinitialiser le wizard session
                    for k in ["step", "config", "parse_result", "validation",
                              "merged_result", "axe_c_result", "saved_session_id"]:
                        st.session_state[k] = 1 if k == "step" else ({} if k == "config" else None)
                    st.switch_page(f"ses_{active_client}")
            with a2:
                if st.button("🗑️", key=f"del_{pkg_id}", use_container_width=True):
                    st.session_state["confirm_delete_pkg"] = pkg_id
                    st.rerun()
            with a3:
                pass  # Espace pour actions futures

        # Confirmation suppression
        if st.session_state.get("confirm_delete_pkg") == pkg_id:
            st.warning(f"⚠️ Supprimer **{pkg.get('nom_package','')}** ? Cette action est irréversible.")
            dy, dn, _ = st.columns([2, 2, 6])
            with dy:
                if st.button("✅ Confirmer", key=f"dcy_{pkg_id}", type="primary"):
                    ok, err = delete_package(pkg_id)
                    if ok:
                        st.success("Supprimé.")
                        st.session_state["confirm_delete_pkg"] = None
                        st.rerun()
                    else:
                        st.error(err)
            with dn:
                if st.button("❌ Annuler", key=f"dcn_{pkg_id}"):
                    st.session_state["confirm_delete_pkg"] = None
                    st.rerun()

        st.markdown(
            "<hr style='border:none;border-top:1px solid #F1F5F9;margin:.1rem 0'>",
            unsafe_allow_html=True,
        )
