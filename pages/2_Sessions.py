"""
Page Sessions — Sprint 5 v2.
Ajouts : boutons retour entre toutes les étapes + sauvegarde session Supabase.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a, get_anomalies_dataframe
from app.core.validator_axe_b import validate_file_axe_b
from app.db.profiles_db import get_profiles_for_select
from app.db.rules_db import get_active_rules_for_profile
from app.db.sessions_db import save_session, get_all_sessions, SESSION_STATUSES, STATUS_COLORS

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
    .card-session { background:white;border:1px solid #E2E8F0;border-radius:10px;padding:14px 18px;margin-bottom:8px; }
    .session-name { font-size:14px;font-weight:600;color:#1B3A6B;margin:0; }
    .session-meta { font-size:12px;color:#64748B;margin:4px 0 0; }
    .stat-box   { background:white;border:1px solid #E2E8F0;border-radius:8px;padding:12px;text-align:center; }
    .stat-num   { font-size:2rem;font-weight:700;margin:0; }
    .stat-lbl   { font-size:11px;color:#64748B;margin:0; }
    .save-box   { background:#E1F5EE;border:1px solid #0F6E56;border-radius:8px;padding:12px 16px;margin:8px 0; }
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
# FONCTION HELPER — définie avant tout appel
# ════════════════════════════════════════════════════════════════════════════
def display_axe_results(axe_result: dict, axe_label: str):
    """Affiche les résultats d'un axe avec tabs par onglet."""
    total    = axe_result.get("total_anomalies", 0)
    major    = axe_result.get("major", 0)
    minor    = axe_result.get("minor", 0)
    info     = axe_result.get("info", 0)
    by_sheet = axe_result.get("by_sheet", {})

    if total == 0:
        st.success(f"✅ Aucune anomalie {axe_label} détectée.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total",       total)
    m2.metric("🔴 Majeures", major)
    m3.metric("🟠 Mineures", minor)
    m4.metric("🔵 Infos",    info)

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

    sheet_tabs = st.tabs(tab_labels)
    for tab, sheet_name in zip(sheet_tabs, sheet_names):
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
                t1.metric("Anomalies",    len(real_anomalies))
                t2.metric("🔴 Majeures",  nb_maj)
                t3.metric("🟠 Mineures",  nb_min)

                severities = sorted(set(a["Sévérité"] for a in real_anomalies))
                filter_sev = st.multiselect(
                    "Filtrer", severities, default=severities,
                    key=f"filt_{axe_label}_{sheet_name}"
                )
                filtered = [a for a in real_anomalies if a["Sévérité"] in filter_sev]

                if filtered:
                    df_an = get_anomalies_dataframe(filtered)

                    def color_row(row):
                        sev = row.get("Sévérité", "")
                        if sev == "Majeure": return ["background-color:#FAECE7"] * len(row)
                        if sev == "Mineure": return ["background-color:#FAEEDA"] * len(row)
                        return [""] * len(row)

                    st.dataframe(
                        df_an.style.apply(color_row, axis=1),
                        use_container_width=True, hide_index=True,
                        height=min(400, 50 + len(filtered) * 35)
                    )

                    with st.expander("📋 Détail des anomalies"):
                        for a in filtered[:50]:
                            css = "card-major" if a["Sévérité"] == "Majeure" else "card-minor"
                            fix = (
                                f" → Suggestion : <b>{a['Correction suggérée']}</b>"
                                if a.get("Correction suggérée") else ""
                            )
                            st.markdown(
                                f'<div class="{css}">'
                                f'<b>Ligne {a["Ligne"]}</b> · <b>{a["Champ"]}</b> · '
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
                st.markdown("**ℹ️ Champs non vérifiables :**")
                for a in info_anomalies:
                    st.markdown(
                        f'<div class="card-info">'
                        f'<span class="tag tag-info">INFO</span>'
                        f'<b>{a["Champ"]}</b> — {a["Message"]}'
                        f'</div>',
                        unsafe_allow_html=True
                    )


def reset_session():
    """Réinitialise complètement la session."""
    for k in ["step", "config", "parse_result", "validation",
              "axe_a_result", "axe_b_result", "saved_session_id"]:
        st.session_state[k] = (
            1 if k == "step" else
            {} if k == "config" else None
        )


# ════════════════════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# 📁 Sessions de contrôle")
st.markdown("---")

tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

with tab1:

    for key, default in [
        ("step", 1), ("config", {}),
        ("parse_result", None), ("validation", None),
        ("axe_a_result", None), ("axe_b_result", None),
        ("saved_session_id", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Barre de progression ──────────────────────────────────────────────────
    steps = ["Informations", "Upload", "Structure", "Analyse A + B"]
    cols  = st.columns(len(steps))
    for i, (col, name) in enumerate(zip(cols, steps), 1):
        with col:
            if i < st.session_state.step:
                st.markdown(f"✅ **{name}**")
            elif i == st.session_state.step:
                st.markdown(f"🔵 **{name}** ←")
            else:
                st.markdown(f"⬜ {name}")
    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 1 — Informations
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.step == 1:

        st.markdown(
            '<div class="step-header">Étape 1 — Informations de la session</div>',
            unsafe_allow_html=True
        )
        col1, col2 = st.columns(2)
        with col1:
            session_name = st.text_input(
                "Nom de la session *",
                placeholder="Ex : ABC - Clients - Juin 2026"
            )
            profiles = get_profiles_for_select()
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
                        st.markdown(
                            f'<div class="card-rule"><b>{r.get("label","")}</b> '
                            f'— {r.get("rule_type","")} ({r.get("severity","Mineure")})'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                    if len(rules) > 4:
                        st.caption(f"... et {len(rules)-4} autre(s).")
                else:
                    st.info("Aucune règle métier pour ce client.")

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

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 2 — Upload
    # ══════════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 2:

        cfg = st.session_state.config
        st.markdown(
            '<div class="step-header">Étape 2 — Upload du fichier client</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · "
            f"Client : **{cfg['client_name']}** · "
            f"**{cfg['nb_rules']} règle(s)**"
        )

        st.info("Format attendu : export **Package de Configuration BC** (.xlsx)")

        uploaded = st.file_uploader(
            "Glissez-déposez ou cliquez pour parcourir",
            type=["xlsx","xls"], key="uploader_s5"
        )

        if uploaded:
            # Mémoriser le nom de fichier
            st.session_state.config["file_name"] = uploaded.name

            with st.spinner("🔍 Lecture et détection..."):
                parse_result = parse_uploaded_file(uploaded)
                st.session_state.parse_result = parse_result

            if not parse_result["success"]:
                for e in parse_result["errors"]: st.error(f"❌ {e}")
            else:
                summary = get_file_summary(parse_result)
                st.success(f"✅ **{uploaded.name}** — lecture réussie")

                c1, c2, c3 = st.columns(3)
                c1.metric("Tables de données",   summary.get("nb_data_tables", 0))
                c2.metric("Tables de référence", summary.get("nb_ref_tables",  0),
                          help="Utilisées pour la validation Axe B")
                c3.metric("Lignes de données",   summary.get("total_data_rows", 0))

                st.markdown("---")
                for t in summary.get("data_tables", []):
                    st.markdown(
                        f'<div class="card-data">'
                        f'<span class="tag tag-data">DONNÉES</span>'
                        f'<b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes</b>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                ref_tables = parse_result.get("ref_tables", [])
                metadata   = parse_result.get("metadata", {})
                total_rows = parse_result.get("total_rows", {})
                with st.expander(f"📋 Tables de référence ({len(ref_tables)})"):
                    for sheet in ref_tables:
                        meta = metadata.get(sheet, {})
                        st.markdown(
                            f'<div class="card-ref">'
                            f'<span class="tag tag-ref">RÉFÉRENCE</span>'
                            f'<b>{sheet}</b> — {meta.get("label",sheet)} '
                            f'· {total_rows.get(sheet,0)} valeurs</div>',
                            unsafe_allow_html=True
                        )

                st.markdown("---")
                col_b, col_v = st.columns([2, 3])
                with col_b:
                    if st.button("← Étape précédente", use_container_width=True):
                        st.session_state.step = 1
                        st.rerun()
                with col_v:
                    if st.button(
                        "🔍 Vérifier la structure →",
                        type="primary", use_container_width=True,
                        disabled=not summary.get("data_tables")
                    ):
                        with st.spinner("Validation structurelle..."):
                            validation = validate_file_structure(parse_result)
                            st.session_state.validation = validation
                        st.session_state.step = 3
                        st.rerun()
        else:
            col_b, _ = st.columns([2, 8])
            with col_b:
                if st.button("← Étape précédente", use_container_width=True):
                    st.session_state.step = 1
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 3 — Structure
    # ══════════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 3:

        cfg        = st.session_state.config
        validation = st.session_state.validation
        pr         = st.session_state.parse_result

        st.markdown(
            '<div class="step-header">Étape 3 — Vérification structurelle</div>',
            unsafe_allow_html=True
        )

        summary_val = validation.get("summary", {})
        if validation["is_valid"]:
            st.success(f"**{summary_val.get('status','✅ Structure conforme')}**")
        else:
            st.error(f"**{summary_val.get('status','❌ Non conforme')}**")

        if validation["blocking_errors"]:
            for err in validation["blocking_errors"]: st.error(err)
        if validation["warnings"]:
            for w in validation["warnings"]: st.warning(w)
        if validation["data_tables"]:
            for t in validation["data_tables"]:
                st.markdown(
                    f'<div class="card-data">'
                    f'<span class="tag tag-data">DONNÉES</span>'
                    f'<b>{t["sheet"]}</b> — {t["label"]} · '
                    f'<b>{t["rows"]} lignes · {t["cols"]} champs</b></div>',
                    unsafe_allow_html=True
                )

        st.markdown("---")
        col_b, col_v = st.columns([2, 4])
        with col_b:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step = 2
                st.session_state.parse_result = None
                st.session_state.validation   = None
                st.rerun()
        with col_v:
            if validation["is_valid"]:
                if st.button(
                    "🚀 Lancer l'analyse complète (Axe A + B) →",
                    type="primary", use_container_width=True
                ):
                    client_code = cfg.get("client_code", "")
                    with st.spinner("⏳ Analyse Axe A — Contraintes BC..."):
                        axe_a = validate_file_axe_a(pr)
                        st.session_state.axe_a_result = axe_a
                    with st.spinner("⏳ Analyse Axe B — Références BC..."):
                        axe_b = validate_file_axe_b(pr, profile_code=client_code)
                        st.session_state.axe_b_result = axe_b
                    st.session_state.saved_session_id = None
                    st.session_state.step = 4
                    st.rerun()
            else:
                st.error("❌ Corrigez les erreurs structurelles.")

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 4 — Résultats Axe A + B
    # ══════════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 4:

        cfg          = st.session_state.config
        axe_a        = st.session_state.axe_a_result
        axe_b        = st.session_state.axe_b_result
        parse_result = st.session_state.parse_result

        st.markdown(
            '<div class="step-header">Étape 4 — Résultats de l\'analyse qualité</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · "
            f"Client : **{cfg['client_name']}** · "
            f"Fichier : **{cfg.get('file_name','')}**"
        )

        # Métriques
        a_total = axe_a.get("total_anomalies", 0)
        b_total = axe_b.get("total_anomalies", 0)
        a_major = axe_a.get("major", 0)
        b_major = axe_b.get("major", 0)
        a_minor = axe_a.get("minor", 0)
        b_minor = axe_b.get("minor", 0)
        b_info  = axe_b.get("info",  0)
        total   = a_total + b_total
        major   = a_major + b_major
        minor   = a_minor + b_minor
        lines   = axe_a.get("lines_analyzed", 0)

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.markdown(f'<div class="stat-box"><p class="stat-num">{lines}</p><p class="stat-lbl">Lignes</p></div>', unsafe_allow_html=True)
        with c2:
            col = "#993C1D" if total > 0 else "#0F6E56"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{total}</p><p class="stat-lbl">Total</p></div>', unsafe_allow_html=True)
        with c3:
            col = "#993C1D" if major > 0 else "#0F6E56"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{major}</p><p class="stat-lbl">🔴 Majeures</p></div>', unsafe_allow_html=True)
        with c4:
            col = "#534AB7" if a_total > 0 else "#64748B"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{a_total}</p><p class="stat-lbl">🔵 Axe A</p></div>', unsafe_allow_html=True)
        with c5:
            col = "#0F6E56" if b_total > 0 else "#64748B"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{b_total}</p><p class="stat-lbl">🟢 Axe B</p></div>', unsafe_allow_html=True)
        with c6:
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:#2E6FBF">{b_info}</p><p class="stat-lbl">🔵 Infos</p></div>', unsafe_allow_html=True)

        st.markdown("---")

        if total == 0 and b_info == 0:
            st.success("🎉 **Aucune anomalie !** Les données sont conformes.")
        else:
            result_tab1, result_tab2, result_tab3 = st.tabs([
                "📊 Résumé global",
                f"🔵 Axe A — Contraintes BC ({a_total})",
                f"🟢 Axe B — Références BC ({b_total})",
            ])

            with result_tab1:
                st.markdown("### Vue consolidée")
                all_anomalies  = (
                    axe_a.get("all_anomalies", []) +
                    axe_b.get("all_anomalies", [])
                )
                real_anomalies = [a for a in all_anomalies if a.get("Ligne", 0) > 0]
                info_anomalies = [a for a in all_anomalies if a.get("Ligne", 0) == 0]

                if real_anomalies:
                    df_all = get_anomalies_dataframe(real_anomalies)
                    def color_summary(row):
                        sev = row.get("Sévérité", "")
                        if sev == "Majeure": return ["background-color:#FAECE7"] * len(row)
                        if sev == "Mineure": return ["background-color:#FAEEDA"] * len(row)
                        return [""] * len(row)
                    st.dataframe(
                        df_all.style.apply(color_summary, axis=1),
                        use_container_width=True, hide_index=True,
                        height=min(500, 50 + len(real_anomalies) * 35)
                    )
                if info_anomalies:
                    st.markdown("---")
                    st.markdown("**ℹ️ Champs non vérifiables :**")
                    for a in info_anomalies:
                        st.markdown(
                            f'<div class="card-info">'
                            f'<span class="tag tag-info">INFO</span>'
                            f'<b>{a["Champ"]}</b> — {a["Message"]}'
                            f'</div>',
                            unsafe_allow_html=True
                        )

            with result_tab2:
                display_axe_results(axe_a, "Axe A")

            with result_tab3:
                display_axe_results(axe_b, "Axe B")

        # Prévisualisation
        if parse_result:
            data_tables = parse_result.get("data_tables", [])
            metadata    = parse_result.get("metadata", {})
            if data_tables:
                with st.expander("👀 Données source"):
                    for sn in data_tables:
                        df = parse_result["sheets"].get(sn)
                        if df is not None and not df.empty:
                            meta = metadata.get(sn, {})
                            st.markdown(f"**{sn}** — {meta.get('label','')} · {len(df)} lignes")
                            st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Barre d'actions ───────────────────────────────────────────────────
        col_back, col_restart, col_save, col_status = st.columns([2, 2, 3, 3])

        with col_back:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step = 3
                st.session_state.axe_a_result  = None
                st.session_state.axe_b_result  = None
                st.session_state.saved_session_id = None
                st.rerun()

        with col_restart:
            if st.button("🔄 Recommencer", use_container_width=True):
                reset_session()
                st.rerun()

        with col_save:
            # Désactiver si déjà sauvegardé
            already_saved = bool(st.session_state.saved_session_id)

            if already_saved:
                st.markdown(
                    f'<div class="save-box">'
                    f'✅ <b>Session sauvegardée</b><br>'
                    f'<span style="font-size:11px;color:#64748B">'
                    f'ID : {st.session_state.saved_session_id}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            else:
                if st.button(
                    "💾 Sauvegarder la session",
                    type="primary",
                    use_container_width=True,
                    help="Enregistre la session et ses résultats dans Supabase"
                ):
                    session_data = {
                        "session_name":    cfg["session_name"],
                        "profile_code":    cfg["client_code"],
                        "file_name":       cfg.get("file_name", ""),
                        "notes":           cfg.get("notes", ""),
                        "status":          (
                            "Analyse terminée"
                            if major > 0 else "Terminée"
                        ),
                        "total_anomalies": total,
                        "major_anomalies": major,
                        "minor_anomalies": minor,
                        "iteration":       1,
                    }
                    ok, result = save_session(session_data)
                    if ok:
                        st.session_state.saved_session_id = result
                        st.success(f"✅ Session sauvegardée !")
                        st.rerun()
                    else:
                        st.error(f"❌ {result}")

        with col_status:
            if major == 0:
                st.success("✅ Prêt pour Axe C — Sprint 6")
            else:
                st.warning(f"⚠️ {major} anomalie(s) majeure(s)")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — MES SESSIONS
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    st.markdown("### 📋 Mes sessions de contrôle")

    profiles = get_profiles_for_select()

    # Filtre par client
    col_f1, col_f2 = st.columns([3, 7])
    with col_f1:
        filter_options = ["Tous les clients"] + [p["label"] for p in profiles]
        filter_choice  = st.selectbox("Filtrer par client", filter_options, key="filter_sessions")

    filter_code = None
    if filter_choice != "Tous les clients":
        filter_code = next(
            (p["code"] for p in profiles if p["label"] == filter_choice), None
        )

    sessions = get_all_sessions(profile_code=filter_code)

    st.markdown("---")

    if not sessions:
        st.info(
            "Aucune session sauvegardée. "
            "Créez une session et cliquez sur **💾 Sauvegarder la session**."
        )
    else:
        st.markdown(f"**{len(sessions)} session(s)**")

        for s in sessions:
            status       = s.get("status", "Nouvelle")
            status_color = STATUS_COLORS.get(status, "#64748B")
            total_a      = s.get("total_anomalies", 0)
            major_a      = s.get("major_anomalies", 0)
            minor_a      = s.get("minor_anomalies", 0)
            created      = s.get("created_at", "")[:16].replace("T", " ") if s.get("created_at") else ""
            file_name    = s.get("file_name", "")

            anomaly_info = ""
            if total_a > 0:
                anomaly_info = (
                    f' · <span style="color:#993C1D">🔴 {major_a}</span>'
                    f' · <span style="color:#854F0B">🟠 {minor_a}</span>'
                )
            else:
                anomaly_info = ' · <span style="color:#0F6E56">✅ Aucune anomalie</span>'

            st.markdown(
                f'<div class="card-session">'
                f'<p class="session-name">{s.get("name","")}</p>'
                f'<p class="session-meta">'
                f'Client : <b>{s.get("profile_code","")}</b> · '
                f'<span style="color:{status_color};font-weight:500">{status}</span>'
                f'{anomaly_info}'
                f'</p>'
                f'<p class="session-meta">'
                f'{"📄 " + file_name + " · " if file_name else ""}'
                f'🕐 {created}'
                f'</p>'
                f'</div>',
                unsafe_allow_html=True
            )
