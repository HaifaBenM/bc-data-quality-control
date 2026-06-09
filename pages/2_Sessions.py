"""
Page Sessions — Sprint 5 v3.
Nouvelle session + Mes sessions avec édition / suppression.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a, get_anomalies_dataframe
from app.core.validator_axe_b import validate_file_axe_b
from app.db.profiles_db import get_profiles_for_select
from app.db.rules_db import get_active_rules_for_profile
from app.db.sessions_db import (
    save_session, update_session, delete_session,
    get_all_sessions, SESSION_STATUSES, STATUS_COLORS, STATUS_ICONS
)

st.set_page_config(
    page_title="Sessions — BC Quality Control",
    page_icon="📁",
    layout="wide"
)

st.markdown("""
<style>
    .step-header {
        background: linear-gradient(135deg, #1B3A6B, #2E6FBF);
        color: white; padding: .75rem 1.25rem;
        border-radius: 8px; margin-bottom: 1rem; font-weight: 600;
    }
    .card-data  { background:#E1F5EE;border-left:4px solid #0F6E56;border-radius:8px;padding:12px 16px;margin-bottom:8px; }
    .card-ref   { background:#EFF6FF;border-left:4px solid #2E6FBF;border-radius:8px;padding:10px 14px;margin-bottom:6px; }
    .card-rule  { background:#EEEDFE;border-left:3px solid #534AB7;border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:12px; }
    .card-major { background:#FAECE7;border-left:4px solid #993C1D;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-minor { background:#FAEEDA;border-left:4px solid #854F0B;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-info  { background:#EFF6FF;border-left:4px solid #2E6FBF;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-session { background:white;border:1px solid #E2E8F0;border-radius:10px;padding:14px 18px;margin-bottom:4px; }
    .session-name { font-size:14px;font-weight:600;color:#1B3A6B;margin:0; }
    .session-meta { font-size:12px;color:#64748B;margin:4px 0 0; }
    .stat-box { background:white;border:1px solid #E2E8F0;border-radius:8px;padding:12px;text-align:center; }
    .stat-num { font-size:2rem;font-weight:700;margin:0; }
    .stat-lbl { font-size:11px;color:#64748B;margin:0; }
    .save-box { background:#E1F5EE;border:1px solid #0F6E56;border-radius:8px;padding:10px 14px;margin:4px 0; }
    .tag { display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;margin-right:4px; }
    .tag-major { background:#993C1D;color:white; }
    .tag-minor { background:#854F0B;color:white; }
    .tag-info  { background:#2E6FBF;color:white; }
    .tag-data  { background:#0F6E56;color:white; }
    .tag-ref   { background:#2E6FBF;color:white; }
    #MainMenu { visibility:hidden; } footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════
def display_axe_results(axe_result: dict, axe_label: str):
    total    = axe_result.get("total_anomalies", 0)
    major    = axe_result.get("major", 0)
    minor    = axe_result.get("minor", 0)
    info     = axe_result.get("info", 0)
    by_sheet = axe_result.get("by_sheet", {})

    if total == 0:
        st.success(f"✅ Aucune anomalie {axe_label}.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", total)
    m2.metric("🔴 Majeures", major)
    m3.metric("🟠 Mineures", minor)
    m4.metric("🔵 Infos", info)

    sheet_names = list(by_sheet.keys())
    tab_labels  = []
    for s in sheet_names:
        anomalies = by_sheet[s]
        nb        = len([a for a in anomalies if a.get("Ligne", 0) > 0])
        nb_maj    = sum(1 for a in anomalies if a["Sévérité"] == "Majeure")
        icon      = "🔴" if nb_maj > 0 else ("🟠" if nb > 0 else "✅")
        tab_labels.append(f"{icon} {s} ({nb})")

    if not tab_labels:
        return

    for tab, sheet_name in zip(st.tabs(tab_labels), sheet_names):
        with tab:
            anomalies      = by_sheet.get(sheet_name, [])
            real_anomalies = [a for a in anomalies if a.get("Ligne", 0) > 0]
            info_anomalies = [a for a in anomalies if a.get("Ligne", 0) == 0]

            if not real_anomalies and not info_anomalies:
                st.success("✅ Aucune anomalie.")
                continue

            if real_anomalies:
                nb_maj = sum(1 for a in real_anomalies if a["Sévérité"] == "Majeure")
                nb_min = sum(1 for a in real_anomalies if a["Sévérité"] == "Mineure")
                t1, t2, t3 = st.columns(3)
                t1.metric("Anomalies", len(real_anomalies))
                t2.metric("🔴 Majeures", nb_maj)
                t3.metric("🟠 Mineures", nb_min)

                severities = sorted(set(a["Sévérité"] for a in real_anomalies))
                filtered   = [
                    a for a in real_anomalies
                    if a["Sévérité"] in st.multiselect(
                        "Filtrer", severities, default=severities,
                        key=f"filt_{axe_label}_{sheet_name}"
                    )
                ]
                if filtered:
                    df_an = get_anomalies_dataframe(filtered)
                    def cr(row):
                        sev = row.get("Sévérité", "")
                        if sev == "Majeure": return ["background-color:#FAECE7"] * len(row)
                        if sev == "Mineure": return ["background-color:#FAEEDA"] * len(row)
                        return [""] * len(row)
                    st.dataframe(
                        df_an.style.apply(cr, axis=1),
                        use_container_width=True, hide_index=True,
                        height=min(400, 50 + len(filtered) * 35)
                    )
                    with st.expander("📋 Détail"):
                        for a in filtered[:50]:
                            css = "card-major" if a["Sévérité"] == "Majeure" else "card-minor"
                            fix = f" → <b>{a['Correction suggérée']}</b>" if a.get("Correction suggérée") else ""
                            st.markdown(
                                f'<div class="{css}"><b>Ligne {a["Ligne"]}</b> · '
                                f'<b>{a["Champ"]}</b> · '
                                f'<span class="tag tag-{"major" if a["Sévérité"]=="Majeure" else "minor"}">'
                                f'{a["Sévérité"]}</span>'
                                f'<span class="tag" style="background:#E2E8F0;color:#1B3A6B">'
                                f'{a["Type d\'anomalie"]}</span>'
                                f'<br>{a["Message"]}{fix}</div>',
                                unsafe_allow_html=True
                            )
                        if len(filtered) > 50:
                            st.caption(f"50 premières sur {len(filtered)}.")

            if info_anomalies:
                st.markdown("---")
                for a in info_anomalies:
                    st.markdown(
                        f'<div class="card-info"><span class="tag tag-info">INFO</span>'
                        f'<b>{a["Champ"]}</b> — {a["Message"]}</div>',
                        unsafe_allow_html=True
                    )


def reset_session():
    for k in ["step","config","parse_result","validation",
              "axe_a_result","axe_b_result","saved_session_id"]:
        st.session_state[k] = (
            1 if k == "step" else {} if k == "config" else None
        )


# ════════════════════════════════════════════════════════════════════════════
# PAGE
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# 📁 Sessions de contrôle")
st.markdown("---")

tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — NOUVELLE SESSION
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    for key, default in [
        ("step", 1), ("config", {}),
        ("parse_result", None), ("validation", None),
        ("axe_a_result", None), ("axe_b_result", None),
        ("saved_session_id", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    steps = ["Informations", "Upload", "Structure", "Analyse A + B"]
    cols  = st.columns(len(steps))
    for i, (col, name) in enumerate(zip(cols, steps), 1):
        with col:
            if i < st.session_state.step:   st.markdown(f"✅ **{name}**")
            elif i == st.session_state.step: st.markdown(f"🔵 **{name}** ←")
            else:                            st.markdown(f"⬜ {name}")
    st.markdown("---")

    # ── Étape 1 ──────────────────────────────────────────────────────────────
    if st.session_state.step == 1:
        st.markdown('<div class="step-header">Étape 1 — Informations</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            session_name = st.text_input("Nom de la session *", placeholder="ABC - Clients - Juin 2026")
            profiles     = get_profiles_for_select()
            if profiles:
                opts     = ["— Sélectionner un client —"] + [p["label"] for p in profiles]
                choice   = st.selectbox("Client *", opts)
                selected = next((p for p in profiles if p["label"] == choice), None)
            else:
                st.warning("Aucun profil. Créez-en un dans **Profils Clients**.")
                selected = None
        with col2:
            notes = st.text_area("Notes", height=60)
            if selected:
                rules = get_active_rules_for_profile(selected["code"])
                if rules:
                    st.markdown(f"**⚙️ {len(rules)} règle(s) chargée(s) :**")
                    for r in rules[:4]:
                        st.markdown(f'<div class="card-rule"><b>{r.get("label","")}</b> — {r.get("rule_type","")} ({r.get("severity","Mineure")})</div>', unsafe_allow_html=True)
                    if len(rules) > 4: st.caption(f"... et {len(rules)-4} autre(s).")
                else: st.info("Aucune règle pour ce client.")

        st.markdown("---")
        _, col_btn = st.columns([8, 2])
        with col_btn:
            if st.button("Suivant →", type="primary", use_container_width=True):
                errors = []
                if not session_name.strip(): errors.append("Nom obligatoire.")
                if not selected:             errors.append("Sélectionnez un client.")
                if errors:
                    for e in errors: st.error(e)
                else:
                    rules = get_active_rules_for_profile(selected["code"])
                    st.session_state.config = {
                        "session_name": session_name.strip(),
                        "client_code":  selected["code"],
                        "client_name":  selected["name"],
                        "notes":        notes,
                        "active_rules": rules,
                        "nb_rules":     len(rules),
                        "file_name":    "",
                    }
                    st.session_state.step = 2
                    st.rerun()

    # ── Étape 2 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 2:
        cfg = st.session_state.config
        st.markdown('<div class="step-header">Étape 2 — Upload du fichier client</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}** · **{cfg['nb_rules']} règle(s)**")
        st.info("Format : export **Package de Configuration BC** (.xlsx)")

        uploaded = st.file_uploader("Glissez-déposez ou cliquez", type=["xlsx","xls"], key="uploader_s5")

        if uploaded:
            st.session_state.config["file_name"] = uploaded.name
            with st.spinner("🔍 Lecture..."):
                parse_result = parse_uploaded_file(uploaded)
                st.session_state.parse_result = parse_result

            if not parse_result["success"]:
                for e in parse_result["errors"]: st.error(f"❌ {e}")
            else:
                summary = get_file_summary(parse_result)
                st.success(f"✅ **{uploaded.name}** — lecture réussie")
                c1,c2,c3 = st.columns(3)
                c1.metric("Tables de données",   summary.get("nb_data_tables",0))
                c2.metric("Tables de référence", summary.get("nb_ref_tables",0))
                c3.metric("Lignes de données",   summary.get("total_data_rows",0))
                st.markdown("---")
                for t in summary.get("data_tables",[]):
                    st.markdown(f'<div class="card-data"><span class="tag tag-data">DONNÉES</span><b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes</b></div>', unsafe_allow_html=True)

                ref_tables = parse_result.get("ref_tables",[])
                metadata   = parse_result.get("metadata",{})
                total_rows = parse_result.get("total_rows",{})
                with st.expander(f"📋 Tables de référence ({len(ref_tables)})"):
                    for sheet in ref_tables:
                        meta = metadata.get(sheet,{})
                        st.markdown(f'<div class="card-ref"><span class="tag tag-ref">RÉFÉRENCE</span><b>{sheet}</b> — {meta.get("label",sheet)} · {total_rows.get(sheet,0)} valeurs</div>', unsafe_allow_html=True)

                st.markdown("---")
                col_b, col_v = st.columns([2,3])
                with col_b:
                    if st.button("← Étape précédente", use_container_width=True):
                        st.session_state.step = 1; st.rerun()
                with col_v:
                    if st.button("🔍 Vérifier la structure →", type="primary", use_container_width=True, disabled=not summary.get("data_tables")):
                        with st.spinner("Validation structurelle..."):
                            validation = validate_file_structure(parse_result)
                            st.session_state.validation = validation
                        st.session_state.step = 3; st.rerun()
        else:
            col_b, _ = st.columns([2,8])
            with col_b:
                if st.button("← Étape précédente", use_container_width=True):
                    st.session_state.step = 1; st.rerun()

    # ── Étape 3 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 3:
        cfg        = st.session_state.config
        validation = st.session_state.validation
        pr         = st.session_state.parse_result

        st.markdown('<div class="step-header">Étape 3 — Vérification structurelle</div>', unsafe_allow_html=True)
        summary_val = validation.get("summary",{})
        if validation["is_valid"]: st.success(f"**{summary_val.get('status','✅ Conforme')}**")
        else:                      st.error(f"**{summary_val.get('status','❌ Non conforme')}**")

        for err in validation.get("blocking_errors",[]): st.error(err)
        for w   in validation.get("warnings",[]):        st.warning(w)
        for t   in validation.get("data_tables",[]):
            st.markdown(f'<div class="card-data"><span class="tag tag-data">DONNÉES</span><b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes · {t["cols"]} champs</b></div>', unsafe_allow_html=True)

        st.markdown("---")
        col_b, col_v = st.columns([2,4])
        with col_b:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step = 2
                st.session_state.parse_result = None
                st.session_state.validation   = None
                st.rerun()
        with col_v:
            if validation["is_valid"]:
                if st.button("🚀 Lancer l'analyse complète (Axe A + B) →", type="primary", use_container_width=True):
                    with st.spinner("⏳ Axe A..."):
                        axe_a = validate_file_axe_a(pr)
                        st.session_state.axe_a_result = axe_a
                    with st.spinner("⏳ Axe B..."):
                        axe_b = validate_file_axe_b(pr, profile_code=cfg.get("client_code",""))
                        st.session_state.axe_b_result = axe_b
                    st.session_state.saved_session_id = None
                    st.session_state.step = 4; st.rerun()
            else:
                st.error("❌ Corrigez les erreurs structurelles.")

    # ── Étape 4 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 4:
        cfg          = st.session_state.config
        axe_a        = st.session_state.axe_a_result
        axe_b        = st.session_state.axe_b_result
        parse_result = st.session_state.parse_result

        st.markdown('<div class="step-header">Étape 4 — Résultats de l\'analyse qualité</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}** · Fichier : **{cfg.get('file_name','')}**")

        a_total = axe_a.get("total_anomalies",0); b_total = axe_b.get("total_anomalies",0)
        a_major = axe_a.get("major",0);           b_major = axe_b.get("major",0)
        a_minor = axe_a.get("minor",0);           b_minor = axe_b.get("minor",0)
        b_info  = axe_b.get("info",0)
        total   = a_total + b_total
        major   = a_major + b_major
        minor   = a_minor + b_minor
        lines   = axe_a.get("lines_analyzed",0)

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        for col_w, val, lbl, color in [
            (c1, lines,   "Lignes",      "#1B3A6B"),
            (c2, total,   "Total",       "#993C1D" if total>0 else "#0F6E56"),
            (c3, major,   "🔴 Majeures", "#993C1D" if major>0 else "#0F6E56"),
            (c4, a_total, "🔵 Axe A",    "#534AB7" if a_total>0 else "#64748B"),
            (c5, b_total, "🟢 Axe B",    "#0F6E56" if b_total>0 else "#64748B"),
            (c6, b_info,  "🔵 Infos",    "#2E6FBF"),
        ]:
            with col_w:
                st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{color}">{val}</p><p class="stat-lbl">{lbl}</p></div>', unsafe_allow_html=True)

        st.markdown("---")

        if total == 0 and b_info == 0:
            st.success("🎉 **Aucune anomalie !** Les données sont conformes.")
        else:
            rt1, rt2, rt3 = st.tabs(["📊 Résumé", f"🔵 Axe A ({a_total})", f"🟢 Axe B ({b_total})"])
            with rt1:
                all_a = axe_a.get("all_anomalies",[]) + axe_b.get("all_anomalies",[])
                real  = [a for a in all_a if a.get("Ligne",0) > 0]
                infos = [a for a in all_a if a.get("Ligne",0) == 0]
                if real:
                    def cs(row):
                        s = row.get("Sévérité","")
                        if s=="Majeure": return ["background-color:#FAECE7"]*len(row)
                        if s=="Mineure": return ["background-color:#FAEEDA"]*len(row)
                        return [""]*len(row)
                    st.dataframe(get_anomalies_dataframe(real).style.apply(cs,axis=1), use_container_width=True, hide_index=True, height=min(500,50+len(real)*35))
                if infos:
                    st.markdown("---")
                    for a in infos:
                        st.markdown(f'<div class="card-info"><span class="tag tag-info">INFO</span><b>{a["Champ"]}</b> — {a["Message"]}</div>', unsafe_allow_html=True)
            with rt2: display_axe_results(axe_a, "Axe A")
            with rt3: display_axe_results(axe_b, "Axe B")

        if parse_result:
            data_tables = parse_result.get("data_tables",[])
            metadata    = parse_result.get("metadata",{})
            if data_tables:
                with st.expander("👀 Données source"):
                    for sn in data_tables:
                        df = parse_result["sheets"].get(sn)
                        if df is not None and not df.empty:
                            meta = metadata.get(sn,{})
                            st.markdown(f"**{sn}** — {meta.get('label','')} · {len(df)} lignes")
                            st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        st.markdown("---")
        col_b, col_r, col_s, col_st = st.columns([2,2,3,3])
        with col_b:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step = 3
                st.session_state.axe_a_result  = None
                st.session_state.axe_b_result  = None
                st.session_state.saved_session_id = None
                st.rerun()
        with col_r:
            if st.button("🔄 Recommencer", use_container_width=True):
                reset_session(); st.rerun()
        with col_s:
            if st.session_state.saved_session_id:
                st.markdown(f'<div class="save-box">✅ <b>Sauvegardée</b><br><span style="font-size:11px;color:#64748B">{st.session_state.saved_session_id}</span></div>', unsafe_allow_html=True)
            else:
                if st.button("💾 Sauvegarder la session", type="primary", use_container_width=True):
                    ok, res = save_session({
                        "session_name":    cfg["session_name"],
                        "profile_code":    cfg["client_code"],
                        "file_name":       cfg.get("file_name",""),
                        "notes":           cfg.get("notes",""),
                        "status":          "Analyse terminée" if major > 0 else "Terminée",
                        "total_anomalies": total,
                        "major_anomalies": major,
                        "minor_anomalies": minor,
                    })
                    if ok:
                        st.session_state.saved_session_id = res
                        st.success("✅ Session sauvegardée !")
                        st.rerun()
                    else:
                        st.error(f"❌ {res}")
        with col_st:
            if major == 0: st.success("✅ Prêt pour Axe C — Sprint 6")
            else:          st.warning(f"⚠️ {major} anomalie(s) majeure(s)")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — MES SESSIONS (avec édition / suppression)
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    st.markdown("### 📋 Mes sessions de contrôle")

    # Init session state pour cet onglet
    for key, default in [
        ("edit_session_id",    None),
        ("confirm_delete_ses", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    profiles = get_profiles_for_select()

    # Filtre par client
    col_f1, col_f2 = st.columns([3, 7])
    with col_f1:
        filter_opts   = ["Tous les clients"] + [p["label"] for p in profiles]
        filter_choice = st.selectbox("Filtrer par client", filter_opts, key="filter_ses")

    filter_code = None
    if filter_choice != "Tous les clients":
        filter_code = next((p["code"] for p in profiles if p["label"] == filter_choice), None)

    sessions = get_all_sessions(profile_code=filter_code)
    st.markdown("---")

    if not sessions:
        st.info("Aucune session. Créez-en une et cliquez sur **💾 Sauvegarder**.")
    else:
        st.markdown(f"**{len(sessions)} session(s)**")

        for s in sessions:
            sid          = s.get("id","")
            status       = s.get("status","Nouvelle")
            status_color = STATUS_COLORS.get(status,"#64748B")
            status_icon  = STATUS_ICONS.get(status,"")
            total_a      = s.get("total_anomalies",0)
            major_a      = s.get("major_anomalies",0)
            minor_a      = s.get("minor_anomalies",0)
            created      = s.get("created_at","")[:16].replace("T"," ") if s.get("created_at") else ""
            updated      = s.get("updated_at","")[:16].replace("T"," ") if s.get("updated_at") else ""
            file_name    = s.get("file_name","")

            anomaly_str = (
                f'<span style="color:#993C1D">🔴 {major_a} majeures</span> · '
                f'<span style="color:#854F0B">🟠 {minor_a} mineures</span>'
                if total_a > 0 else
                '<span style="color:#0F6E56">✅ Aucune anomalie</span>'
            )

            col_info, col_actions = st.columns([7, 3])

            with col_info:
                st.markdown(
                    f'<div class="card-session">'
                    f'<p class="session-name">{s.get("name","")}</p>'
                    f'<p class="session-meta">'
                    f'Client : <b>{s.get("profile_code","")}</b> · '
                    f'<span style="color:{status_color};font-weight:500">'
                    f'{status_icon} {status}</span>'
                    f'</p>'
                    f'<p class="session-meta">{anomaly_str}</p>'
                    f'<p class="session-meta">'
                    f'{"📄 " + file_name + " · " if file_name else ""}'
                    f'🕐 Créée {created}'
                    f'{"  ·  ✏️ Modifiée " + updated if updated != created else ""}'
                    f'</p>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            with col_actions:
                st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
                ca, cb = st.columns(2)
                with ca:
                    if st.button("✏️ Éditer", key=f"edit_s_{sid}", use_container_width=True):
                        st.session_state.edit_session_id    = sid
                        st.session_state.confirm_delete_ses = None
                with cb:
                    if st.button("🗑️", key=f"del_s_{sid}", use_container_width=True, help="Supprimer"):
                        st.session_state.confirm_delete_ses = sid
                        st.session_state.edit_session_id    = None
                st.markdown("</div>", unsafe_allow_html=True)

            # ── Formulaire d'édition ──────────────────────────────────────────
            if st.session_state.edit_session_id == sid:
                with st.container():
                    st.markdown("---")
                    st.markdown(f"**✏️ Modifier la session — {s.get('name','')}**")

                    e1, e2 = st.columns(2)
                    with e1:
                        new_name = st.text_input(
                            "Nom de la session",
                            value=s.get("name",""),
                            key=f"ename_{sid}"
                        )
                        new_status = st.selectbox(
                            "Statut",
                            SESSION_STATUSES,
                            index=SESSION_STATUSES.index(status) if status in SESSION_STATUSES else 0,
                            key=f"estatus_{sid}"
                        )
                    with e2:
                        new_notes = st.text_area(
                            "Notes",
                            value=s.get("notes",""),
                            height=100,
                            key=f"enotes_{sid}"
                        )

                    cs, cc, _ = st.columns([2, 2, 6])
                    with cs:
                        if st.button("💾 Enregistrer", key=f"esave_{sid}",
                                     type="primary", use_container_width=True):
                            ok, err = update_session(sid, {
                                "name":   new_name.strip(),
                                "status": new_status,
                                "notes":  new_notes.strip(),
                            })
                            if ok:
                                st.success("✅ Session mise à jour !")
                                st.session_state.edit_session_id = None
                                st.rerun()
                            else:
                                st.error(f"❌ {err}")
                    with cc:
                        if st.button("Annuler", key=f"ecancel_{sid}", use_container_width=True):
                            st.session_state.edit_session_id = None
                            st.rerun()

                    st.markdown("---")

            # ── Confirmation suppression ──────────────────────────────────────
            if st.session_state.confirm_delete_ses == sid:
                st.warning(
                    f"⚠️ Supprimer la session **{s.get('name','')}** ? "
                    "Cette action est irréversible."
                )
                cy, cn, _ = st.columns([2, 2, 6])
                with cy:
                    if st.button("✅ Confirmer", key=f"dyes_{sid}", type="primary"):
                        ok, err = delete_session(sid)
                        if ok:
                            st.success("Session supprimée.")
                            st.session_state.confirm_delete_ses = None
                            st.rerun()
                        else:
                            st.error(f"❌ {err}")
                with cn:
                    if st.button("❌ Annuler", key=f"dno_{sid}"):
                        st.session_state.confirm_delete_ses = None
                        st.rerun()
