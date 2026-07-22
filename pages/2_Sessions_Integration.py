import base64
import streamlit as st
import pandas as pd
from datetime import datetime
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a
from app.core.validator_axe_b import validate_file_axe_b
from app.core.validator_axe_c import validate_file_axe_c, get_gemini_api_key, is_gemini_available
from app.core.auth import require_role
from app.core.execution_planner import get_execution_plan, build_plan_from_bc
from app.core.integration_levels import (
    load_level_config, traverse_dependencies, build_roadmap,
    is_level_unlocked, refresh_roadmap, all_validated,
)
from app.db.supabase_client import get_supabase_client
from app.core.simulation_context import SimulationContext
from app.core.metadata_loader import MetadataLoader
from app.core.correction_generator import apply_corrections
from app.core.correction_classifier import build_prerequisites_report, build_prerequisites_excel
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import get_access_token, get_companies, get_packages_qc
from app.db.sessions_db import (
    save_session, update_session, delete_session,
    get_all_sessions, SESSION_STATUSES, STATUS_COLORS, STATUS_ICONS
)

require_role()

st.markdown("""
<style>
.step-header {
    background: #EEF4FD; border-left: 4px solid #2E6FBF;
    padding: .5rem 1rem; border-radius: 4px;
    font-weight: 600; color: #1B3A6B; margin-bottom: 1rem;
}
.card-major {
    background: #FAECE7; border-left: 4px solid #993C1D;
    padding: .6rem 1rem; border-radius: 6px;
    margin: .35rem 0; font-size: .88rem; line-height: 1.5;
}
.card-minor {
    background: #FAEEDA; border-left: 4px solid #854F0B;
    padding: .6rem 1rem; border-radius: 6px;
    margin: .35rem 0; font-size: .88rem; line-height: 1.5;
}
.card-info {
    background: #EFF6FF; border-left: 4px solid #3B82F6;
    padding: .6rem 1rem; border-radius: 6px;
    margin: .25rem 0; font-size: .85rem; line-height: 1.5;
}
.card-prereq {
    background: #F3E8FF; border-left: 4px solid #7C3AED;
    padding: .6rem 1rem; border-radius: 6px;
    margin: .35rem 0; font-size: .88rem; line-height: 1.5;
}
.card-data {
    background: #EEF4FD; border-left: 4px solid #2E6FBF;
    padding: .5rem 1rem; border-radius: 6px; margin: .3rem 0;
}
.card-ref {
    background: #F0FBF5; border-left: 4px solid #0F6E56;
    padding: .5rem 1rem; border-radius: 6px; margin: .3rem 0;
}
.card-session {
    background: white; border: 1px solid #E2E8F0;
    border-radius: 8px; padding: 1rem 1.2rem; margin: .4rem 0;
}
.session-name { font-size: 1rem; font-weight: 600; color: #1B3A6B; margin: 0 0 .2rem 0; }
.session-meta { font-size: .8rem; color: #64748B; margin: .1rem 0; }
.stat-box {
    text-align: center; padding: 1rem .5rem;
    background: white; border: 1px solid #E2E8F0; border-radius: 8px;
}
.stat-num { font-size: 2rem; font-weight: 700; margin: 0; }
.stat-lbl { font-size: .75rem; color: #64748B; margin: .2rem 0 0; }
.save-box {
    background: #E1F5EE; border: 1px solid #0F6E56; border-radius: 6px;
    padding: .5rem 1rem; font-size: .85rem; color: #0F6E56;
}
.tag {
    display: inline-block; padding: .15rem .5rem;
    border-radius: 4px; font-size: .72rem; font-weight: 600;
    margin-right: .25rem; vertical-align: middle;
}
.tag-bc    { background: #FAECE7; color: #993C1D; }
.tag-plus  { background: #FFF8E1; color: #854F0B; }
.tag-data  { background: #EEF4FD; color: #1B3A6B; }
.tag-ref   { background: #F0FBF5; color: #0F6E56; }
.tag-info  { background: #EFF6FF; color: #1D4ED8; }
.tag-major { background: #FAECE7; color: #993C1D; }
.tag-minor { background: #FAEEDA; color: #854F0B; }
.tag-ai    { background: #F3E8FF; color: #7C3AED; }
.tag-auto  { background: #E1F5EE; color: #0F6E56; }
.tag-prereq{ background: #F3E8FF; color: #7C3AED; }
.conf-bar  { background: #E2E8F0; border-radius: 3px; height: 5px; margin: 4px 0; }
</style>
""", unsafe_allow_html=True)


# ── Guard ─────────────────────────────────────────────────────────────────────
active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")
active_pkg_code    = st.session_state.get("active_package_code", "")
active_pkg_name    = st.session_state.get("active_package_name", "")

if not active_client:
    st.warning("⚠️ Sélectionnez un client depuis le menu latéral.")
    st.stop()


@st.cache_data(ttl=600, show_spinner=False)
def _load_companies_ses(client_code: str) -> tuple[list, str, str]:
    try:
        p = get_profile_by_code(client_code)
        if not p:
            return [], "", ""
        tid = p.get("bc_tenant_id", "").strip()
        cid = p.get("bc_client_id", "").strip()
        cs  = p.get("bc_client_secret", "").strip()
        env = p.get("bc_environment", "").strip()
        if not all([tid, cid, cs, env]):
            return [], "", ""
        tok       = get_access_token(tid, cid, cs)
        companies = get_companies(tid, env, tok)
        return companies, "", ""
    except Exception as e:
        return [], str(e), ""


@st.cache_data(ttl=300, show_spinner=False)
def _load_pkgs_ses(client_code: str, company_id: str) -> list:
    try:
        p = get_profile_by_code(client_code)
        if not p:
            return []
        tid = p.get("bc_tenant_id", "").strip()
        cid = p.get("bc_client_id", "").strip()
        cs  = p.get("bc_client_secret", "").strip()
        env = p.get("bc_environment", "").strip()
        if not all([tid, cid, cs, env, company_id]):
            return []
        tok = get_access_token(tid, cid, cs)
        return get_packages_qc(tid, env, company_id, tok, visible_only=True)
    except Exception:
        return []


_ses_companies, _ses_err, _ = _load_companies_ses(active_client)

_default_cid   = st.session_state.get("active_company_id", "")
_default_cname = st.session_state.get("active_company_name", "")
if not _default_cid and _ses_companies:
    _p = get_profile_by_code(active_client)
    if _p:
        _default_cid   = _p.get("bc_company_id", "") or ""
        _default_cname = _p.get("bc_company_name", "") or ""


BC_DETECTED = {
    "Longueur maximale dépassée",
    "Valeur Option non autorisée",
    "Type incorrect (entier attendu)",
    "Type incorrect (décimal attendu)",
    "Type incorrect (booléen attendu)",
    "Format de date incorrect",
    # Confirmé empiriquement le 16/07/2026 sur PKG003-Stock : 35/35 anomalies
    # "Code de référence invalide" restantes après nettoyage des faux positifs
    # GUID nul matchent exactement les erreurs BC réelles. Avant ce fix, cette
    # catégorie — la plus fréquente dans les erreurs BC réelles — était
    # étiquetée à tort "détecté uniquement par notre outil".
    "Code de référence invalide",
    "Champ obligatoire vide",
    # Confirmé le 16/07/2026 sur dump BC complet (5/5 items)
    "Souches de n° non résolvable",
    "Champ obligatoire (non-zéro) vide",
}


def bc_badge(error_type: str) -> str:
    if error_type in BC_DETECTED:
        return '<span class="tag tag-bc" title="Détecté aussi par BC Config Package">🔴 BC</span>'
    return '<span class="tag tag-plus" title="Détecté uniquement par notre outil">⭐ Plus</span>'


def merge_results(axe_a: dict, axe_b: dict, axe_c: dict, parse_result: dict = None) -> dict:
    merged = {"by_sheet": {}, "all_anomalies": [], "ai_by_sheet": {}}

    all_sheets = []
    if parse_result:
        all_sheets = (
            parse_result.get("data_tables", []) +
            parse_result.get("ref_tables", [])
        )
    for result in [axe_a, axe_b]:
        for sn in result.get("by_sheet", {}).keys():
            if sn not in all_sheets:
                all_sheets.append(sn)

    ai_map = {}
    if axe_c.get("available") and axe_c.get("by_sheet"):
        for sn, anomalies in axe_c["by_sheet"].items():
            for a in anomalies:
                if a.get("suggestion_ia"):
                    key = (sn, a.get("Ligne", 0), a.get("Champ", ""))
                    ai_map[key] = {
                        "suggestion":  a["suggestion_ia"],
                        "confiance":   a.get("confiance_ia", 0),
                        "explication": a.get("explication_ia", ""),
                        "auto":        a.get("auto_corrige", False),
                    }

    for sn in all_sheets:
        sheet_anomalies = []
        for result in [axe_a, axe_b]:
            for a in result.get("by_sheet", {}).get(sn, []):
                clean = {k: v for k, v in a.items() if k != "Axe"}
                # Classification par défaut pour les anomalies Axe A (champ
                # obligatoire vide, longueur, type...) : toujours corrigibles
                # directement dans le fichier. Les anomalies Axe B de type
                # référence ont déjà leur propre classification explicite
                # (VALEUR_CORRIGIBLE ou PREALABLE_BC_REQUIS) — setdefault ne
                # l'écrase pas.
                clean.setdefault("Classification", "VALEUR_CORRIGIBLE")
                key   = (sn, a.get("Ligne", 0), a.get("Champ", ""))
                if key in ai_map:
                    ia = ai_map[key]
                    clean["suggestion_ia"]  = ia["suggestion"]
                    clean["confiance_ia"]   = ia["confiance"]
                    clean["explication_ia"] = ia["explication"]
                    clean["auto_corrige"]   = ia["auto"]
                    if ia["auto"]:
                        clean["Correction suggérée"] = f"⚡ {ia['suggestion']}"
                    elif not clean.get("Correction suggérée"):
                        clean["Correction suggérée"] = f"🤖 {ia['suggestion']} ({ia['confiance']}%)"
                sheet_anomalies.append(clean)
        merged["by_sheet"][sn]      = sheet_anomalies
        merged["all_anomalies"].extend(sheet_anomalies)

    return merged


def display_unified_results(merged: dict, axe_c: dict, pr: dict = None):
    all_anomalies = merged.get("all_anomalies", [])
    real          = [a for a in all_anomalies if a.get("Ligne", 0) > 0]
    info          = [a for a in all_anomalies if a.get("Ligne", 0) == 0]

    if not real and not info:
        st.success("🎉 **Aucune anomalie détectée !** Les données sont conformes.")
        return

    has_ia = axe_c.get("available") and axe_c.get("total_suggestions", 0) > 0
    auto_c = axe_c.get("auto_corrected", 0)
    if has_ia and auto_c > 0:
        st.info(f"🤖 **{auto_c} correction(s) appliquée(s) automatiquement** par l'IA")

    by_sheet    = merged.get("by_sheet", {})
    sheet_names = list(by_sheet.keys())
    tab_labels  = []
    for sn in sheet_names:
        a    = by_sheet[sn]
        nb   = len([x for x in a if x.get("Ligne", 0) > 0])
        nmaj = sum(1 for x in a if x.get("Sévérité") == "Majeure")
        icon = "🔴" if nmaj > 0 else ("🟠" if nb > 0 else "✅")
        tab_labels.append(f"{icon} {sn} ({nb})")

    if not tab_labels:
        return

    for tab, sn in zip(st.tabs(tab_labels), sheet_names):
        with tab:
            anomalies      = by_sheet.get(sn, [])
            real_anomalies = [a for a in anomalies if a.get("Ligne", 0) > 0]
            info_anomalies = [a for a in anomalies if a.get("Ligne", 0) == 0]

            # Données source SCOPÉES à cet onglet uniquement — affichées
            # avant le early-return "aucune anomalie" pour rester visibles
            # même sur un onglet propre.
            if pr:
                df_sn = pr.get("sheets", {}).get(sn)
                if df_sn is not None and not df_sn.empty:
                    with st.expander(f"👀 Données source — {sn}"):
                        meta_sn = pr.get("metadata", {}).get(sn, {})
                        st.markdown(f"**{sn}** — {meta_sn.get('label', '')} · {len(df_sn)} lignes")
                        st.dataframe(df_sn.head(10), use_container_width=True, hide_index=True)

            if not real_anomalies and not info_anomalies:
                st.success("✅ Aucune anomalie.")
                continue

            if real_anomalies:
                nb_maj = sum(1 for a in real_anomalies if a.get("Sévérité") == "Majeure")
                nb_min = sum(1 for a in real_anomalies if a.get("Sévérité") == "Mineure")
                nb_ia  = sum(1 for a in real_anomalies if a.get("suggestion_ia"))
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Anomalies",     len(real_anomalies))
                t2.metric("🔴 Majeures",   nb_maj)
                t3.metric("🟠 Mineures",   nb_min)
                t4.metric("🤖 IA suggère", nb_ia)

                cf1, cf2 = st.columns(2)
                with cf1:
                    sevs     = sorted(set(a.get("Sévérité", "") for a in real_anomalies))
                    filt_sev = st.multiselect("Sévérité", sevs, default=sevs, key=f"fs_{sn}")
                with cf2:
                    types     = sorted(set(a.get("Type d'anomalie", "") for a in real_anomalies))
                    filt_type = st.multiselect("Type d'anomalie", types, default=types, key=f"ft_{sn}")

                filtered = [
                    a for a in real_anomalies
                    if a.get("Sévérité", "") in filt_sev
                    and a.get("Type d'anomalie", "") in filt_type
                ]

                if filtered:
                    cols_to_show = ["Ligne", "Champ", "Valeur", "Type d'anomalie", "Sévérité", "Classification", "Message", "Correction suggérée"]
                    df_show      = pd.DataFrame([{c: a.get(c, "") for c in cols_to_show} for a in filtered])

                    def color_row(row):
                        s = row.get("Sévérité", "")
                        if s == "Majeure": return ["background-color:#FAECE7"] * len(row)
                        if s == "Mineure": return ["background-color:#FAEEDA"] * len(row)
                        return [""] * len(row)

                    st.dataframe(
                        df_show.style.apply(color_row, axis=1),
                        use_container_width=True, hide_index=True,
                        height=min(400, 50 + len(filtered) * 35)
                    )

                    with st.expander(f"📋 Détail — {len(filtered)} anomalie(s)"):
                        for a in filtered[:50]:
                            css   = "card-major" if a.get("Sévérité") == "Majeure" else "card-minor"
                            fix   = f" → <b>{a['Correction suggérée']}</b>" if a.get("Correction suggérée") else ""
                            err_t = a.get("Type d'anomalie", "")
                            prereq_tag = (
                                '<span class="tag tag-prereq" title="Nécessite la création d\'une donnée en BC avant import">🟣 Prérequis BC</span>'
                                if a.get("Classification") == "PREALABLE_BC_REQUIS" else ""
                            )
                            ia_block = ""
                            if a.get("suggestion_ia"):
                                conf     = a.get("confiance_ia", 0)
                                bar_col  = "#0F6E56" if conf >= 90 else ("#854F0B" if conf >= 70 else "#993C1D")
                                auto_tag = '<span class="tag tag-auto">⚡ Auto</span>' if a.get("auto_corrige") else ""
                                ia_block = (
                                    f'<div style="margin-top:6px;padding-top:6px;border-top:1px solid #E2E8F0">'
                                    f'<span class="tag tag-ai">🤖 IA</span>{auto_tag}'
                                    f' Suggestion : <b>"{a["suggestion_ia"]}"</b>'
                                    f'<div class="conf-bar"><div style="width:{conf}%;background:{bar_col};height:5px;border-radius:3px"></div></div>'
                                    f'<span style="font-size:10px;color:{bar_col}">Confiance : {conf}%</span>'
                                    f'{"<br><i>" + a.get("explication_ia", "") + "</i>" if a.get("explication_ia") else ""}'
                                    f'</div>'
                                )
                            st.markdown(
                                f'<div class="{css}">'
                                f'<b>Ligne {a.get("Ligne", "")}</b> · <b>{a.get("Champ", "")}</b> · '
                                f'<span class="tag tag-{"major" if a.get("Sévérité") == "Majeure" else "minor"}">{a.get("Sévérité", "")}</span>'
                                f'<span class="tag" style="background:#E2E8F0;color:#1B3A6B">{err_t}</span>'
                                f'{bc_badge(err_t)}{prereq_tag}'
                                f'<br>{a.get("Message", "")}{fix}'
                                f'{ia_block}</div>',
                                unsafe_allow_html=True
                            )
                        if len(filtered) > 50:
                            st.caption(f"50 premières sur {len(filtered)}.")

            if info_anomalies:
                st.markdown("---")
                st.markdown("**ℹ️ Champs non vérifiables (référence absente) :**")
                for a in info_anomalies:
                    st.markdown(
                        f'<div class="card-info"><span class="tag tag-info">INFO</span>'
                        f'<b>{a.get("Champ", "")}</b> — {a.get("Message", "")}</div>',
                        unsafe_allow_html=True
                    )


def display_correction_workflow(merged: dict, cfg: dict):
    """
    Étape de correction : sépare les anomalies corrigibles dans le fichier
    (VALEUR_CORRIGIBLE) des prérequis à créer côté BC (PREALABLE_BC_REQUIS),
    laisse le consultant valider/éditer les corrections, génère un fichier
    corrigé (mapping XML préservé) et un rapport de prérequis distinct.

    ⚠️ Le fichier généré n'a pas été validé par un import BC réel — à tester
    avant de le présenter comme "100% intégrable" en démo.
    """
    all_anomalies = merged.get("all_anomalies", [])
    real          = [a for a in all_anomalies if a.get("Ligne", 0) > 0]

    # Tout ce qui est classé VALEUR_CORRIGIBLE va dans le tableau éditable,
    # QU'IL Y AIT ou non une suggestion automatique déjà calculée. La plupart
    # des anomalies Axe A ("Champ obligatoire vide", "Type incorrect...")
    # n'ont pas de suggestion précalculée -- c'est précisément là que le
    # consultant doit pouvoir saisir la bonne valeur lui-même. Filtrer sur
    # "Correction suggérée" non vide (version précédente) excluait la quasi-
    # totalité des anomalies réelles du tableau, d'où : aucune ligne à
    # cocher, aucun fichier généré.
    corrigibles = [a for a in real if a.get("Classification") == "VALEUR_CORRIGIBLE"]
    prereqs = build_prerequisites_report(
        real, profile_code=cfg.get("client_code", ""), company_id=cfg.get("company_id", "")
    )

    st.markdown("---")
    st.markdown('<div class="step-header">🔧 Correction & génération du fichier</div>', unsafe_allow_html=True)

    if prereqs:
        st.markdown(
            f'<div class="card-prereq">🟣 <b>{len(prereqs)} donnée(s) manquante(s) côté BC</b> — '
            f'ces codes n\'existent dans aucune table référencée. Ils doivent être créés dans BC '
            f'AVANT import ; aucune valeur saisie dans le fichier ne les rendra valides.</div>',
            unsafe_allow_html=True
        )
        with st.expander(f"🟣 Prérequis BC à créer ({len(prereqs)})", expanded=True):
            st.dataframe(pd.DataFrame(prereqs), use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Télécharger la checklist prérequis BC (Excel)",
                data=build_prerequisites_excel(prereqs),
                file_name=f"prerequis_bc_{cfg.get('session_name', 'session')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_prereq_xlsx",
            )

    if not corrigibles:
        st.info("Aucune correction directement applicable au fichier pour le moment.")
        st.session_state["prerequisites_report"] = prereqs
        return

    st.markdown(
        f"**✏️ {len(corrigibles)} anomalie(s) corrigible(s) dans le fichier — "
        f"éditez « Nouvelle valeur » et cochez « Appliquer » pour chaque ligne à intégrer :**"
    )
    edit_rows = [
        {
            # Coché par défaut UNIQUEMENT si on a déjà une suggestion fiable
            # (ex: code de référence proche trouvé). Sinon décoché : le
            # consultant doit taper une valeur avant de pouvoir l'appliquer,
            # jamais une case vide poussée par défaut dans le fichier généré.
            "Appliquer":       bool(str(a.get("Correction suggérée", "")).strip()),
            "Onglet":          a.get("Onglet", ""),
            "Ligne":           a.get("Ligne", 0),
            "Champ":           a.get("Champ", ""),
            "Valeur actuelle": a.get("Valeur", ""),
            "Nouvelle valeur": a.get("Correction suggérée", ""),
        }
        for a in corrigibles
    ]
    edited = st.data_editor(
        pd.DataFrame(edit_rows),
        use_container_width=True,
        hide_index=True,
        disabled=["Onglet", "Ligne", "Champ", "Valeur actuelle"],
        column_config={
            "Appliquer": st.column_config.CheckboxColumn(
                help="Cocher pour inclure cette ligne dans le fichier généré"
            ),
            "Nouvelle valeur": st.column_config.TextColumn(
                help="Modifiable — tapez la valeur correcte pour cette cellule"
            ),
        },
        key="corrections_editor",
    )

    cgen1, cgen2 = st.columns([2, 6])
    with cgen1:
        gen_clicked = st.button("🔧 Générer le fichier corrigé", type="primary", use_container_width=True)

    if gen_clicked:
        original_bytes = st.session_state.get("original_file_bytes")
        if not original_bytes:
            st.error("❌ Fichier original introuvable en mémoire — remontez à l'étape 2.")
        else:
            selected = edited[
                (edited["Appliquer"] == True)
                & (edited["Nouvelle valeur"].astype(str).str.strip() != "")
            ]
            if selected.empty:
                st.warning(
                    "Aucune ligne cochée avec une valeur non vide — rien à générer. "
                    "Coche « Appliquer » et vérifie que « Nouvelle valeur » n'est pas vide."
                )
            else:
                corrections = [
                    {
                        "sheet":       row["Onglet"],
                        "excel_row":   int(row["Ligne"]),
                        "column_name": row["Champ"],
                        "new_value":   row["Nouvelle valeur"],
                    }
                    for _, row in selected.iterrows()
                ]
                try:
                    generated_bytes = apply_corrections(original_bytes, corrections)
                    st.session_state["generated_file_bytes"] = generated_bytes
                    st.session_state["generated_file_name"]  = (
                        f"CORRIGE_{cfg.get('file_name', 'fichier.xlsx')}"
                    )
                    st.session_state["prerequisites_report"] = prereqs
                    st.success(f"✅ Fichier généré avec {len(corrections)} correction(s) appliquée(s).")
                except Exception as e:
                    st.error(f"❌ Erreur lors de la génération : {e}")

    if st.session_state.get("generated_file_bytes"):
        st.download_button(
            "⬇️ Télécharger le fichier corrigé",
            data=st.session_state["generated_file_bytes"],
            file_name=st.session_state.get("generated_file_name", "fichier_corrige.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_generated_file",
        )


def reset_session():
    for k in ["step", "config", "parse_result", "validation",
              "merged_result", "axe_c_result", "saved_session_id",
              "original_file_bytes", "generated_file_bytes",
              "generated_file_name", "prerequisites_report",
              # Auto-remplissage du nom de session (package + date/heure) :
              # sans ce nettoyage, une nouvelle session créée juste après un
              # "Recommencer" sur le même package/date garderait la
              # signature et l'horodatage gelés de la session précédente.
              "ses_name_input", "_ses_name_sig", "_ses_name_ts"]:
        st.session_state[k] = (1 if k == "step" else {} if k == "config" else None)
    # Niveaux prérequis (Besoin 2) : la roadmap et les résolutions manuelles
    # de package_code sont propres à un (package, société) donné — à purger
    # explicitement, elles ne sont pas dans la liste fixe ci-dessus car leur
    # nom de clé varie (level_roadmap_<pkg>_<company>).
    for k in list(st.session_state.keys()):
        if k.startswith("level_roadmap_"):
            del st.session_state[k]
    st.session_state["level_pkg_resolve"] = {}


# ════════════════════════════════════════════════════════════════════════════
# PAGE
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"# 📁 Sessions Intégration — {active_client_name}")
st.markdown("---")

tab_main, tab_ses = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

with tab_main:
    for key, default in [
        ("step", 1), ("config", {}), ("parse_result", None), ("validation", None),
        ("merged_result", None), ("axe_c_result", None), ("saved_session_id", None),
        ("original_file_bytes", None), ("generated_file_bytes", None),
        ("generated_file_name", None), ("prerequisites_report", None),
        ("level_pkg_resolve", {}),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    steps = ["Informations", "Upload", "Structure", "Résultats"]
    cols  = st.columns(len(steps))
    for i, (c, n) in enumerate(zip(cols, steps), 1):
        with c:
            if i < st.session_state.step:
                st.markdown(f"✅ **{n}**")
            elif i == st.session_state.step:
                st.markdown(f"🔵 **{n}** ←")
            else:
                st.markdown(f"⬜ {n}")
    st.markdown("---")

    # ── Étape 1 ──────────────────────────────────────────────────────────────
    if st.session_state.step == 1:
        st.markdown('<div class="step-header">Étape 1 — Informations</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)

        # Date de contrôle calculée AVANT le nom de session : le nom en
        # dépend (package + date/heure). Toujours dans col2 visuellement,
        # mais la valeur doit exister avant d'être utilisée dans col1.
        with col2:
            date_controle = st.date_input("📅 Date de contrôle", value=datetime.now().date(), format="DD/MM/YYYY")

        with col1:
            st.markdown(
                f'<div style="background:#EEF4FD;border:1px solid #BFDBFE;border-radius:6px;'
                f'padding:.5rem .75rem;font-size:.88rem;color:#1B3A6B;">'
                f'👤 <b>{active_client_name}</b> ({active_client})'
                f'{"<br>📦 <b>" + active_pkg_name + "</b>" if active_pkg_name else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )

            if _ses_err:
                st.warning(f"Impossible de charger les sociétés BC : {_ses_err}")
                sel_company_id, sel_company_name = _default_cid, _default_cname
            elif _ses_companies:
                _company_opts = {
                    c.get("displayName") or c.get("name", c["id"]): c["id"]
                    for c in _ses_companies
                }
                _names   = list(_company_opts.keys())
                _def_idx = 0
                if _default_cname and _default_cname in _names:
                    _def_idx = _names.index(_default_cname)
                elif _default_cid:
                    for _i, _cid in enumerate(_company_opts.values()):
                        if _cid == _default_cid:
                            _def_idx = _i
                            break
                sel_company_name = st.selectbox(
                    "🏢 Société BC *", _names, index=_def_idx, key="ses_company_sel"
                )
                sel_company_id = _company_opts[sel_company_name]
            else:
                st.info("Aucune société BC disponible.")
                sel_company_id, sel_company_name = _default_cid, _default_cname

            sel_pkg_code = active_pkg_code
            sel_pkg_name = active_pkg_name

            if not active_pkg_code:
                st.markdown("**📦 Package BC**")
                _pkgs_available = _load_pkgs_ses(active_client, sel_company_id)
                if _pkgs_available:
                    _pkg_opts = {
                        f"{p.get('code', '')} — {p.get('packageName', '')}": (
                            p.get("code", ""), p.get("packageName", "")
                        )
                        for p in _pkgs_available
                    }
                    _pkg_choice  = st.selectbox(
                        "Sélectionnez un package *",
                        list(_pkg_opts.keys()),
                        key="ses_pkg_sel",
                    )
                    sel_pkg_code, sel_pkg_name = _pkg_opts[_pkg_choice]
                else:
                    st.warning("Aucun package visible. Configurez la visibilité depuis Packages.")
                    sel_pkg_code, sel_pkg_name = "", ""
                st.markdown("---")

            # Nom de session auto-rempli = package + date/heure de contrôle,
            # au lieu d'une saisie manuelle. L'horodatage est GELÉ dans
            # session_state dès que le package ou la date change (signature
            # trackée via _ses_name_sig) et non recalculé à chaque rerun —
            # sinon datetime.now() changerait à chaque interaction (taper
            # dans les notes, cocher une case...) et écraserait le champ en
            # boucle, y compris après une édition manuelle. Granularité
            # heure:minute:seconde pour éviter les doublons de nom si deux
            # sessions sont créées le même jour sur le même package.
            _name_sig    = f"{sel_pkg_code}|{date_controle.isoformat()}"
            _sig_changed = st.session_state.get("_ses_name_sig") != _name_sig
            if _sig_changed:
                st.session_state["_ses_name_sig"] = _name_sig
                st.session_state["_ses_name_ts"]  = datetime.now()
            _ts = st.session_state.get("_ses_name_ts", datetime.now())
            if _sig_changed or "ses_name_input" not in st.session_state:
                st.session_state["ses_name_input"] = (
                    f"{sel_pkg_name} — {_ts.strftime('%d/%m/%Y %H:%M:%S')}" if sel_pkg_name else ""
                )
            session_name = st.text_input(
                "Nom de la session *",
                key="ses_name_input",
                placeholder="MDD Vente — Juin 2026",
            )

        with col2:
            notes     = st.text_area("Notes", height=68, key=f"step1_notes_{active_client}")
            gemini_ok = is_gemini_available()
            st.markdown("🤖 **Suggestions IA :** " + ("✅ Activées" if gemini_ok else "⚠️ Non configurées"))

        st.markdown("---")
        _, col_btn = st.columns([8, 2])
        with col_btn:
            if st.button("Suivant →", type="primary", use_container_width=True):
                if not session_name.strip():
                    st.error("Nom de session obligatoire.")
                elif not sel_pkg_code:
                    st.error("Sélectionnez un package.")
                else:
                    st.session_state.config = {
                        "session_name": session_name.strip(),
                        "client_code":  active_client,
                        "client_name":  active_client_name,
                        "pkg_code":     sel_pkg_code,
                        "pkg_name":     sel_pkg_name,
                        "notes":        notes,
                        "date_controle":date_controle.isoformat(),
                        "file_name":    "",
                        "company_id":   sel_company_id,
                        "company_name": sel_company_name,
                    }
                    st.session_state.step = 2
                    st.rerun()

    # ── Étape 2 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 2:
        cfg = st.session_state.config
        st.markdown('<div class="step-header">Étape 2 — Upload du fichier client</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}**")
        st.info("Format : export **Package de Configuration BC** (.xlsx)")
        uploaded = st.file_uploader("Glissez-déposez ou cliquez", type=["xlsx", "xls"], key="upl_s")
        if uploaded:
            st.session_state.config["file_name"] = uploaded.name
            # Conservé en mémoire (pas encore en base) pour la génération du
            # fichier corrigé à l'étape 4 — édition XML directe sur les
            # octets d'origine, cf. correction_generator.py.
            st.session_state["original_file_bytes"] = uploaded.getvalue()
            with st.spinner("🔍 Lecture..."):
                pr = parse_uploaded_file(uploaded)
                st.session_state.parse_result = pr
            if not pr["success"]:
                for e in pr["errors"]:
                    st.error(f"❌ {e}")
            else:
                s = get_file_summary(pr)
                st.success(f"✅ **{uploaded.name}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Tables de données",   s.get("nb_data_tables", 0))
                c2.metric("Tables de référence", s.get("nb_ref_tables", 0))
                c3.metric("Lignes",              s.get("total_data_rows", 0))
                for t in s.get("data_tables", []):
                    st.markdown(
                        f'<div class="card-data"><span class="tag tag-data">DONNÉES</span>'
                        f'<b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes</b></div>',
                        unsafe_allow_html=True
                    )
                ref_t = pr.get("ref_tables", [])
                meta  = pr.get("metadata", {})
                tr    = pr.get("total_rows", {})
                with st.expander(f"📋 Tables de référence ({len(ref_t)})"):
                    for sheet in ref_t:
                        m = meta.get(sheet, {})
                        st.markdown(
                            f'<div class="card-ref"><span class="tag tag-ref">RÉFÉRENCE</span>'
                            f'<b>{sheet}</b> — {m.get("label", sheet)} · {tr.get(sheet, 0)} valeurs</div>',
                            unsafe_allow_html=True
                        )
                st.markdown("---")
                cb, cv = st.columns([2, 3])
                with cb:
                    if st.button("← Étape précédente", use_container_width=True):
                        st.session_state.step = 1
                        st.rerun()
                with cv:
                    # Ne bloque que si le fichier n'a strictement aucun onglet
                    # reconnu (ni donnée ni référence) — pas si le fichier ne
                    # contient que des tables absentes de DATA_TABLES (liste
                    # figée, non exhaustive : ex. tables 13, 288 classées
                    # "référence" par défaut alors qu'un client peut vouloir
                    # les faire passer par l'analyse comme des données).
                    has_any_table = bool(pr.get("data_tables")) or bool(pr.get("ref_tables"))
                    if st.button(
                        "🔍 Vérifier la structure →", type="primary",
                        use_container_width=True, disabled=not has_any_table
                    ):
                        with st.spinner("..."):
                            val = validate_file_structure(pr)
                            st.session_state.validation = val
                        st.session_state.step = 3
                        st.rerun()
        else:
            cb, _ = st.columns([2, 8])
            with cb:
                if st.button("← Étape précédente", use_container_width=True):
                    st.session_state.step = 1
                    st.rerun()

    # ── Étape 3 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 3:
        cfg = st.session_state.config
        val = st.session_state.validation
        pr  = st.session_state.parse_result
        st.markdown('<div class="step-header">Étape 3 — Vérification structurelle</div>', unsafe_allow_html=True)
        sv = val.get("summary", {})
        if val["is_valid"]:
            st.success(f"**{sv.get('status', '✅ Conforme')}**")
        else:
            st.error(f"**{sv.get('status', '❌ Non conforme')}**")
        for e in val.get("blocking_errors", []):
            st.error(e)
        for w in val.get("warnings", []):
            st.warning(w)
        for t in val.get("data_tables", []):
            st.markdown(
                f'<div class="card-data"><span class="tag tag-data">DONNÉES</span>'
                f'<b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes · {t["cols"]} champs</b></div>',
                unsafe_allow_html=True
            )

        # ── Niveaux prérequis (Besoin 2) — gate avant l'analyse ──────────────
        # Phase 1 (détection) + Phase 2 (validation BC), avant d'autoriser la
        # Phase 3 (analyse Axe A/Axe B ci-dessous, inchangée). Ne s'exécute
        # que si la structure est valide — pas la peine de vérifier les
        # niveaux sur un fichier qu'on va de toute façon renvoyer à l'étape 2.
        _levels_ok = True
        if val["is_valid"]:
            if "level_config" not in st.session_state:
                try:
                    st.session_state.level_config = load_level_config(get_supabase_client())
                except Exception as e:
                    st.session_state.level_config = {}
                    st.warning(f"⚠️ Impossible de charger level_config : {e}")

            _level_cfg = st.session_state.level_config
            _roadmap_key = f"level_roadmap_{cfg.get('pkg_code', '')}_{cfg.get('company_id', '')}"

            if _level_cfg:
                _cached = st.session_state.get(_roadmap_key)
                # Garde-fou : un objet en cache qui n'est pas une liste de
                # RoadmapEntry (ex. resté d'une version antérieure du code
                # où build_roadmap() retournait un tuple) ne doit jamais
                # planter silencieusement plus loin (refresh_roadmap,
                # is_level_unlocked...). On le détecte et on force une
                # reconstruction propre plutôt que de laisser l'AttributeError
                # remonter à l'utilisateur.
                _cache_valid = isinstance(_cached, list) and (
                    len(_cached) == 0
                    or (
                        hasattr(_cached[0], "level_info")
                        and hasattr(_cached[0], "chain_resolved")
                        and hasattr(_cached[0], "status")
                        and hasattr(getattr(_cached[0], "level_info", None), "level")
                    )
                )
                if _cached is not None and not _cache_valid:
                    st.warning("⚠️ Cache de niveaux dans un format obsolète détecté — reconstruction automatique.")
                    del st.session_state[_roadmap_key]

                if _roadmap_key not in st.session_state:
                    try:
                        _profile = get_profile_by_code(cfg["client_code"])
                        _tid = _profile.get("bc_tenant_id", "").strip()
                        _env = _profile.get("bc_environment", "").strip()
                        _cs  = _profile.get("bc_client_secret", "").strip()
                        _cid = _profile.get("bc_client_id", "").strip()
                        _token = get_access_token(_tid, _cid, _cs)
                        _root_plan = get_execution_plan(
                            profile_code=cfg["client_code"],
                            company_id=cfg["company_id"],
                            package_code=cfg["pkg_code"],
                        )
                        _pkg_resolve = st.session_state.get("level_pkg_resolve", {})
                        _discovered = traverse_dependencies(
                            _root_plan, build_plan_from_bc,
                            _tid, _env, cfg["company_id"], _token,
                            lambda tid: _pkg_resolve.get(tid),
                        )
                        st.session_state[_roadmap_key] = build_roadmap(_discovered, _level_cfg)
                    except Exception as e:
                        st.session_state[_roadmap_key] = []
                        st.warning(f"⚠️ Détection des niveaux impossible pour l'instant : {e}")

                _roadmap = st.session_state[_roadmap_key]

                if _roadmap:
                    st.markdown("---")
                    st.markdown('<div class="step-header">🧱 Prérequis BC détectés</div>', unsafe_allow_html=True)

                    if st.button("🔄 Revérifier les niveaux", key="btn_refresh_levels"):
                        with st.spinner("Vérification BC en cours..."):
                            st.session_state[_roadmap_key] = refresh_roadmap(
                                cfg["client_code"], cfg["company_id"], _roadmap
                            )
                        st.rerun()

                    _current = "__unset__"
                    try:
                        for _entry in _roadmap:
                            if _entry.level_info.level != _current:
                                _current = _entry.level_info.level
                                _header = "Non classé" if _current is None else f"Niveau {_current}"
                                st.markdown(f"**{_header}**")

                            _unlocked = is_level_unlocked(_entry.level_info.level, _roadmap)
                            _label = _entry.level_info.table_name
                            if _entry.level_info.sub_level:
                                _label = f"[{_entry.level_info.sub_level}] {_label}"

                            _icon = "✅" if _entry.status == "validated" else ("🔒" if not _unlocked else "☐")
                            st.markdown(f"{_icon} {_label}")

                            if not _entry.chain_resolved:
                                with st.expander(f"⚠️ package_code inconnu pour {_label} — saisir pour approfondir la détection"):
                                    _pc = st.text_input(
                                        "package_code BC pour cette table",
                                        key=f"pkgresolve_{_entry.level_info.table_id}",
                                    )
                                    if _pc and st.button("Relancer la détection", key=f"redetect_{_entry.level_info.table_id}"):
                                        st.session_state.setdefault("level_pkg_resolve", {})[_entry.level_info.table_id] = _pc
                                        del st.session_state[_roadmap_key]
                                        st.rerun()
                    except Exception as _diag_e:
                        # DIAGNOSTIC TEMPORAIRE — à retirer une fois la vraie cause connue.
                        # Affiche le traceback complet non censuré (contrairement au message
                        # redacted de Streamlit Cloud) pour identifier précisément quel
                        # objet/attribut pose problème.
                        import traceback
                        st.error("🔧 DIAGNOSTIC — erreur capturée dans la boucle d'affichage de la roadmap :")
                        st.code(traceback.format_exc())
                        st.write("Type de `_roadmap` :", type(_roadmap))
                        if _roadmap:
                            st.write("Type du 1er élément :", type(_roadmap[0]))
                            st.write("Contenu du 1er élément :", repr(_roadmap[0]))

                    _levels_ok = all_validated(_roadmap)
                    if not _levels_ok:
                        st.info("🔒 L'analyse qualité reste verrouillée tant que tous les niveaux ne sont pas validés dans BC.")
                # _roadmap vide => aucune dépendance de niveau détectée => _levels_ok reste True (analyse directe)
            # level_config vide/non chargée : ne bloque pas l'analyse — à corriger si level_config
            # doit être rendue obligatoire (dépend de si tu veux imposer le seed avant tout usage).

        st.markdown("---")
        cb, cv = st.columns([2, 5])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step         = 2
                st.session_state.parse_result = None
                st.session_state.validation   = None
                st.rerun()
        with cv:
            if val["is_valid"]:
                if st.button(
                    "🚀 Lancer l'analyse qualité →", type="primary", use_container_width=True,
                    disabled=not _levels_ok,
                ):
                    api_key     = get_gemini_api_key()
                    client_code = cfg.get("client_code", "")

                    with st.spinner("⏳ Analyse des contraintes..."):
                        _exec_plan = get_execution_plan(
                            profile_code = client_code,
                            company_id   = cfg.get("company_id", ""),
                            package_code = cfg.get("pkg_code", ""),
                        )
                        _meta_loader = MetadataLoader(client_code, cfg.get("company_id", ""))
                        _sim_ctx     = SimulationContext()
                        axe_a        = validate_file_axe_a(pr, execution_plan=_exec_plan)

                    with st.spinner("⏳ Vérification des références..."):
                        axe_b = validate_file_axe_b(
                            pr,
                            profile_code    = client_code,
                            company_id      = cfg.get("company_id", ""),
                            sim_context     = _sim_ctx,
                            metadata_loader = _meta_loader,
                            execution_plan  = _exec_plan,
                        )

                    axe_c = {"available": False, "total_suggestions": 0, "auto_corrected": 0, "by_sheet": {}}
                    if api_key:
                        with st.spinner("🤖 Suggestions IA en cours..."):
                            axe_c = validate_file_axe_c(axe_a, axe_b, pr, api_key=api_key)

                    merged = merge_results(axe_a, axe_b, axe_c, parse_result=pr)
                    st.session_state.merged_result = merged
                    st.session_state.axe_c_result  = axe_c

                    all_r = merged.get("all_anomalies", [])
                    real  = [a for a in all_r if a.get("Ligne", 0) > 0]
                    st.session_state.config["total"] = len(real)
                    st.session_state.config["major"] = sum(1 for a in real if a.get("Sévérité") == "Majeure")
                    st.session_state.config["minor"] = sum(1 for a in real if a.get("Sévérité") == "Mineure")
                    st.session_state.config["lines"] = axe_a.get("lines_analyzed", 0)

                    st.session_state.saved_session_id     = None
                    st.session_state.generated_file_bytes = None
                    st.session_state.generated_file_name  = None
                    st.session_state.prerequisites_report = None
                    st.session_state.step = 4
                    st.rerun()
            else:
                st.error("❌ Corrigez les erreurs structurelles.")

    # ── Étape 4 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 4:
        cfg    = st.session_state.config
        merged = st.session_state.merged_result
        axe_c  = st.session_state.axe_c_result or {"available": False}
        pr     = st.session_state.parse_result

        st.markdown('<div class="step-header">Étape 4 — Résultats de l\'analyse qualité</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}** · **{cfg.get('file_name', '')}**")

        total = cfg.get("total", 0)
        major = cfg.get("major", 0)
        minor = cfg.get("minor", 0)
        lines = cfg.get("lines", 0)
        auto  = axe_c.get("auto_corrected", 0)

        c1, c2, c3, c4, c5 = st.columns(5)
        for cw, v, l, col in [
            (c1, lines, "Lignes analysées",  "#1B3A6B"),
            (c2, total, "Total anomalies",    "#993C1D" if total > 0 else "#0F6E56"),
            (c3, major, "🔴 Majeures",        "#993C1D" if major > 0 else "#0F6E56"),
            (c4, minor, "🟠 Mineures",        "#854F0B" if minor > 0 else "#0F6E56"),
            (c5, auto,  "🤖 Corrigées auto",  "#7C3AED" if auto > 0 else "#64748B"),
        ]:
            with cw:
                st.markdown(
                    f'<div class="stat-box"><p class="stat-num" style="color:{col}">{v}</p>'
                    f'<p class="stat-lbl">{l}</p></div>',
                    unsafe_allow_html=True
                )

        st.markdown("---")
        col_leg1, col_leg2, _ = st.columns([2, 2, 6])
        with col_leg1:
            st.markdown('<span class="tag tag-bc">🔴 BC</span> Détecté aussi par BC Config Package', unsafe_allow_html=True)
        with col_leg2:
            st.markdown('<span class="tag tag-plus">⭐ Plus</span> Valeur ajoutée de notre outil', unsafe_allow_html=True)
        st.markdown("---")

        display_unified_results(merged, axe_c, pr)
        display_correction_workflow(merged, cfg)

        st.markdown("---")
        cb, cr, cs, cst = st.columns([2, 2, 3, 3])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step = 3
                for k in ["merged_result", "axe_c_result", "saved_session_id"]:
                    st.session_state[k] = None
                st.rerun()
        with cr:
            if st.button("🔄 Recommencer", use_container_width=True):
                reset_session()
                st.rerun()
        with cs:
            if st.session_state.saved_session_id:
                st.markdown(
                    f'<div class="save-box">✅ <b>Session sauvegardée</b><br>'
                    f'<span style="font-size:11px;color:#64748B">{st.session_state.saved_session_id}</span></div>',
                    unsafe_allow_html=True
                )
            else:
                if st.button("💾 Sauvegarder la session", type="primary", use_container_width=True):
                    original_bytes  = st.session_state.get("original_file_bytes")
                    generated_bytes = st.session_state.get("generated_file_bytes")
                    ok, res = save_session({
                        "session_name":    cfg["session_name"],
                        "profile_code":    cfg["client_code"],
                        "file_name":       cfg.get("file_name", ""),
                        "notes":           cfg.get("notes", ""),
                        "date_controle":   cfg.get("date_controle", ""),
                        "company_id":      cfg.get("company_id", ""),
                        "company_name":    cfg.get("company_name", ""),
                        "status":          "Analyse terminée" if major > 0 else "Terminée",
                        "total_anomalies": total,
                        "major_anomalies": major,
                        "minor_anomalies": minor,
                        "original_file_b64": (
                            base64.b64encode(original_bytes).decode("ascii")
                            if original_bytes else ""
                        ),
                        "generated_file_b64": (
                            base64.b64encode(generated_bytes).decode("ascii")
                            if generated_bytes else ""
                        ),
                        "generated_file_name": st.session_state.get("generated_file_name", ""),
                        "prerequisites_report": st.session_state.get("prerequisites_report") or [],
                    })
                    if ok:
                        st.session_state.saved_session_id = res
                        st.success("✅ Sauvegardée !")
                        st.rerun()
                    else:
                        st.error(f"❌ {res}")
        with cst:
            if major == 0:
                st.success("✅ Aucune anomalie majeure")
            else:
                st.warning(f"⚠️ {major} anomalie(s) majeure(s)")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — MES SESSIONS
# ════════════════════════════════════════════════════════════════════════════
with tab_ses:
    st.markdown("### 📋 Mes sessions de contrôle")
    for key, default in [("edit_session_id", None), ("confirm_delete_ses", None)]:
        if key not in st.session_state:
            st.session_state[key] = default

    sessions = get_all_sessions(profile_code=active_client)
    st.markdown("---")

    if not sessions:
        st.info("Aucune session. Créez-en une et cliquez sur **💾 Sauvegarder**.")
    else:
        st.markdown(f"**{len(sessions)} session(s)**")
        for s in sessions:
            sid    = s.get("id", "")
            status = s.get("status", "Nouvelle")
            sc     = STATUS_COLORS.get(status, "#64748B")
            si     = STATUS_ICONS.get(status, "")
            tot_a  = s.get("total_anomalies", 0)
            maj_a  = s.get("major_anomalies", 0)
            min_a  = s.get("minor_anomalies", 0)
            crd    = s.get("created_at", "")[:16].replace("T", " ") if s.get("created_at") else ""
            upd    = s.get("updated_at", "")[:16].replace("T", " ") if s.get("updated_at") else ""
            fn     = s.get("file_name", "")
            gen_fn = s.get("generated_file_name", "")
            prereq_list = s.get("prerequisites_report") or []
            an_s   = (
                f'<span style="color:#993C1D">🔴 {maj_a} majeures</span> · '
                f'<span style="color:#854F0B">🟠 {min_a} mineures</span>'
                if tot_a > 0 else
                '<span style="color:#0F6E56">✅ Aucune anomalie</span>'
            )

            ci, ca = st.columns([7, 3])
            with ci:
                st.markdown(
                    f'<div class="card-session">'
                    f'<p class="session-name">{s.get("name", "")}</p>'
                    f'<p class="session-meta">Client : <b>{s.get("profile_code", "")}</b> · '
                    f'<span style="color:{sc};font-weight:500">{si} {status}</span></p>'
                    f'<p class="session-meta">{an_s}</p>'
                    f'<p class="session-meta">{"📄 " + fn + " · " if fn else ""}🕐 {crd}'
                    f'{"  ·  ✏️ " + upd if upd != crd else ""}</p>'
                    f'{"<p class=" + chr(34) + "session-meta" + chr(34) + ">📦 Fichier généré : " + gen_fn + "</p>" if gen_fn else ""}'
                    f'{"<p class=" + chr(34) + "session-meta" + chr(34) + ">🟣 " + str(len(prereq_list)) + " prérequis BC</p>" if prereq_list else ""}'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # Téléchargements : fichier chargé, fichier généré, rapport prérequis.
                orig_b64 = s.get("original_file_b64", "")
                gen_b64  = s.get("generated_file_b64", "")
                dcol1, dcol2, dcol3 = st.columns(3)
                with dcol1:
                    if orig_b64:
                        st.download_button(
                            "⬇️ Fichier chargé", data=base64.b64decode(orig_b64),
                            file_name=fn or "fichier_charge.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_orig_{sid}", use_container_width=True,
                        )
                with dcol2:
                    if gen_b64:
                        st.download_button(
                            "⬇️ Fichier corrigé", data=base64.b64decode(gen_b64),
                            file_name=gen_fn or "fichier_corrige.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_gen_{sid}", use_container_width=True,
                        )
                with dcol3:
                    if prereq_list:
                        st.download_button(
                            "⬇️ Prérequis BC", data=build_prerequisites_excel(prereq_list),
                            file_name=f"prerequis_bc_{sid}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_prereq_{sid}", use_container_width=True,
                        )
            with ca:
                st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
                ce, cd = st.columns(2)
                with ce:
                    if st.button("✏️ Éditer", key=f"es_{sid}", use_container_width=True):
                        st.session_state.edit_session_id    = sid
                        st.session_state.confirm_delete_ses = None
                with cd:
                    if st.button("🗑️", key=f"ds_{sid}", use_container_width=True):
                        st.session_state.confirm_delete_ses = sid
                        st.session_state.edit_session_id    = None
                st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.edit_session_id == sid:
                st.markdown("---")
                st.markdown(f"**✏️ Modifier — {s.get('name', '')}**")
                e1, e2 = st.columns(2)
                with e1:
                    nn = st.text_input("Nom", value=s.get("name", ""), key=f"en_{sid}")
                    ns = st.selectbox(
                        "Statut", SESSION_STATUSES,
                        index=SESSION_STATUSES.index(status) if status in SESSION_STATUSES else 0,
                        key=f"est_{sid}"
                    )
                with e2:
                    no = st.text_area("Notes", value=s.get("notes", ""), height=100, key=f"eno_{sid}")
                sv1, sv2, _ = st.columns([2, 2, 6])
                with sv1:
                    if st.button("💾 Enregistrer", key=f"esv_{sid}", type="primary", use_container_width=True):
                        ok, err = update_session(sid, {"name": nn.strip(), "status": ns, "notes": no.strip()})
                        if ok:
                            st.success("✅ Mis à jour !")
                            st.session_state.edit_session_id = None
                            st.rerun()
                        else:
                            st.error(f"❌ {err}")
                with sv2:
                    if st.button("Annuler", key=f"eca_{sid}", use_container_width=True):
                        st.session_state.edit_session_id = None
                        st.rerun()
                st.markdown("---")

            if st.session_state.confirm_delete_ses == sid:
                st.warning(f"⚠️ Supprimer **{s.get('name', '')}** ? Action irréversible.")
                dy, dn, _ = st.columns([2, 2, 6])
                with dy:
                    if st.button("✅ Confirmer", key=f"dcy_{sid}", type="primary"):
                        ok, err = delete_session(sid)
                        if ok:
                            st.success("Supprimée.")
                            st.session_state.confirm_delete_ses = None
                            st.rerun()
                        else:
                            st.error(err)
                with dn:
                    if st.button("❌ Annuler", key=f"dcn_{sid}"):
                        st.session_state.confirm_delete_ses = None
                        st.rerun()