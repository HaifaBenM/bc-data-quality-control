"""
Page Profils Clients — Sprint 2 v4 final.
Credentials BC complets par client (Tenant ID + Client ID + Secret).
Bouton de test de connexion BC. Icônes et accents corrects.
"""
import streamlit as st
from app.db.supabase_client import test_connection
from app.db.profiles_db import (
    get_all_profiles, create_profile, update_profile,
    delete_profile, get_profile_stats, get_profiles_for_select
)
from app.db.rules_db import copy_rules_to_profile
from app.core.bc_connector import test_bc_connection

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
        border-radius: 8px; padding: 16px; margin: 12px 0;
    }
    .section-bc-title {
        font-size: 13px; font-weight: 600; color: #1B3A6B; margin: 0 0 8px;
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

for key, default in [
    ("confirm_delete", None),
    ("edit_profile",   None),
    ("bc_test_result", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

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
            has_bc = bool(
                profile.get("bc_tenant_id") and
                profile.get("bc_client_id") and
                profile.get("bc_client_secret")
            )

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
                    f'<span class="badge badge-rules">{nb_active} règle(s) active(s)</span>'
                    if nb_rules > 0 else
                    '<span class="badge badge-no-rules">Aucune règle</span>'
                )
                bc_badge = (
                    '<span class="badge badge-bc-ok">🔌 BC configuré</span>'
                    if has_bc else
                    '<span class="badge badge-bc-none">⚙️ BC non configuré</span>'
                )
                bc_url = profile.get("bc_url", "")
                bc_env = profile.get("bc_environment", "")
                bc_info = (
                    f'<span style="font-size:11px;color:#94A3B8">'
                    f'{bc_url}{" · " + bc_env if bc_env else ""}</span>'
                    if bc_url else ""
                )

                st.markdown(
                    f'<div class="profile-card">'
                    f'<p class="profile-name">{profile.get("name", "")}</p>'
                    f'<p class="profile-code">Code : {code}</p>'
                    f'<div style="margin-top:8px">'
                    f'{sector_badge}{rules_badge}{bc_badge}</div>'
                    f'{"<div style=margin-top:4px>" + bc_info + "</div>" if bc_info else ""}'
                    f'</div>',
                    unsafe_allow_html=True
                )

            with col_actions:
                st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("⚙️ Règles", key=f"rules_{code}",
                                 use_container_width=True,
                                 help="Gérer les règles métier"):
                        st.session_state["selected_profile_for_rules"] = code
                        st.switch_page("pages/4_Regles_Metier.py")
                with c2:
                    if st.button("✏️ Éditer", key=f"edit_{code}",
                                 use_container_width=True,
                                 help="Modifier le profil"):
                        st.session_state.edit_profile   = code
                        st.session_state.bc_test_result = {}
                with c3:
                    if st.button("🗑️", key=f"del_{code}",
                                 use_container_width=True,
                                 help="Supprimer"):
                        st.session_state.confirm_delete = code
                st.markdown("</div>", unsafe_allow_html=True)

            # ── Formulaire de modification ─────────────────────────────────
            if st.session_state.edit_profile == code:
                with st.expander(
                    f"✏️ Modifier — {profile.get('name', '')}",
                    expanded=True
                ):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        e_name = st.text_input(
                            "Nom client",
                            value=profile.get("name", ""),
                            key=f"e_name_{code}"
                        )
                        e_sector = st.text_input(
                            "Secteur",
                            value=profile.get("sector", ""),
                            key=f"e_sector_{code}"
                        )
                        langs    = ["Français", "Anglais", "Arabe", "Autre"]
                        cur_lang = profile.get("data_language", "Français")
                        e_lang   = st.selectbox(
                            "Langue des données", langs,
                            index=langs.index(cur_lang) if cur_lang in langs else 0,
                            key=f"e_lang_{code}"
                        )
                    with ec2:
                        e_url = st.text_input(
                            "URL BC",
                            value=profile.get("bc_url", ""),
                            placeholder="https://abc.businesscentral.dynamics.com",
                            key=f"e_url_{code}"
                        )
                        e_env = st.text_input(
                            "Environnement BC",
                            value=profile.get("bc_environment", ""),
                            placeholder="Ex : Production, Sandbox",
                            key=f"e_env_{code}"
                        )

                    # Credentials BC
                    st.markdown(
                        '<div class="section-bc">'
                        '<p class="section-bc-title">'
                        '🔌 Credentials de connexion BC</p>',
                        unsafe_allow_html=True
                    )
                    st.caption(
                        "Ces 3 informations sont spécifiques à ce client. "
                        "Demandez-les à l'administrateur IT du client "
                        "(portail Azure / Entra ID). "
                        "Laissez vide si pas encore disponible."
                    )

                    bc1, bc2, bc3 = st.columns(3)
                    with bc1:
                        e_tenant = st.text_input(
                            "Tenant ID",
                            value=profile.get("bc_tenant_id", ""),
                            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                            type="password",
                            key=f"e_tenant_{code}",
                            help="Trouvé dans BC : Aide → Signaler un problème → ID abonné Microsoft Entra"
                        )
                    with bc2:
                        e_client_id = st.text_input(
                            "Client ID",
                            value=profile.get("bc_client_id", ""),
                            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                            type="password",
                            key=f"e_cid_{code}",
                            help="ID de l'application créée dans Entra ID du client"
                        )
                    with bc3:
                        e_secret = st.text_input(
                            "Client Secret",
                            value=profile.get("bc_client_secret", ""),
                            placeholder="Valeur du secret",
                            type="password",
                            key=f"e_secret_{code}",
                            help="Entra ID → Certificats et secrets → Valeur"
                        )

                    # Bouton test
                    col_test, col_result = st.columns([2, 5])
                    with col_test:
                        if st.button(
                            "🔌 Tester la connexion BC",
                            key=f"test_{code}",
                            use_container_width=True
                        ):
                            missing = []
                            if not str(e_tenant or "").strip():
                                missing.append("Tenant ID")
                            if not str(e_client_id or "").strip():
                                missing.append("Client ID")
                            if not str(e_secret or "").strip():
                                missing.append("Client Secret")

                            if missing:
                                st.session_state.bc_test_result[code] = (
                                    False,
                                    f"Champs manquants : {', '.join(missing)}"
                                )
                            else:
                                with st.spinner("Test de connexion en cours..."):
                                    ok_t, msg_t = test_bc_connection(
                                        tenant_id=str(e_tenant).strip(),
                                        client_id=str(e_client_id).strip(),
                                        client_secret=str(e_secret).strip(),
                                        environment=str(e_env or "").strip()
                                    )
                                st.session_state.bc_test_result[code] = (ok_t, msg_t)
                            st.rerun()

                    with col_result:
                        res = st.session_state.bc_test_result.get(code)
                        if res:
                            if res[0]:
                                st.success(f"✅ {res[1]}")
                            else:
                                st.error(f"❌ {res[1]}")

                    st.markdown("</div>", unsafe_allow_html=True)

                    e_notes = st.text_area(
                        "Notes",
                        value=profile.get("notes", ""),
                        height=60,
                        key=f"e_notes_{code}"
                    )

                    cs, cc, _ = st.columns([2, 2, 6])
                    with cs:
                        if st.button(
                            "💾 Enregistrer",
                            key=f"save_{code}",
                            type="primary",
                            use_container_width=True
                        ):
                            ok, err = update_profile(code, {
                                "name":             str(e_name or "").strip(),
                                "sector":           str(e_sector or "").strip(),
                                "data_language":    e_lang,
                                "bc_url":           str(e_url or "").strip(),
                                "bc_environment":   str(e_env or "").strip(),
                                "bc_tenant_id":     str(e_tenant or "").strip() or None,
                                "bc_client_id":     str(e_client_id or "").strip() or None,
                                "bc_client_secret": str(e_secret or "").strip() or None,
                                "notes":            str(e_notes or "").strip(),
                            })
                            if ok:
                                st.success("✅ Profil mis à jour !")
                                st.session_state.edit_profile   = None
                                st.session_state.bc_test_result = {}
                                st.rerun()
                            else:
                                st.error(f"❌ {err}")
                    with cc:
                        if st.button(
                            "Annuler",
                            key=f"cancel_{code}",
                            use_container_width=True
                        ):
                            st.session_state.edit_profile   = None
                            st.session_state.bc_test_result = {}
                            st.rerun()

            # Confirmation suppression
            if st.session_state.confirm_delete == code:
                st.warning(
                    f"⚠️ Supprimer **{profile.get('name', '')}** ? "
                    "Toutes ses règles seront supprimées."
                )
                cy, cn, _ = st.columns([2, 2, 6])
                with cy:
                    if st.button("✅ Confirmer", key=f"yes_{code}", type="primary"):
                        ok, err = delete_profile(code)
                        if ok:
                            st.success("✅ Profil supprimé.")
                            st.session_state.confirm_delete = None
                            st.rerun()
                        else:
                            st.error(f"❌ {err}")
                with cn:
                    if st.button("❌ Annuler", key=f"no_{code}"):
                        st.session_state.confirm_delete = None
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — NOUVEAU PROFIL
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    st.markdown("### Créer un nouveau profil client")
    st.caption(
        "Les credentials BC peuvent être ajoutés plus tard "
        "en cliquant sur '✏️ Éditer'."
    )
    st.markdown("---")

    nc1, nc2 = st.columns(2)
    with nc1:
        new_code   = st.text_input("Code client *", placeholder="CLT-ABC-001",
                                   key="new_code")
        new_name   = st.text_input("Nom client *",
                                   placeholder="ABC Distribution SARL",
                                   key="new_name")
        new_sector = st.text_input("Secteur d'activité",
                                   placeholder="Distribution B2B",
                                   key="new_sector")
        new_lang   = st.selectbox("Langue des données",
                                  ["Français", "Anglais", "Arabe", "Autre"],
                                  key="new_lang")
    with nc2:
        new_url   = st.text_input("URL BC",
                                  placeholder="https://abc.businesscentral.dynamics.com",
                                  key="new_url")
        new_env   = st.text_input("Environnement BC",
                                  placeholder="Production, Sandbox...",
                                  key="new_env")
        new_notes = st.text_area("Notes projet",
                                 placeholder="Contexte, ancien système...",
                                 height=97, key="new_notes")

    st.markdown("---")
    st.markdown(
        '<div class="section-bc">'
        '<p class="section-bc-title">🔌 Credentials de connexion BC (optionnel)</p>',
        unsafe_allow_html=True
    )
    st.caption(
        "Ces 3 informations sont spécifiques à ce client. "
        "Vous pouvez les ajouter maintenant ou plus tard via '✏️ Éditer'."
    )

    nb1, nb2, nb3 = st.columns(3)
    with nb1:
        new_tenant = st.text_input(
            "Tenant ID",
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            type="password", key="new_tenant",
            help="BC : Aide → Signaler un problème → ID abonné Microsoft Entra"
        )
    with nb2:
        new_client_id = st.text_input(
            "Client ID",
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            type="password", key="new_client_id",
            help="ID de l'application Entra ID du client"
        )
    with nb3:
        new_secret = st.text_input(
            "Client Secret",
            placeholder="Valeur du secret",
            type="password", key="new_secret",
            help="Entra ID → Certificats et secrets → Valeur"
        )

    col_t, col_r = st.columns([2, 5])
    with col_t:
        if st.button("🔌 Tester la connexion BC",
                     key="test_new", use_container_width=True):
            missing = []
            if not str(new_tenant or "").strip():    missing.append("Tenant ID")
            if not str(new_client_id or "").strip(): missing.append("Client ID")
            if not str(new_secret or "").strip():    missing.append("Client Secret")

            if missing:
                st.session_state.bc_test_result["new"] = (
                    False, f"Champs manquants : {', '.join(missing)}"
                )
            else:
                with st.spinner("Test de connexion en cours..."):
                    ok_t, msg_t = test_bc_connection(
                        tenant_id=str(new_tenant).strip(),
                        client_id=str(new_client_id).strip(),
                        client_secret=str(new_secret).strip(),
                        environment=str(new_env or "").strip()
                    )
                st.session_state.bc_test_result["new"] = (ok_t, msg_t)
            st.rerun()

    with col_r:
        res = st.session_state.bc_test_result.get("new")
        if res:
            if res[0]: st.success(f"✅ {res[1]}")
            else:      st.error(f"❌ {res[1]}")

    st.markdown("</div>", unsafe_allow_html=True)

    profiles_for_copy = get_profiles_for_select()
    copy_from = None
    if profiles_for_copy:
        st.markdown("---")
        opts   = ["— Ne pas copier de règles —"] + [p["label"] for p in profiles_for_copy]
        choice = st.selectbox("Copier les règles depuis un profil existant (optionnel)",
                              opts, key="copy_choice")
        if choice != "— Ne pas copier de règles —":
            copy_from = next(
                (p["code"] for p in profiles_for_copy if p["label"] == choice), None
            )

    st.markdown("---")
    if st.button("💾 Créer le profil", type="primary", key="btn_create"):
        errors = []
        if not new_code or not new_code.strip(): errors.append("Code client obligatoire.")
        if not new_name or not new_name.strip(): errors.append("Nom client obligatoire.")
        if errors:
            for e in errors: st.error(e)
        else:
            ok, err = create_profile({
                "code":             new_code.strip().upper(),
                "name":             new_name.strip(),
                "sector":           str(new_sector or "").strip(),
                "data_language":    new_lang,
                "bc_url":           str(new_url or "").strip(),
                "bc_environment":   str(new_env or "").strip(),
                "bc_tenant_id":     str(new_tenant or "").strip() or None,
                "bc_client_id":     str(new_client_id or "").strip() or None,
                "bc_client_secret": str(new_secret or "").strip() or None,
                "notes":            str(new_notes or "").strip(),
            })
            if ok:
                st.success(f"✅ Profil **{new_name}** ({new_code.upper()}) créé !")
                if copy_from:
                    ok_c, msg_c, _ = copy_rules_to_profile(
                        copy_from, new_code.strip().upper()
                    )
                    if ok_c: st.info(f"📋 {msg_c}")
                st.session_state.bc_test_result = {}
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ {err}")
