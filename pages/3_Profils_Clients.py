"""
Page Profils Clients — Sprint 2 v2.
Ajout des champs de connexion BC par client.
"""
import streamlit as st
from app.db.supabase_client import test_connection
from app.db.profiles_db import (
    get_all_profiles, create_profile, update_profile,
    delete_profile, get_profile_stats, get_profiles_for_select
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
    .badge-bc-ok    { background: #E1F5EE; color: #0F6E56; }
    .badge-bc-none  { background: #F1F5F9; color: #64748B; }
    .section-bc {
        background: #F8FAFC; border: 1px solid #E2E8F0;
        border-radius: 8px; padding: 16px; margin-top: 8px;
    }
    .section-bc-title {
        font-size: 13px; font-weight: 600; color: #1B3A6B;
        margin: 0 0 12px;
    }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 👥 Profils Clients")
st.markdown("Gérez les profils clients, leurs credentials BC et leurs règles métier.")
st.markdown("---")

connected, msg = test_connection()
if not connected:
    st.error(f"❌ Base de données non connectée : {msg}")
    st.stop()

if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = None
if "edit_profile" not in st.session_state:
    st.session_state.edit_profile = None

tab1, tab2 = st.tabs(["👥 Mes profils", "➕ Nouveau profil"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LISTE DES PROFILS
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
            code   = profile.get("code", "")
            stats  = get_profile_stats(code)
            has_bc = bool(profile.get("bc_tenant_id") and profile.get("bc_client_id"))

            col_info, col_actions = st.columns([7, 3])

            with col_info:
                sector    = profile.get("sector", "")
                nb_active = stats["active_rules"]
                nb_rules  = stats["total_rules"]

                sector_badge = (
                    f'<span class="badge badge-sector">{sector}</span>'
                    if sector else ""
                )
                rules_badge = (
                    f'<span class="badge badge-rules">'
                    f'{nb_active} règle(s) active(s)</span>'
                    if nb_rules > 0
                    else '<span class="badge badge-no-rules">Aucune règle</span>'
                )
                bc_badge = (
                    '<span class="badge badge-bc-ok">🔌 BC configuré</span>'
                    if has_bc
                    else '<span class="badge badge-bc-none">⚙️ BC non configuré</span>'
                )

                bc_url = profile.get("bc_url", "")
                bc_env = profile.get("bc_environment", "")
                bc_info = ""
                if bc_url:
                    bc_info = f'<span style="font-size:11px;color:#94A3B8">{bc_url}'
                    if bc_env:
                        bc_info += f' · {bc_env}'
                    bc_info += '</span>'

                st.markdown(
                    f'<div class="profile-card">'
                    f'<p class="profile-name">{profile.get("name", "")}</p>'
                    f'<p class="profile-code">Code : {code}</p>'
                    f'<div style="margin-top:8px">'
                    f'{sector_badge}{rules_badge}{bc_badge}'
                    f'</div>'
                    f'{"<div style=margin-top:4px>" + bc_info + "</div>" if bc_info else ""}'
                    f'</div>',
                    unsafe_allow_html=True
                )

            with col_actions:
                st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("⚙️", key=f"rules_{code}",
                                 use_container_width=True,
                                 help="Règles métier"):
                        st.session_state["selected_profile_for_rules"] = code
                        st.switch_page("pages/4_Regles_Metier.py")
                with c2:
                    if st.button("✏️", key=f"edit_{code}",
                                 use_container_width=True,
                                 help="Modifier le profil"):
                        st.session_state.edit_profile = code
                with c3:
                    if st.button("🗑️", key=f"del_{code}",
                                 use_container_width=True,
                                 help="Supprimer"):
                        st.session_state.confirm_delete = code
                st.markdown("</div>", unsafe_allow_html=True)

            # ── Formulaire de modification ─────────────────────────────────
            if st.session_state.edit_profile == code:
                with st.expander(
                    f"✏️ Modifier le profil — {profile.get('name', '')}",
                    expanded=True
                ):
                    with st.form(f"edit_form_{code}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            e_name   = st.text_input("Nom client", value=profile.get("name", ""))
                            e_sector = st.text_input("Secteur", value=profile.get("sector", ""))
                            e_lang   = st.selectbox(
                                "Langue des données",
                                ["Français", "Anglais", "Arabe", "Autre"],
                                index=["Français", "Anglais", "Arabe", "Autre"].index(
                                    profile.get("data_language", "Français")
                                ) if profile.get("data_language") in
                                ["Français", "Anglais", "Arabe", "Autre"] else 0
                            )
                        with ec2:
                            e_url = st.text_input(
                                "URL BC",
                                value=profile.get("bc_url", ""),
                                placeholder="https://abc.businesscentral.dynamics.com"
                            )
                            e_env = st.text_input(
                                "Nom de l'environnement BC",
                                value=profile.get("bc_environment", ""),
                                placeholder="Ex: Production, Sandbox"
                            )

                        # Credentials BC
                        st.markdown(
                            '<div class="section-bc">'
                            '<p class="section-bc-title">'
                            '🔌 Credentials de connexion BC</p>',
                            unsafe_allow_html=True
                        )
                        st.caption(
                            "Ces informations sont fournies par l'administrateur IT "
                            "du client depuis le portail Azure (Entra ID). "
                            "Laissez vide si pas encore disponible."
                        )
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            e_tenant = st.text_input(
                                "Tenant ID",
                                value=profile.get("bc_tenant_id", ""),
                                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                                type="password"
                            )
                            e_client_id = st.text_input(
                                "Client ID",
                                value=profile.get("bc_client_id", ""),
                                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                                type="password"
                            )
                        with bc2:
                            e_secret = st.text_input(
                                "Client Secret",
                                value=profile.get("bc_client_secret", ""),
                                placeholder="Valeur du secret créé dans Entra ID",
                                type="password"
                            )
                            st.info(
                                "🔒 Stocké de façon sécurisée dans Supabase. "
                                "Non visible après enregistrement."
                            )
                        st.markdown("</div>", unsafe_allow_html=True)

                        e_notes = st.text_area(
                            "Notes", value=profile.get("notes", ""), height=60
                        )

                        col_save, col_cancel, _ = st.columns([2, 2, 6])
                        with col_save:
                            save = st.form_submit_button(
                                "💾 Enregistrer",
                                type="primary",
                                use_container_width=True
                            )
                        with col_cancel:
                            cancel = st.form_submit_button(
                                "Annuler",
                                use_container_width=True
                            )

                        if save:
                            ok, err = update_profile(code, {
                                "name":              e_name.strip(),
                                "sector":            e_sector.strip(),
                                "data_language":     e_lang,
                                "bc_url":            e_url.strip(),
                                "bc_environment":    e_env.strip(),
                                "bc_tenant_id":      e_tenant.strip() or None,
                                "bc_client_id":      e_client_id.strip() or None,
                                "bc_client_secret":  e_secret.strip() or None,
                                "notes":             e_notes.strip(),
                            })
                            if ok:
                                st.success("✅ Profil mis à jour !")
                                st.session_state.edit_profile = None
                                st.rerun()
                            else:
                                st.error(f"❌ {err}")

                        if cancel:
                            st.session_state.edit_profile = None
                            st.rerun()

            # ── Confirmation suppression ───────────────────────────────────
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
        "Renseignez les informations du client. "
        "Les credentials BC peuvent être ajoutés plus tard "
        "en modifiant le profil."
    )
    st.markdown("---")

    with st.form("create_profile_form", clear_on_submit=True):

        col1, col2 = st.columns(2)
        with col1:
            new_code   = st.text_input(
                "Code client *",
                placeholder="Ex: CLT-ABC-001"
            )
            new_name   = st.text_input(
                "Nom client *",
                placeholder="Ex: ABC Distribution SARL"
            )
            new_sector = st.text_input(
                "Secteur d'activité",
                placeholder="Ex: Distribution B2B"
            )
            new_lang   = st.selectbox(
                "Langue des données",
                ["Français", "Anglais", "Arabe", "Autre"]
            )
        with col2:
            new_url = st.text_input(
                "URL environnement BC",
                placeholder="https://abc.businesscentral.dynamics.com"
            )
            new_env = st.text_input(
                "Nom de l'environnement BC",
                placeholder="Ex: Production, Sandbox"
            )
            new_notes = st.text_area(
                "Notes projet",
                placeholder="Contexte, ancien système...",
                height=97
            )

        # Credentials BC — optionnels à la création
        st.markdown("---")
        st.markdown(
            '<div class="section-bc">'
            '<p class="section-bc-title">'
            '🔌 Credentials de connexion BC (optionnel)</p>',
            unsafe_allow_html=True
        )
        st.caption(
            "Vous pouvez laisser ces champs vides maintenant "
            "et les renseigner plus tard en modifiant le profil. "
            "Ces informations sont fournies par l'administrateur IT du client."
        )
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            new_tenant = st.text_input(
                "Tenant ID",
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                type="password"
            )
        with bc2:
            new_client_id = st.text_input(
                "Client ID",
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                type="password"
            )
        with bc3:
            new_secret = st.text_input(
                "Client Secret",
                placeholder="Valeur du secret",
                type="password"
            )
        st.markdown("</div>", unsafe_allow_html=True)

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
                    "code":             new_code.strip().upper(),
                    "name":             new_name.strip(),
                    "sector":           new_sector.strip(),
                    "data_language":    new_lang,
                    "bc_url":           new_url.strip(),
                    "bc_environment":   new_env.strip(),
                    "bc_tenant_id":     new_tenant.strip() or None,
                    "bc_client_id":     new_client_id.strip() or None,
                    "bc_client_secret": new_secret.strip() or None,
                    "notes":            new_notes.strip(),
                }
                ok, err = create_profile(profile_data)
                if ok:
                    st.success(
                        f"✅ Profil **{new_name}** ({new_code.upper()}) créé !"
                    )
                    if copy_from:
                        ok_c, msg_c, _ = copy_rules_to_profile(
                            copy_from, new_code.strip().upper()
                        )
                        if ok_c:
                            st.info(f"📋 {msg_c}")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ {err}")