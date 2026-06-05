"""
Page Sessions — Sprint 2.
Client chargé depuis Supabase avec ses règles métier.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
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
    .card-data {
        background: #E1F5EE; border-left: 4px solid #0F6E56;
        border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;
    }
    .card-ref {
        background: #EFF6FF; border-left: 4px solid #2E6FBF;
        border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;
    }
    .card-rule {
        background: #EEEDFE; border-left: 3px solid #534AB7;
        border-radius: 6px; padding: 8px 12px;
        margin-bottom: 6px; font-size: 12px;
    }
    .tag {
        display: inline-block; font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 4px; margin-right: 6px;
    }
    .tag-data { background: #0F6E56; color: white; }
    .tag-ref  { background: #2E6FBF; color: white; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 📁 Sessions de contrôle")
st.markdown("---")

tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

with tab1:

    for key, default in [
        ("step", 1), ("config", {}),
        ("parse_result", None), ("validation", None)
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Barre de progression
    steps = ["Informations", "Upload & Détection", "Résultats"]
    cols = st.columns(len(steps))
    for i, (col, name) in enumerate(zip(cols, steps), 1):
        with col:
            if i < st.session_state.step:
                st.markdown(f"✅ **{name}**")
            elif i == st.session_state.step:
                st.markdown(f"🔵 **{name}** ←")
            else:
                st.markdown(f"⬜ {name}")
    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════
    # ÉTAPE 1
    # ══════════════════════════════════════════════════════════════════════
    if st.session_state.step == 1:

        st.markdown(
            '<div class="step-header">Étape 1 — Informations de la session</div>',
            unsafe_allow_html=True
        )

        col1, col2 = st.columns(2)
        with col1:
            session_name = st.text_input(
                "Nom de la session *",
                placeholder="Ex: ABC Distribution - Migration Clients - Juin 2026"
            )

            profiles = get_profiles_for_select()
            if profiles:
                options = ["— Sélectionner un client —"] + [p["label"] for p in profiles]
                choice = st.selectbox("Client *", options)
                selected = next((p for p in profiles if p["label"] == choice), None)
            else:
                st.warning("Aucun profil client. Créez-en un dans **Profils Clients**.")
                selected = None

        with col2:
            notes = st.text_area("Notes (optionnel)", height=60)

            if selected:
                rules = get_active_rules_for_profile(selected["code"])
                if rules:
                    st.markdown(f"**⚙️ {len(rules)} règle(s) active(s) chargée(s) :**")
                    for r in rules[:4]:
                        st.markdown(
                            f'<div class="card-rule">'
                            f'<b>{r.get("label", "")}</b> '
                            f'— {r.get("rule_type", "")} '
                            f'({r.get("severity", "Mineure")})'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                    if len(rules) > 4:
                        st.caption(f"... et {len(rules) - 4} autre(s) règle(s).")
                else:
                    st.info("Ce client n'a pas encore de règles métier.")

        st.markdown("---")
        col_btn, _ = st.columns([2, 8])
        with col_btn:
            if st.button("Suivant →", type="primary", use_container_width=True):
                errors = []
                if not session_name.strip():
                    errors.append("Nom de session obligatoire.")
                if not selected:
                    errors.append("Sélectionnez un client.")
                if errors:
                    for e in errors:
                        st.error(e)
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

    # ══════════════════════════════════════════════════════════════════════
    # ÉTAPE 2
    # ══════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 2:

        cfg = st.session_state.config
        st.markdown(
            '<div class="step-header">'
            'Étape 2 — Upload du fichier & Détection automatique'
            '</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · "
            f"Client : **{cfg['client_name']}** · "
            f"**{cfg['nb_rules']} règle(s)** chargée(s)"
        )

        st.markdown("### 📎 Charger le fichier Excel reçu du client")
        st.info(
            "Format attendu : export **Package de Configuration BC** "
            "(.xlsx — en-têtes en ligne 3, données à partir de la ligne 4)."
        )

        uploaded = st.file_uploader(
            "Glissez-déposez ou cliquez pour parcourir",
            type=["xlsx", "xls"], key="uploader_s2"
        )

        if uploaded:
            with st.spinner("🔍 Lecture et détection automatique des tables..."):
                parse_result = parse_uploaded_file(uploaded)
                st.session_state.parse_result = parse_result

            if not parse_result["success"]:
                for e in parse_result["errors"]:
                    st.error(f"❌ {e}")
            else:
                summary = get_file_summary(parse_result)
                st.success(f"✅ **{uploaded.name}** — lecture réussie")

                c1, c2, c3 = st.columns(3)
                c1.metric("Tables de données", summary.get("nb_data_tables", 0),
                          help="Tables où le client a saisi ses données")
                c2.metric("Tables de référence", summary.get("nb_ref_tables", 0),
                          help="Listes de valeurs BC")
                c3.metric("Lignes de données", summary.get("total_data_rows", 0))

                st.markdown("---")
                st.markdown("### 📊 Tables de données détectées")

                data_tables = summary.get("data_tables", [])
                for t in data_tables:
                    st.markdown(
                        f'<div class="card-data">'
                        f'<span class="tag tag-data">DONNÉES</span>'
                        f'<b>{t["sheet"]}</b> — {t["label"]} '
                        f'(Table {t["table_id"]}) · <b>{t["rows"]} lignes</b>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                ref_tables = parse_result.get("ref_tables", [])
                metadata   = parse_result.get("metadata", {})
                total_rows = parse_result.get("total_rows", {})
                with st.expander(f"📋 Tables de référence ({len(ref_tables)})"):
                    for sheet in ref_tables:
                        meta = metadata.get(sheet, {})
                        rows = total_rows.get(sheet, 0)
                        st.markdown(
                            f'<div class="card-ref">'
                            f'<span class="tag tag-ref">RÉFÉRENCE</span>'
                            f'<b>{sheet}</b> — {meta.get("label", sheet)} · {rows} valeurs'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                st.markdown("---")
                col_b, col_v, _ = st.columns([2, 3, 5])
                with col_b:
                    if st.button("← Retour", use_container_width=True):
                        st.session_state.step = 1
                        st.rerun()
                with col_v:
                    if st.button(
                        "🔍 Lancer la validation →",
                        type="primary",
                        use_container_width=True,
                        disabled=not data_tables
                    ):
                        with st.spinner("Validation structurelle..."):
                            validation = validate_file_structure(parse_result)
                            st.session_state.validation = validation
                        st.session_state.step = 3
                        st.rerun()
        else:
            if st.button("← Retour"):
                st.session_state.step = 1
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # ÉTAPE 3
    # ══════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 3:

        cfg          = st.session_state.config
        validation   = st.session_state.validation
        parse_result = st.session_state.parse_result

        st.markdown(
            '<div class="step-header">'
            'Étape 3 — Résultats de la vérification structurelle'
            '</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · "
            f"Client : **{cfg['client_name']}** · "
            f"**{cfg['nb_rules']} règle(s) métier** chargée(s)"
        )

        summary_val = validation.get("summary", {})
        if validation["is_valid"]:
            st.success(f"**{summary_val.get('status', '✅ Fichier conforme')}**")
        else:
            st.error(f"**{summary_val.get('status', '❌ Fichier non conforme')}**")

        if validation["blocking_errors"]:
            st.markdown("### ❌ Erreurs bloquantes")
            for err in validation["blocking_errors"]:
                st.error(err)

        if validation["warnings"]:
            st.markdown("### ⚠️ Avertissements")
            for w in validation["warnings"]:
                st.warning(w)

        data_tables_val = validation.get("data_tables", [])
        if data_tables_val:
            st.markdown(f"### 📊 Tables de données ({len(data_tables_val)})")
            for t in data_tables_val:
                st.markdown(
                    f'<div class="card-data">'
                    f'<span class="tag tag-data">DONNÉES</span>'
                    f'<b>{t["sheet"]}</b> — {t["label"]} · '
                    f'<b>{t["rows"]} lignes · {t["cols"]} champs</b>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # Règles métier chargées
        active_rules = cfg.get("active_rules", [])
        if active_rules:
            with st.expander(
                f"⚙️ Règles métier chargées ({len(active_rules)}) "
                "— seront appliquées à l'analyse qualité"
            ):
                for r in active_rules:
                    sev  = r.get("severity", "Mineure")
                    auto = "⚡ Auto" if r.get("auto_correct") else ""
                    st.markdown(
                        f'<div class="card-rule">'
                        f'<b>{r.get("label", "")}</b> '
                        f'— {r.get("rule_type", "")} '
                        f'· <span style="color:#854F0B">{sev}</span> {auto}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

        # Prévisualisation
        if data_tables_val and parse_result:
            st.markdown("---")
            st.markdown("### 👀 Prévisualisation des données")
            for t in data_tables_val:
                df = parse_result["sheets"].get(t["sheet"])
                if df is not None and not df.empty:
                    with st.expander(
                        f"📄 **{t['sheet']}** — {t['label']} · {t['rows']} lignes",
                        expanded=True
                    ):
                        st.dataframe(df.head(10), use_container_width=True, hide_index=True)
                        if t["rows"] > 10:
                            st.caption(f"10 premières lignes sur {t['rows']}.")

        # Résumé tables de référence
        ref_tables_val = validation.get("ref_tables", [])
        if ref_tables_val:
            with st.expander(
                f"📋 Tables de référence ({len(ref_tables_val)}) "
                "— pour la validation croisée (Sprint 5)"
            ):
                for t in ref_tables_val:
                    st.markdown(
                        f'<div class="card-ref">'
                        f'<span class="tag tag-ref">RÉFÉRENCE</span>'
                        f'<b>{t["sheet"]}</b> — {t["label"]} · {t["rows"]} valeurs'
                        f'</div>',
                        unsafe_allow_html=True
                    )

        st.markdown("---")
        col1, col2, col3, _ = st.columns([2, 2, 3, 3])
        with col1:
            if st.button("← Recommencer", use_container_width=True):
                st.session_state.step = 1
                st.session_state.config = {}
                st.session_state.parse_result = None
                st.session_state.validation = None
                st.rerun()
        with col2:
            if st.button("↩ Changer fichier", use_container_width=True):
                st.session_state.step = 2
                st.session_state.parse_result = None
                st.session_state.validation = None
                st.rerun()
        with col3:
            if validation["is_valid"]:
                st.success("✅ Prêt pour l'analyse — Sprint 4")
            else:
                st.error("❌ Corrigez les erreurs")

with tab2:
    st.info("🚧 **Sprint 9** — Historique et reprise des sessions.")
