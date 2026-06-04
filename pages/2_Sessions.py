"""
Page Sessions - Sprint 1 v3.
Flux simplifie avec auto-detection complete des tables BC.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure

st.set_page_config(
    page_title="Sessions - BC Quality Control",
    page_icon="📁",
    layout="wide"
)

st.markdown("""
<style>
    .step-header {
        background: linear-gradient(135deg, #1B3A6B, #2E6FBF);
        color: white; padding: 0.75rem 1.25rem;
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
    .card-err {
        background: #FAECE7; border-left: 4px solid #993C1D;
        border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;
    }
    .tag {
        display: inline-block; font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 4px; margin-right: 6px;
    }
    .tag-data { background: #0F6E56; color: white; }
    .tag-ref  { background: #2E6FBF; color: white; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 📁 Sessions de contrôle")
st.markdown("---")

tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 - NOUVELLE SESSION
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # Session state
    if "step" not in st.session_state:
        st.session_state.step = 1
    if "config" not in st.session_state:
        st.session_state.config = {}
    if "parse_result" not in st.session_state:
        st.session_state.parse_result = None
    if "validation" not in st.session_state:
        st.session_state.validation = None

    # Barre de progression
    steps = ["Informations", "Upload & Detection", "Resultats"]
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
    # ETAPE 1 - Informations
    # ══════════════════════════════════════════════════════════════════════
    if st.session_state.step == 1:

        st.markdown(
            '<div class="step-header">Etape 1 — Informations de la session</div>',
            unsafe_allow_html=True
        )
        st.caption(
            "Plus besoin de selectionner la Master Data — "
            "l'outil la detecte automatiquement depuis le fichier."
        )

        col1, col2 = st.columns(2)
        with col1:
            session_name = st.text_input(
                "Nom de la session *",
                placeholder="Ex: ABC Distribution - Migration donnees - Juin 2026"
            )
        with col2:
            client = st.text_input(
                "Client *",
                placeholder="Ex: ABC Distribution SARL",
                help="En Sprint 2 : liste deroulante des profils clients."
            )

        notes = st.text_area("Notes (optionnel)", height=60)

        st.markdown("---")
        col_btn, _ = st.columns([2, 8])
        with col_btn:
            if st.button("Suivant →", type="primary", use_container_width=True):
                errors = []
                if not session_name.strip():
                    errors.append("Nom de session obligatoire.")
                if not client.strip():
                    errors.append("Client obligatoire.")
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    st.session_state.config = {
                        "session_name": session_name.strip(),
                        "client": client.strip(),
                        "notes": notes
                    }
                    st.session_state.step = 2
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # ETAPE 2 - Upload et detection
    # ══════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 2:

        cfg = st.session_state.config
        st.markdown(
            '<div class="step-header">Etape 2 — Upload du fichier & Detection automatique</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · Client : **{cfg['client']}**"
        )

        st.markdown("### 📎 Charger le fichier Excel recu du client")
        st.info(
            "Format attendu : export **Package de Configuration BC** "
            "(.xlsx — en-tetes en ligne 3, donnees a partir de la ligne 4)."
        )

        uploaded = st.file_uploader(
            "Glissez-deposez ou cliquez pour parcourir",
            type=["xlsx", "xls"],
            key="uploader_v3"
        )

        if uploaded:
            with st.spinner("🔍 Lecture et detection automatique des tables..."):
                parse_result = parse_uploaded_file(uploaded)
                st.session_state.parse_result = parse_result

            if not parse_result["success"]:
                for e in parse_result["errors"]:
                    st.error(f"❌ {e}")
            else:
                summary = get_file_summary(parse_result)
                st.success(f"✅ **{uploaded.name}** — lecture reussie")

                # Résumé
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "Tables de donnees",
                    summary.get("nb_data_tables", 0),
                    help="Tables ou le client a saisi ses donnees"
                )
                c2.metric(
                    "Tables de reference",
                    summary.get("nb_ref_tables", 0),
                    help="Listes de valeurs BC (pays, conditions paiement...)"
                )
                c3.metric(
                    "Lignes de donnees",
                    summary.get("total_data_rows", 0)
                )

                st.markdown("---")

                # Tables de donnees detectees
                st.markdown("### 📊 Tables de donnees detectees")
                st.caption("Ce sont les tables que l'outil va analyser et controler.")

                data_tables = summary.get("data_tables", [])
                if data_tables:
                    for t in data_tables:
                        st.markdown(
                            f'<div class="card-data">'
                            f'<span class="tag tag-data">DONNEES</span>'
                            f'<b>{t["sheet"]}</b> — {t["label"]} '
                            f'(Table BC n°{t["table_id"]}) · '
                            f'<b>{t["rows"]} lignes</b>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.warning(
                        "Aucune table de donnees reconnue. "
                        "Verifiez que le fichier est bien un export BC."
                    )

                # Tables de reference
                ref_tables = parse_result.get("ref_tables", [])
                metadata = parse_result.get("metadata", {})
                total_rows = parse_result.get("total_rows", {})

                with st.expander(
                    f"📋 Tables de reference detectees ({len(ref_tables)}) "
                    "— utilisees pour la validation croisee (Sprint 5)"
                ):
                    for sheet in ref_tables:
                        meta = metadata.get(sheet, {})
                        rows = total_rows.get(sheet, 0)
                        st.markdown(
                            f'<div class="card-ref">'
                            f'<span class="tag tag-ref">REFERENCE</span>'
                            f'<b>{sheet}</b> — {meta.get("label", sheet)} · {rows} valeurs'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                # Navigation
                st.markdown("---")
                col_b, col_v, _ = st.columns([2, 3, 5])
                with col_b:
                    if st.button("← Retour", use_container_width=True):
                        st.session_state.step = 1
                        st.rerun()
                with col_v:
                    can_validate = bool(data_tables)
                    if st.button(
                        "🔍 Lancer la validation →",
                        type="primary",
                        use_container_width=True,
                        disabled=not can_validate
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
    # ETAPE 3 - Resultats
    # ══════════════════════════════════════════════════════════════════════
    elif st.session_state.step == 3:

        cfg = st.session_state.config
        validation = st.session_state.validation
        parse_result = st.session_state.parse_result

        st.markdown(
            '<div class="step-header">Etape 3 — Resultats de la verification structurelle</div>',
            unsafe_allow_html=True
        )
        st.caption(
            f"Session : **{cfg['session_name']}** · Client : **{cfg['client']}**"
        )

        summary_val = validation.get("summary", {})

        if validation["is_valid"]:
            st.success(f"**{summary_val.get('status', '✅ Fichier conforme')}**")
        else:
            st.error(f"**{summary_val.get('status', '❌ Fichier non conforme')}**")

        # Erreurs bloquantes
        if validation["blocking_errors"]:
            st.markdown("### ❌ Erreurs bloquantes")
            for err in validation["blocking_errors"]:
                st.error(err)

        # Avertissements
        if validation["warnings"]:
            st.markdown("### ⚠️ Avertissements")
            for w in validation["warnings"]:
                st.warning(w)

        # Tables de donnees validees
        data_tables_val = validation.get("data_tables", [])
        if data_tables_val:
            st.markdown(f"### 📊 Tables de donnees ({len(data_tables_val)})")
            for t in data_tables_val:
                st.markdown(
                    f'<div class="card-data">'
                    f'<span class="tag tag-data">DONNEES</span>'
                    f'<b>{t["sheet"]}</b> — {t["label"]} · '
                    f'<b>{t["rows"]} lignes · {t["cols"]} champs</b>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # Prévisualisation
        if data_tables_val and parse_result:
            st.markdown("---")
            st.markdown("### 👀 Previsualisation des donnees")
            for t in data_tables_val:
                sheet_name = t["sheet"]
                df = parse_result["sheets"].get(sheet_name)
                if df is not None and not df.empty:
                    with st.expander(
                        f"📄 **{sheet_name}** — {t['label']} · {t['rows']} lignes",
                        expanded=True
                    ):
                        st.dataframe(
                            df.head(10),
                            use_container_width=True,
                            hide_index=True
                        )
                        if t["rows"] > 10:
                            st.caption(
                                f"10 premieres lignes sur {t['rows']} au total."
                            )

        # Tables de reference
        ref_tables_val = validation.get("ref_tables", [])
        if ref_tables_val:
            with st.expander(
                f"📋 Tables de reference ({len(ref_tables_val)}) "
                "— pour la validation croisee (Sprint 5)"
            ):
                for t in ref_tables_val:
                    st.markdown(
                        f'<div class="card-ref">'
                        f'<span class="tag tag-ref">REFERENCE</span>'
                        f'<b>{t["sheet"]}</b> — {t["label"]} · {t["rows"]} valeurs'
                        f'</div>',
                        unsafe_allow_html=True
                    )

        # Navigation
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
                st.success("✅ Pret pour l'analyse qualite — Sprint 4")
            else:
                st.error("❌ Corrigez les erreurs")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 - MES SESSIONS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.info("🚧 **Sprint 9** — Historique et reprise des sessions.")