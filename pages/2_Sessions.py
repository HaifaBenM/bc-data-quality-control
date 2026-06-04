"""
Page Sessions — Sprint 1 : Upload fichier + vérification structurelle.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.master_data_config import (
    get_master_data_list,
    get_master_data_config,
    get_related_tables
)

# ── Configuration de la page ─────────────────────────────────────────────────
st.set_page_config(
    page_title="Sessions — BC Quality Control",
    page_icon="📁",
    layout="wide"
)

# ── Style CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .step-header {
        background: linear-gradient(135deg, #1B3A6B, #2E6FBF);
        color: white;
        padding: 0.75rem 1.25rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        font-weight: 600;
    }
    .result-box {
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin: 0.5rem 0;
    }
    .result-ok    { background: #E1F5EE; border-left: 4px solid #0F6E56; }
    .result-error { background: #FAECE7; border-left: 4px solid #993C1D; }
    .result-warn  { background: #FAEEDA; border-left: 4px solid #854F0B; }
    .sheet-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 📁 Sessions de contrôle")
st.markdown("Créer une nouvelle session ou reprendre une session existante.")
st.markdown("---")

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — NOUVELLE SESSION
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # Initialiser la session state pour garder les données entre les étapes
    if "session_step" not in st.session_state:
        st.session_state.session_step = 1
    if "session_config" not in st.session_state:
        st.session_state.session_config = {}
    if "parse_result" not in st.session_state:
        st.session_state.parse_result = None
    if "validation_result" not in st.session_state:
        st.session_state.validation_result = None

    # ── Indicateur de progression ────────────────────────────────────────────
    steps = ["Configuration", "Upload fichier", "Résultats"]
    col_steps = st.columns(len(steps))
    for i, (col, step_name) in enumerate(zip(col_steps, steps), 1):
        with col:
            if i < st.session_state.session_step:
                st.markdown(f"✅ **{step_name}**")
            elif i == st.session_state.session_step:
                st.markdown(f"🔵 **{step_name}** ←")
            else:
                st.markdown(f"⬜ {step_name}")

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 1 — Configuration de la session
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.session_step == 1:

        st.markdown(
            '<div class="step-header">Étape 1 — Configuration de la session</div>',
            unsafe_allow_html=True
        )

        col1, col2 = st.columns(2)

        with col1:
            session_name = st.text_input(
                "Nom de la session *",
                placeholder="Ex: ABC Distribution - Clients - Juin 2026",
                help="Donnez un nom clair pour retrouver cette session facilement."
            )

            # Client — placeholder (sera remplacé en Sprint 2)
            client = st.text_input(
                "Client *",
                placeholder="Ex: ABC Distribution SARL",
                help="En Sprint 2, ce sera une liste déroulante des profils clients."
            )

            master_data = st.selectbox(
                "Master Data *",
                ["— Sélectionner —"] + get_master_data_list(),
                help="Choisissez la table BC principale concernée par ce fichier."
            )

        with col2:
            # Tables liées — dépend de la Master Data sélectionnée
            if master_data and master_data != "— Sélectionner —":
                config = get_master_data_config(master_data)
                related = get_related_tables(master_data)

                # Afficher les infos de la Master Data
                st.info(
                    f"**{config.get('icon', '')} {master_data}** — "
                    f"{config.get('description', '')}\n\n"
                    f"Table BC : `{config.get('bc_table', '')}` (Table {config.get('bc_table_id', '')})"
                )

                if related:
                    selected_related = st.multiselect(
                        "Tables liées à inclure",
                        related,
                        help="Sélectionnez les mêmes tables liées que dans le template envoyé au client."
                    )
                else:
                    st.info("Cette Master Data n'a pas de tables liées standard.")
                    selected_related = []
            else:
                st.empty()
                selected_related = []

            notes = st.text_area(
                "Notes (optionnel)",
                placeholder="Contexte du projet, informations importantes...",
                height=80
            )

        # Bouton de validation
        st.markdown("---")
        col_btn1, col_btn2, col_empty = st.columns([2, 2, 6])

        with col_btn1:
            if st.button("Suivant →", type="primary", use_container_width=True):
                # Validation des champs obligatoires
                errors = []
                if not session_name.strip():
                    errors.append("Le nom de la session est obligatoire.")
                if not client.strip():
                    errors.append("Le client est obligatoire.")
                if not master_data or master_data == "— Sélectionner —":
                    errors.append("La Master Data est obligatoire.")

                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    # Construire la liste complète des onglets attendus
                    # = la table principale + les tables liées sélectionnées
                    config = get_master_data_config(master_data)
                    main_table = config.get("bc_table", master_data)
                    expected_sheets = [main_table] + selected_related

                    # Sauvegarder la configuration
                    st.session_state.session_config = {
                        "session_name": session_name.strip(),
                        "client": client.strip(),
                        "master_data": master_data,
                        "related_tables": selected_related,
                        "expected_sheets": expected_sheets,
                        "notes": notes
                    }
                    st.session_state.session_step = 2
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 2 — Upload du fichier
    # ══════════════════════════════════════════════════════════════════════════
    elif st.session_state.session_step == 2:

        config = st.session_state.session_config

        st.markdown(
            '<div class="step-header">Étape 2 — Upload du fichier client</div>',
            unsafe_allow_html=True
        )

        # Rappel de la configuration
        with st.expander("📋 Rappel de la configuration", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric("Session", config["session_name"])
            col2.metric("Client", config["client"])
            col3.metric("Master Data", config["master_data"])

            st.markdown("**Onglets attendus dans le fichier :**")
            for sheet in config["expected_sheets"]:
                st.markdown(f"- `{sheet}`")

        st.markdown("---")

        # Zone d'upload
        st.markdown("### 📎 Charger le fichier Excel reçu du client")
        uploaded_file = st.file_uploader(
            "Glissez-déposez le fichier ou cliquez pour parcourir",
            type=["xlsx", "xls"],
            help="Fichier Excel généré depuis les Packages de Configuration BC, rempli par le client.",
            key="file_uploader_sprint1"
        )

        if uploaded_file is not None:

            # Parser le fichier
            with st.spinner("📖 Lecture du fichier en cours..."):
                parse_result = parse_uploaded_file(uploaded_file)
                st.session_state.parse_result = parse_result

            if not parse_result["success"]:
                for err in parse_result["errors"]:
                    st.error(f"❌ {err}")
            else:
                # Résumé du fichier
                summary = get_file_summary(parse_result)
                st.success(f"✅ Fichier lu avec succès : **{uploaded_file.name}**")

                col1, col2, col3 = st.columns(3)
                col1.metric("Onglets détectés", summary["nb_onglets"])
                col2.metric("Lignes de données", summary["total_lignes"])
                col3.metric("Colonnes total", summary["total_colonnes"])

                # Liste des onglets détectés
                st.markdown("**Onglets détectés dans le fichier :**")
                expected = config["expected_sheets"]
                for sheet in parse_result["sheet_names"]:
                    if sheet in expected:
                        st.markdown(f"✅ `{sheet}` — {parse_result['total_rows'].get(sheet, 0)} lignes")
                    else:
                        st.markdown(f"⚠️ `{sheet}` — non attendu")

                # Boutons navigation
                st.markdown("---")
                col_btn1, col_btn2, col_empty = st.columns([2, 2, 6])

                with col_btn1:
                    if st.button("← Retour", use_container_width=True):
                        st.session_state.session_step = 1
                        st.rerun()

                with col_btn2:
                    if st.button("Lancer la validation →", type="primary", use_container_width=True):
                        # Lancer la validation structurelle
                        with st.spinner("🔍 Validation structurelle en cours..."):
                            validation = validate_file_structure(
                                parse_result=parse_result,
                                expected_sheets=config["expected_sheets"],
                                master_data_name=config["master_data"]
                            )
                            st.session_state.validation_result = validation
                        st.session_state.session_step = 3
                        st.rerun()
        else:
            # Bouton retour si pas de fichier
            if st.button("← Retour"):
                st.session_state.session_step = 1
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # ÉTAPE 3 — Résultats de la validation structurelle
    # ══════════════════════════════════════════════════════════════════════════
    elif st.session_state.session_step == 3:

        config = st.session_state.session_config
        validation = st.session_state.validation_result
        parse_result = st.session_state.parse_result

        st.markdown(
            '<div class="step-header">Étape 3 — Résultats de la vérification structurelle</div>',
            unsafe_allow_html=True
        )

        # ── Statut global ────────────────────────────────────────────────────
        summary = validation.get("summary", {})

        if validation["is_valid"]:
            st.markdown(
                '<div class="result-box result-ok">'
                f'<b>✅ {summary.get("status", "Structure conforme")}</b><br>'
                f'{summary.get("conforming", 0)} onglet(s) conforme(s) sur '
                f'{summary.get("total_expected", 0)} attendu(s).'
                '</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="result-box result-error">'
                f'<b>❌ {summary.get("status", "Structure non conforme")}</b><br>'
                f'{len(validation["blocking_errors"])} erreur(s) bloquante(s) détectée(s). '
                'Le fichier doit être corrigé avant de continuer.'
                '</div>',
                unsafe_allow_html=True
            )

        st.markdown("---")

        # ── Erreurs bloquantes ───────────────────────────────────────────────
        if validation["blocking_errors"]:
            st.markdown("### ❌ Erreurs bloquantes")
            st.markdown("Ces erreurs doivent être corrigées — demandez au client un nouveau fichier.")
            for err in validation["blocking_errors"]:
                st.error(err)

        # ── Avertissements ───────────────────────────────────────────────────
        if validation["warnings"]:
            st.markdown("### ⚠️ Avertissements")
            st.markdown("Ces points méritent attention mais ne bloquent pas l'analyse.")
            for warn in validation["warnings"]:
                st.warning(warn)

        # ── Onglets conformes ────────────────────────────────────────────────
        if validation["conforming_sheets"]:
            st.markdown(f"### ✅ Onglets conformes ({len(validation['conforming_sheets'])})")
            for sheet in validation["conforming_sheets"]:
                nb_rows = parse_result["total_rows"].get(sheet, 0)
                nb_cols = len(parse_result["sheets"].get(sheet, pd.DataFrame()).columns)
                st.success(f"**{sheet}** — {nb_rows} lignes · {nb_cols} colonnes")

        st.markdown("---")

        # ── Prévisualisation des données ─────────────────────────────────────
        if parse_result and parse_result.get("success") and validation["conforming_sheets"]:
            st.markdown("### 👀 Prévisualisation des données")
            st.markdown("Aperçu des 10 premières lignes de chaque onglet conforme.")

            for sheet_name in validation["conforming_sheets"]:
                df = parse_result["sheets"].get(sheet_name)
                if df is not None and not df.empty:
                    with st.expander(f"📄 Onglet : **{sheet_name}** ({len(df)} lignes)", expanded=True):
                        st.dataframe(
                            df.head(10),
                            use_container_width=True,
                            hide_index=True
                        )
                        if len(df) > 10:
                            st.caption(f"Affichage des 10 premières lignes sur {len(df)} au total.")

        st.markdown("---")

        # ── Boutons de navigation ────────────────────────────────────────────
        col1, col2, col3, col_empty = st.columns([2, 2, 3, 3])

        with col1:
            if st.button("← Recommencer", use_container_width=True):
                st.session_state.session_step = 1
                st.session_state.session_config = {}
                st.session_state.parse_result = None
                st.session_state.validation_result = None
                st.rerun()

        with col2:
            if st.button("↩ Changer le fichier", use_container_width=True):
                st.session_state.session_step = 2
                st.session_state.parse_result = None
                st.session_state.validation_result = None
                st.rerun()

        with col3:
            if validation["is_valid"]:
                st.success("✅ Prêt pour l'analyse qualité — Sprint 4")
            else:
                st.error("❌ Corrigez les erreurs avant de continuer")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — MES SESSIONS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Sessions existantes")
    st.info("""
    🚧 **Sprint 9** — Cette section affichera la liste de toutes vos sessions
    avec leur statut, les anomalies restantes et la possibilité de reprendre
    une session interrompue.
    """)
