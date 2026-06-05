"""
Page Profils Clients — Sprint 2.
Gestion des profils clients et accès aux règles métier.
"""
import streamlit as st
from app.db.supabase_client import test_connection
from app.db.profiles_db import (
    get_all_profiles, create_profile, delete_profile,
    get_profile_stats, get_profiles_for_select
)
from app.db.rules_db import copy_rules_to_profile

st.set_page_config(
    page_title="Profils Clients — BC Quality Control",
    page_icon="👥",
    layout="wide"
)

st.markdown("""
<style>
    .profile-card {
        background: white; border: 1px solid #E2E8F0;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 10px;
    }
    .profile-name { font-size: 15px; font-weight: 600; color: #1B3A6B; margin: 0; }
    .profile-code { font-size: 12px; color: #64748B; margin: 2px 0 0; }
    .badge {
        display: inline-block; font-size: 11px; font-weight: 500;
        padding: 2px 8px; border-radius: 12px; margin-right: 6px;
    }
    .badge-rules    { background: #E1F5EE; color: #0F6E56; }
    .badge-sector   { background: #EFF6FF; color: #2E6FBF; }
    .badge-no-rules { background: #FEF3C7; color: #92400E; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 👥 Profils Clients")
st.markdown("Gérez les profils clients et leurs règles métier associées.")
st.markdown("---")

connected, msg = test_connection()
if not connected:
    st.error(f"❌ Base de données non connectée : {msg}")
    st.stop()

if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = None

tab1, tab2 = st.tabs(["👥 Mes profils", "➕ Nouveau profil"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LISTE
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    profiles = get_all_profiles()

    if not profiles:
        st.info(
            "Aucun profil client créé. "
            "Utilisez l'onglet **'Nouveau profil'** pour commencer."
        )
    else:
        st.markdown(f"**{len(profiles)} profil(s) client(s)**")
        st.markdown("---")

        for profile in profiles:
            code  = profile.get("code", "")
            stats = get_profile_stats(code)

            col_info, col_actions = st.columns([7, 3])

            with col_info:
                sector   = profile.get("sector", "")
                nb_rules = stats["total_rules"]
                nb_active = stats["active_rules"]

                sector_badge = (
                    f'<span class="badge badge-sector">{sector}</span>'
                    if sector else ""
                )
                rules_badge = (
                    f'<span class="badge badge-rules">{nb_active} règle(s) active(s)</span>'
                    if nb_rules > 0
                    else '<span class="badge badge-no-rules">Aucune règle</span>'
                )

                st.markdown(
                    f'<div class="profile-card">'
                    f'<p class="profile-name">{profile.get("name", "")}</p>'
                    f'<p class="profile-code">Code : {code}</p>'
                    f'<div style="margin-top:8px">{sector_badge}{rules_badge}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            with col_actions:
                st.markdown("<div style='padding-top:12px'>", unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("⚙️ Règles", key=f"rules_{code}",
                                 use_container_width=True):
                        st.session_state["selected_profile_for_rules"] = code
                        st.switch_page("pages/4_Regles_Metier.py")
                with c2:
                    if st.button("🗑️", key=f"del_{code}",
                                 use_container_width=True):
                        st.session_state.confirm_delete = code
                st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.confirm_delete == code:
                st.warning(
                    f"⚠️ Supprimer **{profile.get('name', '')}** ? "
                    "Toutes ses règles seront supprimées."
                )
                c_yes, c_no, _ = st.columns([2, 2, 6])
                with c_yes:
                    if st.button("✅ Confirmer", key=f"yes_{code}", type="primary"):
                        ok, err = delete_profile(code)
                        if ok:
                            st.success("Profil supprimé.")
                            st.session_state.confirm_delete = None
                            st.rerun()
                        else:
                            st.error(err)
                with c_no:
                    if st.button("❌ Annuler", key=f"no_{code}"):
                        st.session_state.confirm_delete = None
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — NOUVEAU PROFIL
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    st.markdown("### Créer un nouveau profil client")
    st.caption(
        "Un profil regroupe les informations d'un client et ses règles métier. "
        "Il sera sélectionnable dans les sessions de contrôle."
    )
    st.markdown("---")

    with st.form("create_profile_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            new_code = st.text_input(
                "Code client *",
                placeholder="Ex: CLT-ABC-001",
                help="Identifiant unique."
            )
            new_name = st.text_input(
                "Nom client *",
                placeholder="Ex: ABC Distribution SARL"
            )
            new_sector = st.text_input(
                "Secteur d'activité",
                placeholder="Ex: Distribution B2B"
            )

        with col2:
            new_bc_url = st.text_input(
                "URL environnement BC",
                placeholder="https://abc.businesscentral.dynamics.com"
            )
            new_language = st.selectbox(
                "Langue des données",
                ["Français", "Anglais", "Arabe", "Autre"],
                help="Aide l'IA pour les suggestions de correction."
            )

        new_notes = st.text_area("Notes projet", height=80,
                                 placeholder="Contexte, ancien système...")

        # Copier les règles d'un profil existant
        profiles_for_copy = get_profiles_for_select()
        copy_from = None
        if profiles_for_copy:
            st.markdown("---")
            options_copy = ["— Ne pas copier de règles —"] + [
                p["label"] for p in profiles_for_copy
            ]
            copy_choice = st.selectbox(
                "Copier les règles depuis un profil existant (optionnel)",
                options_copy
            )
            if copy_choice != "— Ne pas copier de règles —":
                copy_from = next(
                    (p["code"] for p in profiles_for_copy
                     if p["label"] == copy_choice),
                    None
                )

        submitted = st.form_submit_button(
            "💾 Créer le profil",
            type="primary",
            use_container_width=True
        )

        if submitted:
            errors = []
            if not new_code.strip():
                errors.append("Le code client est obligatoire.")
            if not new_name.strip():
                errors.append("Le nom client est obligatoire.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                profile_data = {
                    "code":          new_code.strip().upper(),
                    "name":          new_name.strip(),
                    "sector":        new_sector.strip(),
                    "bc_url":        new_bc_url.strip(),
                    "data_language": new_language,
                    "notes":         new_notes.strip(),
                }
                ok, err = create_profile(profile_data)
                if ok:
                    st.success(
                        f"✅ Profil **{new_name}** ({new_code.upper()}) créé !"
                    )
                    if copy_from:
                        ok_c, msg_c, nb = copy_rules_to_profile(
                            copy_from, new_code.strip().upper()
                        )
                        if ok_c:
                            st.info(f"📋 {msg_c}")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ {err}")
