"""
Page Packages — Liste des Configuration Packages lus directement depuis BC.
Aucune saisie manuelle : la liste vient de l'environnement BC du client.
"""
import streamlit as st
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import get_config_packages

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
.pkg-header {
    display:grid;
    grid-template-columns: 100px 1fr 100px 140px 100px 120px;
    gap:.5rem; padding:.5rem .75rem;
    background:#F8FAFC; border-bottom:2px solid #E2E8F0;
    font-size:.8rem; font-weight:600; color:#64748B;
}
.pkg-row {
    display:grid;
    grid-template-columns: 100px 1fr 100px 140px 100px 120px;
    gap:.5rem; padding:.55rem .75rem;
    border-bottom:1px solid #F1F5F9;
    align-items:center; font-size:.88rem;
}
.pkg-row:hover { background:#F8FAFC; }
.badge-code {
    background:#EEF4FD; color:#1B3A6B; font-weight:700;
    padding:.2rem .5rem; border-radius:4px;
    font-family:monospace; font-size:.82rem;
}
.badge-error { color:#993C1D; font-weight:600; }
.badge-ok    { color:#64748B; }
.num         { text-align:center; }
</style>
""", unsafe_allow_html=True)

# ── En-tête ───────────────────────────────────────────────────────────────────
st.markdown(f"# 📦 Packages — {active_client_name}")
st.caption(f"Client : **{active_client_name}** ({active_client}) — Source : environnement BC")
st.markdown("---")

# ── Chargement profil BC ──────────────────────────────────────────────────────
profile = get_profile_by_code(active_client)

if not profile:
    st.error("Profil client introuvable. Vérifiez dans Profils Clients.")
    st.stop()

missing = [
    f for f in ["bc_tenant_id", "bc_client_id", "bc_client_secret",
                "bc_environment", "bc_company_id"]
    if not profile.get(f, "").strip()
]
if missing:
    st.error(
        f"Credentials BC manquants dans le profil : **{', '.join(missing)}**\n\n"
        "Allez dans **Profils Clients** pour compléter la configuration BC."
    )
    st.stop()

# ── Chargement packages BC (avec cache 5 min) ─────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_packages(client_code: str, env: str) -> tuple:
    """
    Cache par (client_code, env) — TTL 5 min.
    company_id est résolu automatiquement si non renseigné.
    """
    return get_config_packages(profile)

col_title, col_refresh = st.columns([8, 2])
with col_refresh:
    if st.button("🔄 Rafraîchir", use_container_width=True):
        _load_packages.clear()
        st.rerun()

with st.spinner("⏳ Chargement des packages depuis BC..."):
    try:
        packages, company_display = _load_packages(
            active_client,
            profile.get("bc_environment", ""),
        )
    except Exception as e:
        st.error(f"❌ Impossible de charger les packages BC\n\n{e}")
        st.stop()

# ── Affichage liste ───────────────────────────────────────────────────────────
if not packages:
    st.info(
        f"Aucun package de configuration trouvé dans "
        f"**{profile.get('bc_environment')}** / "
        f"**{profile.get('bc_company_name', active_client)}**."
    )
    st.stop()

st.markdown(f"**{len(packages)} package(s) de configuration**")
st.caption(
    f"Environnement : `{profile.get('bc_environment')}` · "
    f"Société : `{company_display}`"
)
st.markdown("---")

# En-tête colonnes
st.markdown("""
<div class="pkg-header">
    <div>Code</div>
    <div>Nom package</div>
    <div class="num">Ordre</div>
    <div class="num">Nb tables</div>
    <div class="num">Nb erreurs</div>
    <div></div>
</div>
""", unsafe_allow_html=True)

for pkg in packages:
    code      = pkg.get("code", "")
    name      = pkg.get("packageName", "")
    order     = pkg.get("processingOrder", 0)
    nb_tables = pkg.get("numberOfTables", 0)
    nb_errors = pkg.get("numberOfErrors", 0)
    err_cls   = "badge-error" if nb_errors > 0 else "badge-ok"

    col_code, col_name, col_ord, col_tbl, col_err, col_act = st.columns(
        [1.2, 3.5, 1, 1.5, 1, 1.5]
    )

    with col_code:
        st.markdown(
            f'<span class="badge-code">{code}</span>',
            unsafe_allow_html=True,
        )
    with col_name:
        st.markdown(
            f'<span style="font-weight:500;color:#1E293B">{name}</span>',
            unsafe_allow_html=True,
        )
    with col_ord:
        st.markdown(
            f'<div class="num" style="color:#94A3B8">{order}</div>',
            unsafe_allow_html=True,
        )
    with col_tbl:
        st.markdown(
            f'<div class="num">{nb_tables}</div>',
            unsafe_allow_html=True,
        )
    with col_err:
        st.markdown(
            f'<div class="num {err_cls}">{nb_errors}</div>',
            unsafe_allow_html=True,
        )
    with col_act:
        if st.button(
            "📥 Importer",
            key=f"imp_{code}",
            use_container_width=True,
            type="primary",
        ):
            # Pré-charger le contexte package pour la session
            st.session_state["active_package_code"] = code
            st.session_state["active_package_name"] = name
            # Réinitialiser le wizard Sessions
            for k in ["step", "config", "parse_result", "validation",
                      "merged_result", "axe_c_result", "saved_session_id"]:
                st.session_state[k] = 1 if k == "step" else ({} if k == "config" else None)
            st.switch_page(f"ses_{active_client}")

    st.markdown(
        "<hr style='border:none;border-top:1px solid #F1F5F9;margin:.05rem 0'>",
        unsafe_allow_html=True,
    )
