"""
Page Sessions — Sprint 4.
Ajout de l'étape de validation Axe A.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a, get_anomalies_dataframe
from app.db.profiles_db import get_profiles_for_select
from app.db.rules_db import get_active_rules_for_profile

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
    .stat-box   { background:white;border:1px solid #E2E8F0;border-radius:8px;padding:12px;text-align:center; }
    .stat-num   { font-size:2rem;font-weight:700;margin:0; }
    .stat-lbl   { font-size:11px;color:#64748B;margin:0; }
    .tag { display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;margin-right:4px; }
    .tag-major { background:#993C1D;color:white; }
    .tag-minor { background:#854F0B;color:white; }
    .tag-data  { background:#0F6E56;color:white; }
    .tag-ref   { background:#2E6FBF;color:white; }
    #MainMenu { visibility:hidden; } footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 📁 Sessions de contrôle")
st.markdown("---")

tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

with tab1:

    for key, default in [
        ("step", 1), ("config", {}),
        ("parse_result", None), ("validation", None),
        ("axe_a_result", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Barre de progression
    steps = ["Informations", "Upload", "Structure", "Axe A"]
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
    # ÉTAPE 1
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
                            f'— {r.get("rule_type","")} ({r.get("severity","Mineure")})</div>',
                            unsafe_allow_html=True
                        )
                    if len(rules) > 4: st.caption(f"... et {len(rules)-4} autre(s).")
                else:
                    st.info("Aucune règle métier pour ce client.")

        st.markdown("---")
        col_btn, _ = st.columns([2, 8])
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
                    }
                    st.session_state.step = 2
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 2
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
            type=["xlsx","xls"], key="uploader_s4"
        )

        if uploaded:
            with st.spinner("🔍 Lecture et détection..."):
                parse_result = parse_uploaded_file(uploaded)
                st.session_state.parse_result = parse_result

            if not parse_result["success"]:
                for e in parse_result["errors"]: st.error(f"❌ {e}")
            else:
                summary = get_file_summary(parse_result)
                st.success(f"✅ **{uploaded.name}** — lecture réussie")

                c1, c2, c3 = st.columns(3)
                c1.metric("Tables de données",  summary.get("nb_data_tables", 0))
                c2.metric("Tables de référence", summary.get("nb_ref_tables",  0))
                c3.metric("Lignes de données",   summary.get("total_data_rows", 0))

                st.markdown("---")
                for t in summary.get("data_tables", []):
                    st.markdown(
                        f'<div class="card-data"><span class="tag tag-data">DONNÉES</span>'
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
                            f'<div class="card-ref"><span class="tag tag-ref">RÉFÉRENCE</span>'
                            f'<b>{sheet}</b> — {meta.get("label",sheet)} '
                            f'· {total_rows.get(sheet,0)} valeurs</div>',
                            unsafe_allow_html=True
                        )

                st.markdown("---")
                col_b, col_v, _ = st.columns([2, 3, 5])
                with col_b:
                    if st.button("← Retour", use_container_width=True):
                        st.session_state.step = 1; st.rerun()
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
            if st.button("← Retour"): st.session_state.step = 1; st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 3
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
                    f'<div class="card-data"><span class="tag tag-data">DONNÉES</span>'
                    f'<b>{t["sheet"]}</b> — {t["label"]} · '
                    f'<b>{t["rows"]} lignes · {t["cols"]} champs</b></div>',
                    unsafe_allow_html=True
                )

        st.markdown("---")
        col1, col2, col3, _ = st.columns([2, 2, 3, 3])
        with col1:
            if st.button("← Changer fichier", use_container_width=True):
                st.session_state.step = 2
                st.session_state.parse_result = None
                st.session_state.validation = None
                st.rerun()
        with col2:
            if st.button("← Recommencer", use_container_width=True):
                for k in ["step","config","parse_result","validation","axe_a_result"]:
                    st.session_state[k] = 1 if k=="step" else ({} if k=="config" else None)
                st.rerun()
        with col3:
            if validation["is_valid"]:
                if st.button("🔍 Analyser Axe A →", type="primary", use_container_width=True):
                    with st.spinner("Analyse Axe A..."):
                        axe_a = validate_file_axe_a(pr)
                        st.session_state.axe_a_result = axe_a
                    st.session_state.step = 4
                    st.rerun()
            else:
                st.error("❌ Corrigez d'abord les erreurs structurelles.")

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 4 — Résultats Axe A
    # ══════════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 4:

        cfg          = st.session_state.config
        axe_a        = st.session_state.axe_a_result
        parse_result = st.session_state.parse_result

        st.markdown(
            '<div class="step-header">Étape 4 — Résultats Axe A — Contraintes BC</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · "
            f"Client : **{cfg['client_name']}**"
        )

        # Métriques
        total = axe_a.get("total_anomalies", 0)
        major = axe_a.get("major", 0)
        minor = axe_a.get("minor", 0)
        lines = axe_a.get("lines_analyzed", 0)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="stat-box"><p class="stat-num">{lines}</p><p class="stat-lbl">Lignes analysées</p></div>', unsafe_allow_html=True)
        with c2:
            col = "#993C1D" if total>0 else "#0F6E56"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{total}</p><p class="stat-lbl">Total anomalies</p></div>', unsafe_allow_html=True)
        with c3:
            col = "#993C1D" if major>0 else "#0F6E56"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{major}</p><p class="stat-lbl">🔴 Majeures</p></div>', unsafe_allow_html=True)
        with c4:
            col = "#854F0B" if minor>0 else "#0F6E56"
            st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{minor}</p><p class="stat-lbl">🟠 Mineures</p></div>', unsafe_allow_html=True)

        st.markdown("---")

        if total == 0:
            st.success("🎉 **Aucune anomalie Axe A !** Les données sont conformes aux contraintes BC.")
        else:
            by_sheet = axe_a.get("by_sheet", {})
            sheet_names = list(by_sheet.keys())

            tab_labels = []
            for s in sheet_names:
                nb     = len(by_sheet[s])
                nb_maj = sum(1 for a in by_sheet[s] if a["Sévérité"]=="Majeure")
                icon   = "🔴" if nb_maj > 0 else ("🟠" if nb > 0 else "✅")
                tab_labels.append(f"{icon} {s} ({nb})")

            sheet_tabs = st.tabs(tab_labels) if tab_labels else []

            for tab, sheet_name in zip(sheet_tabs, sheet_names):
                with tab:
                    anomalies = by_sheet.get(sheet_name, [])
                    if not anomalies:
                        st.success(f"✅ Aucune anomalie.")
                        continue

                    nb_maj = sum(1 for a in anomalies if a["Sévérité"]=="Majeure")
                    nb_min = sum(1 for a in anomalies if a["Sévérité"]=="Mineure")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total",     len(anomalies))
                    m2.metric("🔴 Majeures", nb_maj)
                    m3.metric("🟠 Mineures", nb_min)

                    # Filtre
                    severities  = sorted(set(a["Sévérité"] for a in anomalies))
                    filter_sev  = st.multiselect(
                        "Filtrer par sévérité", severities,
                        default=severities, key=f"filt_{sheet_name}"
                    )
                    filtered = [a for a in anomalies if a["Sévérité"] in filter_sev]

                    if filtered:
                        # Tableau coloré
                        df_an = get_anomalies_dataframe(filtered)

                        def color_row(row):
                            sev = row.get("Sévérité","")
                            if sev == "Majeure": return ["background-color:#FAECE7"] * len(row)
                            if sev == "Mineure": return ["background-color:#FAEEDA"] * len(row)
                            return [""] * len(row)

                        st.dataframe(
                            df_an.style.apply(color_row, axis=1),
                            use_container_width=True,
                            hide_index=True,
                            height=min(400, 50 + len(filtered)*35)
                        )

                        # Détail en cartes
                        with st.expander("📋 Détail des anomalies"):
                            for a in filtered[:50]:
                                css = "card-major" if a["Sévérité"]=="Majeure" else "card-minor"
                                fix = f" → Suggestion : <b>{a['Correction suggérée']}</b>" if a.get("Correction suggérée") else ""
                                st.markdown(
                                    f'<div class="{css}">'
                                    f'<b>Ligne {a["Ligne"]}</b> · '
                                    f'<b>{a["Champ"]}</b> · '
                                    f'<span class="tag tag-{"major" if a["Sévérité"]=="Majeure" else "minor"}">{a["Sévérité"]}</span>'
                                    f'<span class="tag" style="background:#E2E8F0;color:#1B3A6B">{a["Type d\'anomalie"]}</span>'
                                    f'<br>{a["Message"]}{fix}</div>',
                                    unsafe_allow_html=True
                                )
                            if len(filtered) > 50:
                                st.caption(f"50 premières sur {len(filtered)} anomalies.")

        # Prévisualisation
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
        col1, col2, col3, _ = st.columns([2, 2, 3, 3])
        with col1:
            if st.button("← Recommencer", use_container_width=True):
                for k in ["step","config","parse_result","validation","axe_a_result"]:
                    st.session_state[k] = 1 if k=="step" else ({} if k=="config" else None)
                st.rerun()
        with col2:
            if st.button("↩ Changer fichier", use_container_width=True):
                st.session_state.step = 2
                st.session_state.parse_result = None
                st.session_state.validation   = None
                st.session_state.axe_a_result = None
                st.rerun()
        with col3:
            if major == 0:
                st.success("✅ Prêt pour l'Axe B — Sprint 5")
            else:
                st.warning(f"⚠️ {major} anomalie(s) majeure(s) à corriger.")

with tab2:
    st.info("🚧 **Sprint 9** — Historique des sessions.")
