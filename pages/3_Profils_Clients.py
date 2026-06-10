"""
Page Profils Clients — Sprint 3.
Sélection société BC + chargement metadata.
"""
import streamlit as st
from app.db.supabase_client import test_connection
from app.db.profiles_db import (
    get_all_profiles, create_profile, update_profile,
    delete_profile, get_profile_stats, get_profiles_for_select
)
from app.db.rules_db import copy_rules_to_profile
from app.db.metadata_db import get_cache_summary, delete_cache, save_metadata, save_reference_data
from app.core.bc_connector import test_bc_connection, get_bc_companies
from app.core.bc_metadata import read_bc_metadata, load_all_reference_data

st.set_page_config(page_title="Profils Clients — BC Quality Control", page_icon="👥", layout="wide")

st.markdown("""
<style>
    .profile-card { background:white;border:1px solid #E2E8F0;border-radius:10px;padding:16px 20px;margin-bottom:10px; }
    .profile-name { font-size:15px;font-weight:600;color:#1B3A6B;margin:0; }
    .profile-code { font-size:12px;color:#64748B;margin:2px 0 0; }
    .badge { display:inline-block;font-size:11px;font-weight:500;padding:2px 8px;border-radius:12px;margin-right:6px; }
    .badge-rules    { background:#E1F5EE;color:#0F6E56; }
    .badge-sector   { background:#EFF6FF;color:#2E6FBF; }
    .badge-no-rules { background:#FEF3C7;color:#92400E; }
    .badge-bc-ok    { background:#E1F5EE;color:#0F6E56; }
    .badge-bc-none  { background:#F1F5F9;color:#64748B; }
    .badge-meta-ok  { background:#EEEDFE;color:#534AB7; }
    .section-bc { background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:16px;margin:12px 0; }
    .section-bc-title { font-size:13px;font-weight:600;color:#1B3A6B;margin:0 0 8px; }
    .meta-box { background:#EEEDFE;border:1px solid #C4B5FD;border-radius:8px;padding:12px 16px;margin:8px 0; }
    #MainMenu { visibility:hidden; } footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 👥 Profils Clients")
st.markdown("Gérez les profils clients, leurs credentials BC et leurs règles métier.")
st.markdown("---")

connected, msg = test_connection()
if not connected:
    st.error(f"❌ Base de données non connectée : {msg}")
    st.stop()

for key, default in [("confirm_delete",None),("edit_profile",None),("bc_test_result",{}),("companies_list",{})]:
    if key not in st.session_state:
        st.session_state[key] = default

tab1, tab2 = st.tabs(["👥 Mes profils", "➕ Nouveau profil"])

# ════════════════════════════════════════════════════════════════════════════
# FONCTION METADATA
# ════════════════════════════════════════════════════════════════════════════
def charger_metadata(code, tenant_id, client_id, client_secret, environment, company_id):
    progress = st.progress(0, text="Lecture de la metadata BC...")
    total = 0

    # Étape 1 — Metadata champs
    progress.progress(10, text="Lecture des définitions de champs...")
    meta = read_bc_metadata(tenant_id, client_id, client_secret, environment)
    if meta["success"]:
        entities = meta["entities"]
        for i, (name, data) in enumerate(entities.items()):
            pct = 10 + int((i / max(len(entities),1)) * 40)
            progress.progress(pct, text=f"Entité : {name}")
            ok, _ = save_metadata(code, name, "data", data.get("fields", []))
            if ok: total += 1

    # Étape 2 — Données de référence
    progress.progress(55, text="Chargement tables de référence...")
    ref_data = load_all_reference_data(tenant_id, client_id, client_secret, environment, company_id)
    for i, (path, info) in enumerate(ref_data.items()):
        pct = 55 + int((i / max(len(ref_data),1)) * 40)
        progress.progress(pct, text=f"Référence : {info['label']}")
        ok, _ = save_reference_data(code, path, info["label"], info["data"], info["count"])
        if ok: total += 1

    progress.progress(100, text="Terminé !")
    cache = get_cache_summary(code)
    st.success(
        f"✅ Metadata chargée — "
        f"{cache['data']} entités · "
        f"{cache['reference']} tables de référence"
    )
    st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LISTE
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    profiles = get_all_profiles()
    if not profiles:
        st.info("Aucun profil. Utilisez **'Nouveau profil'** pour commencer.")
    else:
        st.markdown(f"**{len(profiles)} profil(s)**")
        st.markdown("---")

        for profile in profiles:
            code  = profile.get("code","")
            stats = get_profile_stats(code)
            has_bc = bool(profile.get("bc_tenant_id") and profile.get("bc_client_id") and profile.get("bc_client_secret"))
            cache  = get_cache_summary(code)

            col_info, col_actions = st.columns([7,3])
            with col_info:
                s_badge = f'<span class="badge badge-sector">{profile.get("sector","")}</span>' if profile.get("sector") else ""
                r_badge = f'<span class="badge badge-rules">{stats["active_rules"]} règle(s)</span>' if stats["total_rules"]>0 else '<span class="badge badge-no-rules">Aucune règle</span>'
                b_badge = '<span class="badge badge-bc-ok">🔌 BC configuré</span>' if has_bc else '<span class="badge badge-bc-none">⚙️ BC non configuré</span>'
                m_badge = ""  # Badge entités supprimé
                company_name = profile.get("bc_company_name","")
                bc_info = f'<span style="font-size:11px;color:#94A3B8">{profile.get("bc_url","")}{" · "+profile.get("bc_environment","") if profile.get("bc_environment") else ""}{" · 🏢 "+company_name if company_name else ""}</span>' if profile.get("bc_url") else ""
                st.markdown(f'<div class="profile-card"><p class="profile-name">{profile.get("name","")}</p><p class="profile-code">Code : {code}</p><div style="margin-top:8px">{s_badge}{r_badge}{b_badge}{m_badge}</div>{"<div style=margin-top:4px>"+bc_info+"</div>" if bc_info else ""}</div>', unsafe_allow_html=True)

            with col_actions:
                st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
                c1,c2,c3 = st.columns(3)
                with c1:
                    if st.button("⚙️ Règles", key=f"rules_{code}", use_container_width=True):
                        st.session_state["selected_profile_for_rules"] = code
                        st.switch_page("pages/4_Regles_Metier.py")
                with c2:
                    if st.button("✏️ Éditer", key=f"edit_{code}", use_container_width=True):
                        st.session_state.edit_profile = code
                        st.session_state.bc_test_result = {}
                        st.session_state.companies_list = {}
                with c3:
                    if st.button("🗑️", key=f"del_{code}", use_container_width=True):
                        st.session_state.confirm_delete = code
                st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.edit_profile == code:
                with st.expander(f"✏️ Modifier — {profile.get('name','')}", expanded=True):
                    ec1,ec2 = st.columns(2)
                    with ec1:
                        e_name   = st.text_input("Nom client",   value=profile.get("name",""),   key=f"e_name_{code}")
                        e_sector = st.text_input("Secteur",       value=profile.get("sector",""), key=f"e_sector_{code}")
                        langs    = ["Français","Anglais","Arabe","Autre"]
                        cur_lang = profile.get("data_language","Français")
                        e_lang   = st.selectbox("Langue", langs, index=langs.index(cur_lang) if cur_lang in langs else 0, key=f"e_lang_{code}")
                    with ec2:
                        e_url = st.text_input("URL BC",            value=profile.get("bc_url",""),         placeholder="https://abc.businesscentral.dynamics.com", key=f"e_url_{code}")
                        e_env = st.text_input("Environnement BC",  value=profile.get("bc_environment",""), placeholder="Production, Sandbox", key=f"e_env_{code}")

                    st.markdown('<div class="section-bc"><p class="section-bc-title">🔌 Credentials BC</p>', unsafe_allow_html=True)
                    st.caption("Ces 3 informations sont spécifiques à ce client.")
                    bc1,bc2,bc3 = st.columns(3)
                    with bc1: e_tenant    = st.text_input("Tenant ID",     value=profile.get("bc_tenant_id",""),     placeholder="xxxx-xxxx-xxxx", type="password", key=f"e_tenant_{code}",    help="BC : Aide → Signaler un problème → ID abonné Entra")
                    with bc2: e_client_id = st.text_input("Client ID",     value=profile.get("bc_client_id",""),     placeholder="xxxx-xxxx-xxxx", type="password", key=f"e_cid_{code}")
                    with bc3: e_secret    = st.text_input("Client Secret", value=profile.get("bc_client_secret",""), placeholder="Valeur secret",  type="password", key=f"e_secret_{code}")

                    col_test, col_result = st.columns([2,5])
                    with col_test:
                        if st.button("🔌 Tester la connexion", key=f"test_{code}", use_container_width=True):
                            missing = [f for f,v in [("Tenant ID",e_tenant),("Client ID",e_client_id),("Secret",e_secret)] if not str(v or "").strip()]
                            if missing:
                                st.session_state.bc_test_result[code] = (False, f"Manquants : {', '.join(missing)}")
                                st.session_state.companies_list[code] = []
                            else:
                                with st.spinner("Test..."):
                                    ok_t, msg_t = test_bc_connection(str(e_tenant).strip(), str(e_client_id).strip(), str(e_secret).strip(), str(e_env or "").strip())
                                st.session_state.bc_test_result[code] = (ok_t, msg_t)
                                if ok_t:
                                    st.session_state.companies_list[code] = get_bc_companies(str(e_tenant).strip(), str(e_client_id).strip(), str(e_secret).strip(), str(e_env or "").strip())
                            st.rerun()
                    with col_result:
                        res = st.session_state.bc_test_result.get(code)
                        if res:
                            if res[0]: st.success(f"✅ {res[1]}")
                            else:      st.error(f"❌ {res[1]}")

                    # Sélection société
                    companies = st.session_state.companies_list.get(code, [])
                    sel_company_name = profile.get("bc_company_name","")
                    sel_company_id   = profile.get("bc_company_id","")

                    if companies:
                        st.markdown("---")
                        st.markdown("**🏢 Société BC par défaut**")
                        company_map = {c.get("name", c.get("id","?")): c.get("id","") for c in companies}
                        names = list(company_map.keys())
                        default_idx = names.index(sel_company_name) if sel_company_name in names else 0
                        sel_company_name = st.selectbox("Société BC", names, index=default_idx, key=f"csel_{code}")
                        sel_company_id   = company_map.get(sel_company_name,"")
                    elif sel_company_name:
                        st.info(f"🏢 Société actuelle : **{sel_company_name}** — Testez la connexion pour changer.")

                    st.markdown("</div>", unsafe_allow_html=True)
                    e_notes = st.text_area("Notes", value=profile.get("notes",""), height=60, key=f"e_notes_{code}")

                    cs, cc, cm, _ = st.columns([2,2,3,3])
                    with cs:
                        if st.button("💾 Enregistrer", key=f"save_{code}", type="primary", use_container_width=True):
                            ok, err = update_profile(code, {
                                "name": str(e_name or "").strip(), "sector": str(e_sector or "").strip(),
                                "data_language": e_lang, "bc_url": str(e_url or "").strip(),
                                "bc_environment": str(e_env or "").strip(),
                                "bc_tenant_id":     str(e_tenant or "").strip() or None,
                                "bc_client_id":     str(e_client_id or "").strip() or None,
                                "bc_client_secret": str(e_secret or "").strip() or None,
                                "bc_company_id":    sel_company_id or None,
                                "bc_company_name":  sel_company_name or None,
                                "notes": str(e_notes or "").strip(),
                            })
                            if ok:
                                st.success("✅ Profil mis à jour !")
                                st.session_state.edit_profile = None
                                st.session_state.bc_test_result = {}
                                st.session_state.companies_list = {}
                                st.rerun()
                            else: st.error(f"❌ {err}")
                    with cc:
                        if st.button("Annuler", key=f"cancel_{code}", use_container_width=True):
                            st.session_state.edit_profile = None
                            st.session_state.bc_test_result = {}
                            st.session_state.companies_list = {}
                            st.rerun()
                    with cm:
                        can_load = bool(str(e_tenant or "").strip() and str(e_client_id or "").strip() and str(e_secret or "").strip() and sel_company_id)
                        if st.button("📋 Charger metadata BC", key=f"meta_{code}", use_container_width=True, disabled=not can_load, help="Lit les champs et tables de référence depuis BC"):
                            charger_metadata(code, str(e_tenant).strip(), str(e_client_id).strip(), str(e_secret).strip(), str(e_env or "").strip(), sel_company_id)

                    # Statut cache (discret)
                    cache_now = get_cache_summary(code)
                    if cache_now["total"] > 0:
                        col_cs, col_cb, _ = st.columns([3, 2, 5])
                        with col_cs:
                            st.success(f"✅ Metadata BC chargée — {cache_now['last_update']}")
                        with col_cb:
                            if st.button("🗑️ Vider le cache", key=f"clear_meta_{code}"):
                                ok, _ = delete_cache(code)
                                if ok: st.rerun()

            if st.session_state.confirm_delete == code:
                st.warning(f"⚠️ Supprimer **{profile.get('name','')}** ?")
                cy,cn,_ = st.columns([2,2,6])
                with cy:
                    if st.button("✅ Confirmer", key=f"yes_{code}", type="primary"):
                        ok, err = delete_profile(code)
                        if ok:
                            st.success("✅ Supprimé.")
                            st.session_state.confirm_delete = None
                            st.rerun()
                        else: st.error(err)
                with cn:
                    if st.button("❌ Annuler", key=f"no_{code}"):
                        st.session_state.confirm_delete = None
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — NOUVEAU PROFIL
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Créer un nouveau profil client")
    nc1,nc2 = st.columns(2)
    with nc1:
        new_code   = st.text_input("Code client *", placeholder="CLT-ABC-001", key="new_code")
        new_name   = st.text_input("Nom client *", placeholder="ABC Distribution SARL", key="new_name")
        new_sector = st.text_input("Secteur", placeholder="Distribution B2B", key="new_sector")
        new_lang   = st.selectbox("Langue", ["Français","Anglais","Arabe","Autre"], key="new_lang")
    with nc2:
        new_url   = st.text_input("URL BC", placeholder="https://abc.businesscentral.dynamics.com", key="new_url")
        new_env   = st.text_input("Environnement BC", placeholder="Production, Sandbox", key="new_env")
        new_notes = st.text_area("Notes", height=97, key="new_notes")

    st.markdown("---")
    st.markdown('<div class="section-bc"><p class="section-bc-title">🔌 Credentials BC (optionnel)</p>', unsafe_allow_html=True)
    nb1,nb2,nb3 = st.columns(3)
    with nb1: new_tenant    = st.text_input("Tenant ID",     placeholder="xxxx-xxxx", type="password", key="new_tenant",    help="BC : Aide → Signaler un problème")
    with nb2: new_client_id = st.text_input("Client ID",     placeholder="xxxx-xxxx", type="password", key="new_client_id")
    with nb3: new_secret    = st.text_input("Client Secret", placeholder="Valeur",    type="password", key="new_secret")

    ct,cr = st.columns([2,5])
    with ct:
        if st.button("🔌 Tester", key="test_new", use_container_width=True):
            missing = [f for f,v in [("Tenant",new_tenant),("Client ID",new_client_id),("Secret",new_secret)] if not str(v or "").strip()]
            if missing: st.session_state.bc_test_result["new"] = (False, f"Manquants : {', '.join(missing)}")
            else:
                with st.spinner("Test..."):
                    ok_t, msg_t = test_bc_connection(str(new_tenant).strip(), str(new_client_id).strip(), str(new_secret).strip(), str(new_env or "").strip())
                st.session_state.bc_test_result["new"] = (ok_t, msg_t)
            st.rerun()
    with cr:
        res = st.session_state.bc_test_result.get("new")
        if res:
            if res[0]: st.success(f"✅ {res[1]}")
            else:      st.error(f"❌ {res[1]}")
    st.markdown("</div>", unsafe_allow_html=True)

    profiles_for_copy = get_profiles_for_select()
    copy_from = None
    if profiles_for_copy:
        st.markdown("---")
        opts = ["— Ne pas copier —"] + [p["label"] for p in profiles_for_copy]
        choice = st.selectbox("Copier règles depuis", opts, key="copy_choice")
        if choice != "— Ne pas copier —":
            copy_from = next((p["code"] for p in profiles_for_copy if p["label"] == choice), None)

    st.markdown("---")
    if st.button("💾 Créer le profil", type="primary", key="btn_create"):
        errors = []
        if not new_code or not new_code.strip(): errors.append("Code obligatoire.")
        if not new_name or not new_name.strip(): errors.append("Nom obligatoire.")
        if errors:
            for e in errors: st.error(e)
        else:
            ok, err = create_profile({
                "code": new_code.strip().upper(), "name": new_name.strip(),
                "sector": str(new_sector or "").strip(), "data_language": new_lang,
                "bc_url": str(new_url or "").strip(), "bc_environment": str(new_env or "").strip(),
                "bc_tenant_id":     str(new_tenant or "").strip() or None,
                "bc_client_id":     str(new_client_id or "").strip() or None,
                "bc_client_secret": str(new_secret or "").strip() or None,
                "notes": str(new_notes or "").strip(),
            })
            if ok:
                st.success(f"✅ Profil **{new_name}** créé !")
                if copy_from:
                    ok_c, msg_c, _ = copy_rules_to_profile(copy_from, new_code.strip().upper())
                    if ok_c: st.info(f"📋 {msg_c}")
                st.session_state.bc_test_result = {}
                st.balloons()
                st.rerun()
            else: st.error(f"❌ {err}")
