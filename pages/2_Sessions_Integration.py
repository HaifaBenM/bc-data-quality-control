import base64
import streamlit as st
import pandas as pd
from datetime import datetime
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a
from app.core.validator_axe_b import validate_file_axe_b
from app.core.validator_axe_c import validate_file_axe_c, get_gemini_api_key, is_gemini_available
from app.core.auth import require_role, is_consultant
from app.core.execution_planner import get_execution_plan, build_plan_from_bc
from app.core.integration_levels import (
    load_level_config, traverse_dependencies, build_roadmap, build_roadmap_from_prereqs,
    is_level_unlocked, refresh_roadmap, all_validated,
    check_table_filled, _has_blocking_sub_anomalies,
)
from app.db.supabase_client import get_supabase_client
from app.core.simulation_context import SimulationContext
from app.core.metadata_loader import MetadataLoader
from app.core.correction_generator import apply_corrections, clear_id_reference_columns
from app.core.correction_classifier import (
    build_prerequisites_report, build_prerequisites_excel,
    check_gl_account_prerequisites, extract_gl_account_posting_fields,
)
from app.db.metadata_db import (
    persist_gl_account_posting_fields, get_gl_account_posting_fields,
    get_table_caption_cached, clear_reference_cache,
)
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import (
    get_access_token, get_companies, get_packages_qc, get_gl_account_fields_live,
    diagnose_standard_api_account,
)
from app.db.sessions_db import (
    save_session, update_session, delete_session,
    get_all_sessions, SESSION_STATUSES, STATUS_COLORS, STATUS_ICONS,
    get_sessions_for_company, build_sessions_tree,
    resolve_parent_candidates, get_descendant_table_ids, can_close_session,
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
.level-check-item {
    display: flex; align-items: center; gap: .65rem;
    padding: .45rem 0; font-size: .92rem;
}
.level-check-circle-done {
    width: 22px; height: 22px; border-radius: 50%; background: #0F6E56;
    color: white; display: flex; align-items: center; justify-content: center;
    font-size: 13px; flex-shrink: 0;
}
.level-check-circle-todo {
    width: 22px; height: 22px; border-radius: 50%;
    border: 2px solid #CBD5E1; flex-shrink: 0;
}
.level-check-label-done   { color: #1B3A6B; font-weight: 500; }
.level-check-label-todo   { color: #334155; }
.level-check-label-locked { color: #94A3B8; }
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
def _load_pkgs_ses(client_code: str, company_id: str, only_visible: bool) -> list:
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
        return get_packages_qc(tid, env, company_id, tok, visible_only=only_visible)
    except Exception:
        return []


def _try_live_gl_account(client_code: str, company_id: str) -> dict:
    """
    Tentative de lecture live BC (get_gl_account_fields_live) — extrait de
    _resolve_gl_account_fallback (28/07/2026) pour pouvoir l'appeler
    indépendamment du repli cache, AVANT même de regarder si le fichier
    déposé a son propre onglet Compte général. Voir check_gl_account_
    prerequisites(prefer_fallback=...) : le live doit primer sur l'onglet
    du fichier, pas seulement s'y substituer quand l'onglet est absent —
    sinon un fichier template repris d'une autre société (avec son propre
    onglet 15, sans rapport avec la société réellement testée) fait
    remonter à tort des anomalies déjà corrigées dans BC.

    Retourne {} si le live échoue ou ne trouve rien — jamais d'exception
    remontée à l'appelant.
    """
    try:
        p = get_profile_by_code(client_code)
        if not p:
            if is_consultant():
                st.caption(f"🔧 [Debug consultant] Vérification live impossible : aucun profil trouvé pour '{client_code}'.")
            return {}
        tid = p.get("bc_tenant_id", "").strip()
        cid = p.get("bc_client_id", "").strip()
        cs  = p.get("bc_client_secret", "").strip()
        env = p.get("bc_environment", "").strip()
        if not all([tid, cid, cs, env, company_id]):
            if is_consultant():
                st.caption("🔧 [Debug consultant] Vérification live impossible : profil BC incomplet (tenant/client/secret/environnement/société).")
            return {}
        tok  = get_access_token(tid, cid, cs)
        live = get_gl_account_fields_live(tid, env, company_id, tok)
        if is_consultant():
            st.caption(f"🔧 [Debug consultant] Vérification live du plan comptable : {len(live)} compte(s) GL trouvé(s).")
        return live or {}
    except Exception as e:
        if is_consultant():
            st.caption(f"🔧 [Debug consultant] Vérification live échouée : {type(e).__name__}: {e}")
        return {}


def _resolve_gl_account_fallback(client_code: str, company_id: str) -> dict:
    """
    Tente d'abord une vérification LIVE via BC (_try_live_gl_account) — plus
    fiable qu'un cache car jamais périmée (voir discussion du 24/07/2026 :
    un repli persisté reste correct tant que personne ne modifie le plan
    comptable entre deux analyses, ce qui n'est pas garanti). Retombe sur le
    repli persisté (cache Supabase) si le live échoue pour n'importe quelle
    raison — page AL pas encore publiée, société sans accès BC configuré,
    etc. Ne jamais faire planter l'analyse pour cette seule raison.

    Utilisée quand le fichier déposé n'a PAS d'onglet Compte général
    exploitable. Pour le cas où le fichier EN A un mais qu'on veut quand
    même prioriser le live (fichier template d'une autre société), voir
    _try_live_gl_account() appelé directement, combiné à
    check_gl_account_prerequisites(prefer_fallback=True).
    """
    live = _try_live_gl_account(client_code, company_id)
    if live:
        return live
    return get_gl_account_posting_fields(client_code, company_id)


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


def display_correction_workflow(merged: dict, cfg: dict, pr: dict):
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
    # Le contrôle croisé GL Account (comptes GL référencés par 92/93/94 avec
    # champs vides) a été retiré d'ici le 27/07/2026 : il appartient
    # exclusivement à la roadmap de niveaux (Phase A, Étape 3, avant clic
    # "Analyse qualité") — Phase B ne montre plus que les erreurs
    # corrigibles, clarifié explicitement par Rami. Voir _prereqs plus loin
    # dans ce fichier pour l'endroit où ce contrôle reste actif.

    st.markdown("---")
    st.markdown('<div class="step-header">🔧 Correction & génération du fichier</div>', unsafe_allow_html=True)

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
            # RÉVISÉ (19/08/2026) : le vidage des colonnes Guid
            # (clear_id_reference_columns) est indépendant des corrections
            # de valeur — il ne devrait pas être bloqué par "aucune ligne
            # cochée". Avant ce fix, le bouton refusait purement et
            # simplement de générer un fichier s'il n'y avait rien à
            # corriger, empêchant de tester le nettoyage Guid seul (cas
            # Rami du 19/08 : 251 déjà correct dans BC, rien à corriger,
            # mais besoin de télécharger le fichier nettoyé quand même).
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
                generated_bytes = (
                    apply_corrections(original_bytes, corrections)
                    if corrections else original_bytes
                )
                # RÉVISÉ (18/08/2026, 2e passe) : calcule les colonnes de
                # type Guid par feuille depuis l'execution_plan déjà en
                # cache (early_axeab_*), plutôt que de deviner par le nom
                # "ID X" — extension-agnostique (voir docstring de
                # clear_id_reference_columns). Repli automatique sur
                # l'ancien préfixe si le plan est indisponible.
                _guid_cols_by_sheet: dict[str, set[str]] | None = None
                _early_key = (
                    f"early_axeab_{cfg.get('pkg_code', '')}_"
                    f"{cfg.get('company_id', '')}_{cfg.get('file_name', '')}"
                )
                _cached_plan = st.session_state.get(_early_key, {}).get("exec_plan")
                if _cached_plan is not None:
                    try:
                        from app.core.bc_excel_processor import extract_sheets_info
                        _sheets_info = extract_sheets_info(original_bytes)
                        _guid_cols_by_sheet = {}
                        for _si in _sheets_info:
                            _tid = int(_si["table_id"]) if str(_si["table_id"]).isdigit() else 0
                            if not _tid:
                                continue
                            _defs = _cached_plan.get_field_defs_for_table(_tid)
                            _guid_names = {n for n, fm in _defs.items() if fm.al_type == "Guid"}
                            if _guid_names:
                                _guid_cols_by_sheet[_si["sheet_name"]] = _guid_names
                    except Exception:
                        _guid_cols_by_sheet = None  # repli silencieux sur l'heuristique par nom
                # AJOUTÉ (18/08/2026) : les colonnes Guid (SystemId BC)
                # ne sont jamais portables d'une société à l'autre — BC
                # rejette l'import sur ces colonnes même quand le Code
                # associé est correct. On les vide pour laisser BC
                # résoudre uniquement via Code à l'import.
                generated_bytes = clear_id_reference_columns(generated_bytes, _guid_cols_by_sheet)
                st.session_state["generated_file_bytes"] = generated_bytes
                st.session_state["generated_file_name"]  = (
                    f"CORRIGE_{cfg.get('file_name', 'fichier.xlsx')}"
                )
                st.session_state["prerequisites_report"] = prereqs
                if corrections:
                    st.success(f"✅ Fichier généré avec {len(corrections)} correction(s) appliquée(s).")
                else:
                    st.success(
                        "✅ Fichier généré sans correction de valeur — colonnes Guid (SystemId) "
                        "vidées uniquement."
                    )
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
    # BUG CORRIGÉ (24/07/2026) : "ses_name_input" est la clé du st.text_input
    # du nom de session (Étape 1), instancié PLUS HAUT dans le même run que
    # le bouton "Recommencer" qui appelle cette fonction. Streamlit interdit
    # `st.session_state[key] = valeur` pour une clé de widget déjà
    # instanciée dans le run courant (StreamlitAPIException — vérifié dans
    # session_state.py : la restriction porte sur __setitem__, pas sur
    # __delitem__). On utilise donc `del` partout ici, jamais une
    # assignation directe — un rerun suit immédiatement chaque appel, donc
    # les valeurs par défaut (step=1, config={}...) seront réinitialisées
    # normalement au prochain run par le bloc d'init habituel, pas besoin
    # de les fixer ici.
    for k in ["step", "config", "parse_result", "validation",
              "merged_result", "axe_c_result", "saved_session_id",
              "original_file_bytes", "generated_file_bytes",
              "generated_file_name", "prerequisites_report",
              # Auto-remplissage du nom de session (package + date/heure) :
              # sans ce nettoyage, une nouvelle session créée juste après un
              # "Recommencer" sur le même package/date garderait la
              # signature et l'horodatage gelés de la session précédente.
              "ses_name_input", "_ses_name_sig", "_ses_name_ts"]:
        if k in st.session_state:
            del st.session_state[k]
    # Niveaux prérequis (Besoin 2) : la roadmap et les résolutions manuelles
    # de package_code sont propres à un (package, société) donné — à purger
    # explicitement, elles ne sont pas dans la liste fixe ci-dessus car leur
    # nom de clé varie (level_roadmap_<pkg>_<company>).
    for k in list(st.session_state.keys()):
        if k.startswith("level_roadmap_") or k.startswith("early_axeab_"):
            del st.session_state[k]
    if "level_pkg_resolve" in st.session_state:
        del st.session_state["level_pkg_resolve"]


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
                _pkgs_available = _load_pkgs_ses(active_client, sel_company_id, not is_consultant())
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
        col_rc, _, col_btn = st.columns([2, 6, 2])
        with col_rc:
            if st.button("🔄 Recommencer", use_container_width=True, key="rc_step1"):
                reset_session()
                st.rerun()
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
                st.markdown("---")
                cb, _, crc = st.columns([2, 6, 2])
                with cb:
                    if st.button("← Étape précédente", use_container_width=True, key="back_step2_fail"):
                        st.session_state.step = 1
                        st.rerun()
                with crc:
                    if st.button("🔄 Recommencer", use_container_width=True, key="rc_step2_fail"):
                        reset_session()
                        st.rerun()
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
                cb, cv, crc = st.columns([2, 3, 2])
                with cb:
                    if st.button("← Étape précédente", use_container_width=True):
                        st.session_state.step = 1
                        st.rerun()
                with crc:
                    if st.button("🔄 Recommencer", use_container_width=True, key="rc_step2a"):
                        reset_session()
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
            cb, _, crc = st.columns([2, 6, 2])
            with cb:
                if st.button("← Étape précédente", use_container_width=True):
                    st.session_state.step = 1
                    st.rerun()
            with crc:
                if st.button("🔄 Recommencer", use_container_width=True, key="rc_step2b"):
                    reset_session()
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
        # Détection basée sur les VRAIES anomalies Axe B (build_prerequisites_report),
        # pas sur une traversée théorique des jointures BC : une table n'apparaît que
        # si Axe B a réellement trouvé une valeur manquante la référençant dans CE
        # fichier. Élimine par construction le bruit des tables techniques/système
        # (confirmé le 22/07/2026 : ~40 tables non pertinentes détectées par jointure
        # sur un simple PKG003-Stock). Implique de lancer Axe A/Axe B ici, avant le
        # gate, puis de réutiliser ce résultat au clic sur "Lancer l'analyse"
        # plutôt que de le recalculer.
        _levels_ok = True
        _early_axeb_key = f"early_axeab_{cfg.get('pkg_code', '')}_{cfg.get('company_id', '')}_{cfg.get('file_name', '')}"
        if val["is_valid"]:
            if "level_config" not in st.session_state:
                try:
                    st.session_state.level_config = load_level_config(get_supabase_client())
                except Exception as e:
                    st.session_state.level_config = {}
                    st.warning(f"⚠️ Impossible de charger level_config : {e}")

            # AJOUTÉ (07/08/2026) : level_config n'était rechargée qu'une fois
            # par session navigateur — une modif SQL faite dans Supabase
            # (nouvelle classification de table) restait invisible tant que
            # l'utilisateur n'actualisait pas complètement la page (F5), y
            # compris après un "Recommencer" qui ne vidait pas cette clé.
            # Bouton explicite plutôt qu'un rechargement systématique à
            # chaque run (coût Supabase superflu quand rien n'a changé).
            if st.button("🔄 Recharger classification niveaux (level_config)", key="btn_reload_level_config"):
                try:
                    st.session_state.level_config = load_level_config(get_supabase_client())
                    for _k in list(st.session_state.keys()):
                        if _k.startswith("level_roadmap_"):
                            del st.session_state[_k]
                    st.success("Classification rechargée depuis Supabase.")
                except Exception as e:
                    st.error(f"Échec du rechargement : {e}")
                st.rerun()

            # AJOUTÉ (19/08/2026) : get_reference_values_by_table_id() n'a
            # aucune expiration — une entrée en cache reste utilisée
            # indéfiniment même si BC a changé depuis (ex. 251 Groupe compta.
            # produit signalé "introuvable" par le Trigger Simulator alors
            # que les groupes existent bien dans BC, si le cache date d'avant
            # leur création). Bouton consultant, même logique que celui de
            # level_config ci-dessus — vidage manuel à la demande, pas de
            # rafraîchissement automatique.
            if is_consultant():
                if st.button("🔄 Vider le cache des valeurs de référence (Supabase)", key="btn_clear_ref_cache"):
                    try:
                        ok, err = clear_reference_cache(
                            profile_code = cfg.get("client_code", ""),
                            company_id   = cfg.get("company_id", ""),
                        )
                        if ok:
                            st.success("Cache des tables de référence vidé — sera rechargé depuis BC au prochain contrôle.")
                        else:
                            st.error(f"Échec du vidage : {err}")
                    except Exception as e:
                        st.error(f"Échec du vidage : {e}")
                    st.rerun()

                # AJOUTÉ (19/08/2026) — diagnostic direct : affiche EXACTEMENT
                # ce que get_reference_values_by_table_id() voit pour une
                # table donnée (cache Supabase vidé ou non, résultat live BC
                # inclus), pour trancher sans deviner pourquoi un niveau
                # reste bloqué malgré une correction BC confirmée (ex. 308
                # Souches de n° signalé "empty" après création de la souche
                # ARTICLE et vidage du cache — ce diagnostic dit directement
                # si le souci est le cache, le lookup live, ou autre chose).
                with st.expander("🔬 Diagnostic — voir les valeurs de référence détectées pour une table"):
                    _diag_tid = st.number_input(
                        "Table ID à inspecter", min_value=1, value=308, step=1, key="diag_ref_table_id"
                    )
                    if st.button("Interroger get_reference_values_by_table_id", key="btn_diag_ref_values"):
                        from app.db.metadata_db import get_reference_values_by_table_id
                        try:
                            _codes, _found = get_reference_values_by_table_id(
                                cfg.get("client_code", ""), cfg.get("company_id", ""), int(_diag_tid)
                            )
                            st.write(f"**found** = {_found}")
                            st.write(f"**Nombre de codes trouvés** = {len(_codes)}")
                            st.write(sorted(_codes) if _codes else "(aucun code)")
                        except Exception as e:
                            st.error(f"Erreur pendant l'appel : {e}")

            _level_cfg = st.session_state.level_config
            _roadmap_key = f"level_roadmap_{cfg.get('pkg_code', '')}_{cfg.get('company_id', '')}_{cfg.get('file_name', '')}"

            if _level_cfg:
                _cached = st.session_state.get(_roadmap_key)
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
                        import time as _perf_time
                        _t_start = _perf_time.time()
                        _perf_log = []

                        client_code = cfg.get("client_code", "")
                        _exec_plan = get_execution_plan(
                            profile_code=client_code,
                            company_id=cfg.get("company_id", ""),
                            package_code=cfg.get("pkg_code", ""),
                        )
                        _perf_log.append(("get_execution_plan", _perf_time.time() - _t_start))
                        _t = _perf_time.time()

                        _meta_loader = MetadataLoader(client_code, cfg.get("company_id", ""))
                        _sim_ctx     = SimulationContext()
                        with st.spinner("⏳ Analyse des prérequis BC..."):
                            _axe_a = validate_file_axe_a(pr, execution_plan=_exec_plan)
                            _perf_log.append(("validate_file_axe_a", _perf_time.time() - _t))
                            _t = _perf_time.time()

                            _axe_b = validate_file_axe_b(
                                pr,
                                profile_code    = client_code,
                                company_id      = cfg.get("company_id", ""),
                                sim_context     = _sim_ctx,
                                metadata_loader = _meta_loader,
                                execution_plan  = _exec_plan,
                            )
                            _perf_log.append(("validate_file_axe_b", _perf_time.time() - _t))
                            _t = _perf_time.time()
                        # Mis en cache pour réutilisation au clic "Lancer l'analyse" —
                        # évite de relancer Axe A/Axe B une seconde fois pour rien.
                        st.session_state[_early_axeb_key] = {
                            "axe_a": _axe_a, "axe_b": _axe_b, "exec_plan": _exec_plan,
                        }
                        _early_merged = merge_results(_axe_a, _axe_b, {"available": False}, parse_result=pr)
                        _real = [a for a in _early_merged.get("all_anomalies", []) if a.get("Ligne", 0) > 0]
                        _prereqs = build_prerequisites_report(
                            _real, profile_code=client_code, company_id=cfg.get("company_id", "")
                        )
                        _perf_log.append(("build_prerequisites_report", _perf_time.time() - _t))
                        _t = _perf_time.time()
                        # Contrôle croisé GL Account <-> groupes comptables (92/93/94...).
                        # Voir app.core.correction_classifier.check_gl_account_prerequisites.
                        # Confirmé nécessaire par test réel du 23-24/07/2026 (compte
                        # 77110001 sans Groupe compta. produit, invisible pour Axe B
                        # puisque ce n'est pas un code de référence manquant mais un
                        # champ GL vide).
                        #
                        # CORRIGÉ (28/07/2026) : avant cette version, l'onglet GL
                        # Account du fichier déposé primait TOUJOURS dès qu'il était
                        # présent, le live BC n'étant tenté qu'en son absence. Bug
                        # confirmé en réel : un fichier template repris d'une AUTRE
                        # société (pour être intégré dans la société de test) a son
                        # propre onglet Compte général, sans rapport avec l'état réel
                        # de la société testée — il primait à tort sur le live, ET sa
                        # persistance écrasait le cache Supabase avec ces valeurs
                        # étrangères. Le live BC est désormais tenté EN PREMIER,
                        # systématiquement ; l'onglet du fichier ne sert plus que de
                        # repli si le live échoue (société sans accès BC configuré,
                        # page AL pas encore publiée, etc.).
                        _company_id = cfg.get("company_id", "")
                        _gl_live = _try_live_gl_account(client_code, _company_id)
                        _perf_log.append(("_try_live_gl_account", _perf_time.time() - _t))
                        _t = _perf_time.time()
                        if _gl_live:
                            persist_gl_account_posting_fields(client_code, _company_id, _gl_live)
                            _gl_anomalies = check_gl_account_prerequisites(pr, _gl_live, prefer_fallback=True)
                        else:
                            _gl_extract = extract_gl_account_posting_fields(pr)
                            if _gl_extract:
                                persist_gl_account_posting_fields(client_code, _company_id, _gl_extract)
                                _gl_fallback = None
                            else:
                                _gl_fallback = get_gl_account_posting_fields(client_code, _company_id)
                            _gl_anomalies = check_gl_account_prerequisites(pr, _gl_fallback)
                        _perf_log.append(("check_gl_account_prerequisites", _perf_time.time() - _t))
                        _t = _perf_time.time()
                        _prereqs = _prereqs + _gl_anomalies
                        # build_roadmap_from_prereqs regroupe désormais génériquement
                        # les lignes de _prereqs par table et les attache en
                        # sub_anomalies à CHAQUE niveau concerné (pas seulement GL
                        # Account) — demandé par Rami le 27/07 : plusieurs tables
                        # prérequis doivent chacune afficher leur propre détail.
                        st.session_state[_roadmap_key] = build_roadmap_from_prereqs(_prereqs, _level_cfg)
                        _perf_log.append(("build_roadmap_from_prereqs", _perf_time.time() - _t))
                        _perf_log.append(("TOTAL", _perf_time.time() - _t_start))
                        st.session_state["_perf_log_prereqs"] = _perf_log
                    except Exception as e:
                        st.session_state[_roadmap_key] = []
                        st.warning(f"⚠️ Détection des niveaux impossible pour l'instant : {e}")

                _roadmap = st.session_state[_roadmap_key]

                if is_consultant():
                    with st.expander("🔧 Diagnostic recordValues (consultant)"):
                        st.caption(
                            "Teste directement l'endpoint live recordValues pour ce client/société, "
                            "sans rien configurer en local — utilise les mêmes identifiants que l'outil."
                        )
                        # AJOUTÉ (04/08/2026) : dump brut de /api/v2.0/companies pour
                        # comparer sans ambiguïté le nom affiché ("TEST-GL-VALIDATION")
                        # à l'ID (systemId) réellement utilisé par company_id — sert à
                        # trancher entre "mauvaise société sélectionnée" et "vrai bug
                        # de scoping côté extension AL" quand le nom semble correct
                        # mais que le plan comptable retourné ne correspond pas.
                        if st.button("Lister sociétés BC (brut)", key="btn_debug_companies_raw"):
                            try:
                                _dbg_profile0 = get_profile_by_code(cfg.get("client_code", ""))
                                _dbg_tid0 = _dbg_profile0.get("bc_tenant_id", "").strip()
                                _dbg_cid0 = _dbg_profile0.get("bc_client_id", "").strip()
                                _dbg_cs0  = _dbg_profile0.get("bc_client_secret", "").strip()
                                _dbg_env0 = _dbg_profile0.get("bc_environment", "").strip()
                                _dbg_tok0 = get_access_token(_dbg_tid0, _dbg_cid0, _dbg_cs0)
                                _dbg_companies_raw = get_companies(_dbg_tid0, _dbg_env0, _dbg_tok0)
                                st.write(f"**company_id actuel de cette session : `{cfg.get('company_id', '')}`**")
                                st.json(_dbg_companies_raw)
                            except Exception as _dbg_exc0:
                                st.error(f"Échec : {_dbg_exc0}")
                        # AJOUTÉ (04/08/2026) : isole plateforme BC vs extension
                        # talan/qctools — interroge l'API STANDARD BC (pas notre
                        # extension) sur un compte précis, pour trancher un écart
                        # constaté entre le client web BC (à jour) et l'API.
                        _dbg_acc_test = st.text_input(
                            "N° de compte à tester (API standard)", value="77110001",
                            key="dbg_acc_no_input",
                        )
                        if st.button("Tester API standard (accounts)", key="btn_debug_std_api"):
                            try:
                                _dbg_profile3b = get_profile_by_code(cfg.get("client_code", ""))
                                _dbg_tid3b = _dbg_profile3b.get("bc_tenant_id", "").strip()
                                _dbg_cid3b = _dbg_profile3b.get("bc_client_id", "").strip()
                                _dbg_cs3b  = _dbg_profile3b.get("bc_client_secret", "").strip()
                                _dbg_env3b = _dbg_profile3b.get("bc_environment", "").strip()
                                _dbg_company3b = cfg.get("company_id", "")
                                _dbg_tok3b = get_access_token(_dbg_tid3b, _dbg_cid3b, _dbg_cs3b)
                                _dbg_std_result = diagnose_standard_api_account(
                                    _dbg_tid3b, _dbg_env3b, _dbg_company3b, _dbg_acc_test, _dbg_tok3b
                                )
                                if _dbg_std_result["found"]:
                                    st.success(f"✅ API standard TROUVE le compte {_dbg_acc_test} — le souci est spécifique à l'extension talan/qctools, pas la plateforme.")
                                else:
                                    st.warning(f"⚠️ API standard NE TROUVE PAS le compte {_dbg_acc_test} non plus — probable délai de réplication côté plateforme BC, pas un bug de code.")
                                st.json(_dbg_std_result["raw"])
                            except Exception as _dbg_exc3b:
                                st.error(f"Échec : {_dbg_exc3b}")
                        # AJOUTÉ (07/08/2026) : teste la nouvelle résolution
                        # dynamique de libellé de table (get_table_caption_cached)
                        # sans avoir à relancer toute une analyse Stock complète.
                        _dbg_table_id_test = st.text_input(
                            "ID de table à tester (résolution libellé)", value="99000763",
                            key="dbg_table_caption_input",
                        )
                        if st.button("Tester résolution libellé table", key="btn_debug_table_caption"):
                            try:
                                caption = get_table_caption_cached(
                                    cfg.get("client_code", ""), cfg.get("company_id", ""), _dbg_table_id_test
                                )
                                if caption:
                                    st.success(f"✅ Table {_dbg_table_id_test} résolue : \"{caption}\"")
                                else:
                                    st.warning(f"⚠️ Table {_dbg_table_id_test} non résolue (None) — AL pas encore republié, table inexistante, ou profil BC incomplet.")
                            except Exception as _dbg_exc_cap:
                                st.error(f"Échec : {type(_dbg_exc_cap).__name__}: {_dbg_exc_cap}")
                        if st.button("Tester recordValues (champ No., table 15)", key="btn_debug_recordvalues"):
                            try:
                                _dbg_profile = get_profile_by_code(cfg.get("client_code", ""))
                                _dbg_tid = _dbg_profile.get("bc_tenant_id", "").strip()
                                _dbg_cid = _dbg_profile.get("bc_client_id", "").strip()
                                _dbg_cs  = _dbg_profile.get("bc_client_secret", "").strip()
                                _dbg_env = _dbg_profile.get("bc_environment", "").strip()
                                _dbg_company = cfg.get("company_id", "")
                                _dbg_tok = get_access_token(_dbg_tid, _dbg_cid, _dbg_cs)
                                _dbg_result = get_gl_account_fields_live(_dbg_tid, _dbg_env, _dbg_company, _dbg_tok)
                                st.write(f"**{len(_dbg_result)} compte(s) GL trouvé(s) au total.**")
                                # CORRIGÉ (04/08/2026) : st.json(...[:10]) masquait
                                # silencieusement tout compte au-delà des 10 premiers
                                # triés — a fait perdre plusieurs heures de diagnostic
                                # sur 77110001/76310001 (jamais dans les 10 premiers
                                # d'une liste de 351 comptes). Recherche ciblée par
                                # numéro de compte en plus de l'échantillon.
                                _dbg_lookup = st.text_input(
                                    "Chercher un/des compte(s) précis (séparés par virgule)",
                                    value="77110001, 76310001",
                                    key="dbg_gl_lookup_input",
                                )
                                if _dbg_lookup.strip():
                                    _dbg_targets = [t.strip() for t in _dbg_lookup.split(",") if t.strip()]
                                    _dbg_found = {t: _dbg_result.get(t, "❌ ABSENT du live") for t in _dbg_targets}
                                    st.json(_dbg_found)
                                st.caption("Échantillon (10 premiers comptes, triés) :")
                                st.json(dict(list(_dbg_result.items())[:10]))
                            except Exception as e:
                                st.error(f"{type(e).__name__}: {e}")
                                _dbg_resp = getattr(e, "response", None)
                                if _dbg_resp is not None:
                                    st.code(f"HTTP {_dbg_resp.status_code}\n{_dbg_resp.text[:1500]}")

                        st.divider()
                        st.caption(
                            "Test 2 — contourne complètement la résolution par nom de champ : "
                            "interroge fieldNo=1 en brut (le champ 1 est presque toujours la clé "
                            "primaire sur une table BC standard). Si ça remonte aussi 0, le "
                            "problème n'est PAS dans la réflexion par nom mais plus en amont "
                            "(société vide, table mal ouverte, réponse OData mal formée...)."
                        )
                        if st.button("Tester recordValues (fieldNo=1 brut, sans résolution par nom)", key="btn_debug_recordvalues_raw"):
                            try:
                                _dbg_profile2 = get_profile_by_code(cfg.get("client_code", ""))
                                _dbg_tid2 = _dbg_profile2.get("bc_tenant_id", "").strip()
                                _dbg_cid2 = _dbg_profile2.get("bc_client_id", "").strip()
                                _dbg_cs2  = _dbg_profile2.get("bc_client_secret", "").strip()
                                _dbg_env2 = _dbg_profile2.get("bc_environment", "").strip()
                                _dbg_company2 = cfg.get("company_id", "")
                                _dbg_tok2 = get_access_token(_dbg_tid2, _dbg_cid2, _dbg_cs2)
                                import requests as _dbg_requests
                                from app.core.bc_api import _qc_base as _dbg_qc_base, _headers as _dbg_headers
                                _dbg_url = f"{_dbg_qc_base(_dbg_tid2, _dbg_env2, _dbg_company2)}/recordValues?$filter=tableId eq 15 and fieldNo eq 1"
                                st.code(_dbg_url)
                                _dbg_resp2 = _dbg_requests.get(_dbg_url, headers=_dbg_headers(_dbg_tok2), timeout=30)
                                st.write(f"**HTTP {_dbg_resp2.status_code}**")
                                st.code(_dbg_resp2.text[:2000])
                            except Exception as e:
                                st.error(f"{type(e).__name__}: {e}")

                        st.divider()
                        st.caption(
                            "Test 3 — même requête que le Test 1 (fieldNameFilter='No.'), mais "
                            "en URL brute construite ici, sans passer par get_record_values_qc. "
                            "Historique : confirmé cassé côté AL (comparaison FldRef.Name) — "
                            "contourné depuis via resolve_field_no_via_package(). Conservé ici à "
                            "titre de comparaison si le comportement AL changeait un jour."
                        )
                        if st.button("Tester recordValues (fieldNameFilter='No.' brut)", key="btn_debug_recordvalues_rawname"):
                            try:
                                _dbg_profile3 = get_profile_by_code(cfg.get("client_code", ""))
                                _dbg_tid3 = _dbg_profile3.get("bc_tenant_id", "").strip()
                                _dbg_cid3 = _dbg_profile3.get("bc_client_id", "").strip()
                                _dbg_cs3  = _dbg_profile3.get("bc_client_secret", "").strip()
                                _dbg_env3 = _dbg_profile3.get("bc_environment", "").strip()
                                _dbg_company3 = cfg.get("company_id", "")
                                _dbg_tok3 = get_access_token(_dbg_tid3, _dbg_cid3, _dbg_cs3)
                                import requests as _dbg_requests3
                                from app.core.bc_api import _qc_base as _dbg_qc_base3, _headers as _dbg_headers3
                                _dbg_url3 = f"{_dbg_qc_base3(_dbg_tid3, _dbg_env3, _dbg_company3)}/recordValues?$filter=tableId eq 15 and fieldNameFilter eq 'No.'"
                                st.code(_dbg_url3)
                                _dbg_resp3 = _dbg_requests3.get(_dbg_url3, headers=_dbg_headers3(_dbg_tok3), timeout=30)
                                st.write(f"**HTTP {_dbg_resp3.status_code}**")
                                st.code(_dbg_resp3.text[:2000])
                            except Exception as e:
                                st.error(f"{type(e).__name__}: {e}")

                # AJOUTÉ (19/08/2026, 2e passe) — diagnostic ciblé : affiche
                # EXACTEMENT ce que refresh_roadmap voit pour UNE entrée
                # précise du roadmap actuellement en mémoire (pas un nouveau
                # calcul isolé comme le diagnostic get_reference_values_by_
                # table_id ci-dessus — celui-ci lit le VRAI objet RoadmapEntry
                # que le bouton "Revérifier" manipule), pour trancher sans
                # deviner pourquoi un niveau reste non coché malgré une
                # correction BC confirmée (cf. table 308, 19/08).
                if _roadmap and is_consultant():
                    with st.expander("🔬 Diagnostic — état exact d'une entrée du roadmap"):
                        _diag_table_ids = [e.level_info.table_id for e in _roadmap]
                        _diag_sel_tid = st.selectbox(
                            "Table à inspecter", options=_diag_table_ids, key="diag_roadmap_entry_tid"
                        )
                        _diag_entry = next(e for e in _roadmap if e.level_info.table_id == _diag_sel_tid)
                        st.write(f"**status actuel** = `{_diag_entry.status}`")
                        st.write(f"**level** = `{_diag_entry.level_info.level}` "
                                 f"| **is_level_unlocked** = `{is_level_unlocked(_diag_entry.level_info.level, _roadmap)}`")
                        st.write(f"**last_check** (dernier résultat check_table_filled connu) = "
                                 f"`{getattr(_diag_entry, 'last_check', '(jamais vérifié)')}`")
                        st.write(f"**sub_anomalies bloquantes** = "
                                 f"`{_has_blocking_sub_anomalies(getattr(_diag_entry, 'sub_anomalies', None))}`")
                        st.write("**sub_anomalies brutes :**")
                        st.write(getattr(_diag_entry, "sub_anomalies", None) or "(aucune)")
                        if st.button("Appeler check_table_filled maintenant (contournant le cache d'affichage)", key="btn_diag_live_check"):
                            _diag_live = check_table_filled(cfg["client_code"], cfg["company_id"], _diag_sel_tid)
                            st.write(f"**check_table_filled live** = `{_diag_live}`")

                if _roadmap:
                    st.markdown("---")
                    _hcol1, _hcol2 = st.columns([5, 2])
                    with _hcol1:
                        st.markdown('<div class="step-header">🧱 Prérequis BC détectés</div>', unsafe_allow_html=True)
                    with _hcol2:
                        if st.button("🔄 Revérifier", key="btn_refresh_levels", use_container_width=True):
                            with st.spinner("Vérification BC en cours..."):
                                def _gl_check():
                                    _rc_company_id = cfg.get("company_id", "")
                                    # Live BC en premier, l'onglet du fichier n'est qu'un
                                    # repli (28/07/2026) — voir check_gl_account_prerequisites.
                                    _rc_live = _try_live_gl_account(cfg["client_code"], _rc_company_id)
                                    if _rc_live:
                                        persist_gl_account_posting_fields(cfg["client_code"], _rc_company_id, _rc_live)
                                        return check_gl_account_prerequisites(pr, _rc_live, prefer_fallback=True)
                                    _rc_extract = extract_gl_account_posting_fields(pr)
                                    if _rc_extract:
                                        persist_gl_account_posting_fields(cfg["client_code"], _rc_company_id, _rc_extract)
                                        _rc_fallback = None
                                    else:
                                        _rc_fallback = get_gl_account_posting_fields(cfg["client_code"], _rc_company_id)
                                    return check_gl_account_prerequisites(pr, _rc_fallback)

                                try:
                                    st.session_state[_roadmap_key] = refresh_roadmap(
                                        cfg["client_code"], cfg["company_id"], _roadmap,
                                        gl_account_check=_gl_check,
                                    )
                                except Exception as _refresh_e:
                                    st.error(f"Erreur lors de la revérification : {type(_refresh_e).__name__}: {_refresh_e}")
                                    st.stop()
                            st.rerun()

                    _total   = len(_roadmap)
                    _done    = sum(1 for e in _roadmap if e.status == "validated")
                    _pct     = int(100 * _done / _total) if _total else 0

                    st.markdown(f"**Progression — {_pct}%**")
                    st.progress(_pct / 100)

                    # AJOUTÉ (07/08/2026) — DIAGNOSTIC TEMPORAIRE : chronométrage
                    # précis de chaque étape du chargement des prérequis, pour
                    # identifier objectivement le vrai goulot plutôt que de deviner
                    # après plusieurs fixes qui n'ont pas suffi. À retirer une fois
                    # la cause confirmée et réglée.
                    if "_perf_log_prereqs" in st.session_state:
                        with st.expander("⏱️ Chronométrage chargement prérequis (temporaire)", expanded=True):
                            for _label, _dur in st.session_state["_perf_log_prereqs"]:
                                st.code(f"{_label} : {_dur:.2f}s", language=None)

                    try:
                        for _entry in _roadmap:
                            _unlocked = is_level_unlocked(_entry.level_info.level, _roadmap)
                            _label = _entry.level_info.table_name
                            if _entry.level_info.sub_level:
                                _label = f"{_label} ({_entry.level_info.sub_level})"

                            if _entry.status == "validated":
                                _circle, _lbl_cls = '<div class="level-check-circle-done">✓</div>', "level-check-label-done"
                            elif not _unlocked:
                                _circle, _lbl_cls = '<div class="level-check-circle-todo"></div>', "level-check-label-locked"
                            else:
                                _circle, _lbl_cls = '<div class="level-check-circle-todo"></div>', "level-check-label-todo"

                            st.markdown(
                                f'<div class="level-check-item">{_circle}'
                                f'<span class="{_lbl_cls}">{_label}</span></div>',
                                unsafe_allow_html=True,
                            )
                            # getattr défensif : un RoadmapEntry déjà présent dans
                            # st.session_state (construit par une version antérieure du
                            # code, avant l'ajout de ce champ) n'a pas sub_anomalies —
                            # confirmé par l'AttributeError remontée par Rami le 27/07.
                            _sub_anomalies = getattr(_entry, "sub_anomalies", None)
                            if _sub_anomalies:
                                with st.expander(
                                    f"⚠️ {len(_sub_anomalies)} champ(s) manquant(s) sur des comptes référencés",
                                    expanded=False,
                                ):
                                    st.dataframe(
                                        pd.DataFrame(_sub_anomalies),
                                        use_container_width=True, hide_index=True,
                                    )
                    except Exception as _diag_e:
                        # DIAGNOSTIC — laissé en place tant qu'on n'a pas une confirmation
                        # de stabilité dans la durée. Sans impact visuel si tout va bien.
                        import traceback
                        st.error("🔧 DIAGNOSTIC — erreur capturée dans la boucle d'affichage de la roadmap :")
                        st.code(traceback.format_exc())

                    # AJOUTÉ (07/08/2026) : export consolidé de TOUS les niveaux en
                    # un seul fichier — jusqu'ici chaque niveau n'était téléchargeable
                    # qu'individuellement via l'icône native du st.dataframe, obligeant
                    # à recopier/exporter niveau par niveau pour construire un
                    # comparatif complet contre les erreurs BC réelles.
                    _all_sub_anomalies = []
                    for _e in _roadmap:
                        _e_sub = getattr(_e, "sub_anomalies", None)
                        if _e_sub:
                            for _a in _e_sub:
                                _row = dict(_a)
                                _row["Niveau"] = _e.level_info.table_name
                                _all_sub_anomalies.append(_row)
                    if _all_sub_anomalies:
                        st.download_button(
                            "⬇️ Toutes les anomalies (tous niveaux)",
                            data=build_prerequisites_excel(_all_sub_anomalies),
                            file_name="anomalies_tous_niveaux.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_all_sub_anomalies",
                        )

                    _levels_ok = all_validated(_roadmap)
                    if not _levels_ok:
                        st.info("🔒 L'analyse qualité reste verrouillée tant que tous les niveaux ne sont pas validés dans BC.")
                        # Contournement TEMPORAIRE, consultant uniquement — le temps que
                        # les tables "Non classé" soient examinées avec Shema et classées
                        # dans level_config (niveau réel ou ignored=true). Ne doit jamais
                        # être visible ni utilisable par un client. Affiché UNIQUEMENT s'il
                        # existe réellement des entrées level=None dans la roadmap — pas
                        # à chaque fois qu'un niveau correctement classé attend juste
                        # d'être rempli dans BC (ça, c'est le fonctionnement normal du
                        # gate, aucun rapport avec une classification manquante).
                        _has_unclassified = any(e.level_info.level is None for e in _roadmap)
                        if _has_unclassified and is_consultant():
                            st.warning(
                                "🔧 Consultant — des tables restent non classées dans level_config. "
                                "Ce contournement passe outre la vérification, uniquement pour "
                                "continuer les tests le temps de la classification."
                            )
                            if st.checkbox("Ignorer temporairement le verrouillage (consultant, test uniquement)", key="bypass_levels"):
                                _levels_ok = True
                # _roadmap vide => aucune dépendance de niveau détectée => _levels_ok reste True (analyse directe)
            # level_config vide/non chargée : ne bloque pas l'analyse — à corriger si level_config
            # doit être rendue obligatoire (dépend de si tu veux imposer le seed avant tout usage).

        st.markdown("---")
        cb, cv, crc = st.columns([2, 5, 2])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step         = 2
                st.session_state.parse_result = None
                st.session_state.validation   = None
                st.rerun()
        with crc:
            if st.button("🔄 Recommencer", use_container_width=True, key="rc_step3"):
                reset_session()
                st.rerun()
        with cv:
            if val["is_valid"]:
                if st.button(
                    "🚀 Lancer l'analyse qualité →", type="primary", use_container_width=True,
                    disabled=not _levels_ok,
                ):
                    api_key     = get_gemini_api_key()
                    client_code = cfg.get("client_code", "")
                    _early = st.session_state.get(_early_axeb_key)

                    if _early:
                        # Déjà calculés pour le gate niveaux — pas la peine de relancer
                        # Axe A/Axe B une seconde fois pour le même fichier/package.
                        axe_a = _early["axe_a"]
                        axe_b = _early["axe_b"]
                    else:
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
        display_correction_workflow(merged, cfg, pr)

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
                # AJOUTÉ (19/08/2026) — architecture mère/fille : rattache
                # cette session soit comme racine d'un socle, soit comme
                # session fille pour une table précise de la roadmap, avec
                # résolution automatique du parent quand un seul candidat
                # existe (voir resolve_parent_candidates, sessions_db.py).
                _tree_sessions = get_sessions_for_company(
                    cfg.get("client_code", ""), cfg.get("company_id", "")
                )
                _lvl_cfg = st.session_state.get("level_config", {})
                _orig_b = st.session_state.get("original_file_bytes")
                _table_options: list[tuple[int, str]] = []
                if _orig_b:
                    try:
                        from app.core.bc_excel_processor import extract_sheets_info
                        for _si in extract_sheets_info(_orig_b):
                            _tid = int(_si["table_id"]) if str(_si["table_id"]).isdigit() else 0
                            if _tid:
                                _tname = (
                                    _lvl_cfg[_tid].table_name if _tid in _lvl_cfg
                                    else _si.get("table_name", str(_tid))
                                )
                                _table_options.append((_tid, f"{_tid} — {_tname}"))
                    except Exception:
                        _table_options = []

                _node_kind = st.radio(
                    "Type de session",
                    ["Racine (socle complet)", "Fille (une table de la roadmap)"],
                    key="node_kind_radio",
                    horizontal=True,
                )
                _sel_table_id: int | None = None
                _sel_parent_id: str | None = None
                if _node_kind == "Fille (une table de la roadmap)" and _table_options:
                    _sel_table_id = st.selectbox(
                        "Table traitée par cette session",
                        options=[t[0] for t in _table_options],
                        format_func=lambda tid: dict(_table_options).get(tid, str(tid)),
                        key="node_table_select",
                    )
                    _candidates = resolve_parent_candidates(_tree_sessions, _sel_table_id, _lvl_cfg)
                    if len(_candidates) == 1:
                        _sel_parent_id = _candidates[0]["id"]
                        st.caption(f"↳ Rattachée automatiquement à : **{_candidates[0].get('name', '')}**")
                    elif len(_candidates) > 1:
                        _parent_names = {c["id"]: c.get("name", c["id"]) for c in _candidates}
                        _sel_parent_id = st.selectbox(
                            "Plusieurs sessions candidates au même niveau — choisis la session parente",
                            options=list(_parent_names.keys()),
                            format_func=lambda pid: _parent_names.get(pid, pid),
                            key="node_parent_select",
                        )
                    else:
                        st.caption("↳ Aucune session de niveau inférieur trouvée — rattachée à la racine du socle.")
                elif _node_kind == "Fille (une table de la roadmap)":
                    st.warning("Aucune table détectée dans le fichier chargé — impossible de créer une session fille.")

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
                        # AJOUTÉ (19/08/2026) — architecture mère/fille.
                        "table_id":            _sel_table_id,
                        "parent_session_id":   _sel_parent_id,
                        "is_root":             _node_kind == "Racine (socle complet)",
                        "pkg_code":            cfg.get("pkg_code", ""),
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

    # AJOUTÉ (19/08/2026) — architecture mère/fille : bascule entre la vue
    # consolidée existante (inchangée, toutes sociétés/clients confondus) et
    # une vue arbre par société, reflétant parent_session_id. Les deux
    # coexistent — décision actée avec Rami (04-07/08) de garder la vue
    # consolidée en plus de l'arbre, pas à sa place.
    # AJOUTÉ (19/08/2026, 2e passe) — même valeur que _CLOSED_STATUS dans
    # sessions_db.py (can_close_session) ; dupliquée ici en constante locale
    # plutôt que d'importer un nom privé (préfixé _) d'un autre module.
    _CLOSED_STATUS_LABEL = "Terminée"

    _view_mode = st.radio(
        "Affichage", ["📋 Liste consolidée", "🌳 Vue arbre (par société)"],
        key="ses_view_mode", horizontal=True, label_visibility="collapsed",
    )

    if _view_mode == "🌳 Vue arbre (par société)":
        _companies = sorted({
            (s.get("company_id", ""), s.get("company_name", "") or s.get("company_id", ""))
            for s in sessions if s.get("company_id")
        }, key=lambda c: c[1])
        if not _companies:
            st.info("Aucune session rattachée à une société pour l'instant.")
        else:
            _company_labels = {cid: f"{cname} ({cid})" for cid, cname in _companies}
            _sel_company = st.selectbox(
                "Société", options=[c[0] for c in _companies],
                format_func=lambda cid: _company_labels.get(cid, cid),
                key="ses_tree_company",
            )
            _tree_sessions_view = get_sessions_for_company(active_client or "", _sel_company)
            _tree = build_sessions_tree(_tree_sessions_view)
            if not _tree:
                st.info("Aucune session pour cette société.")
            else:
                _lvl_cfg_view = st.session_state.get("level_config", {})

                def _render_node(node: dict, depth: int = 0):
                    _nid    = node["id"]
                    _status = node.get("status", "Nouvelle")
                    _sc     = STATUS_COLORS.get(_status, "#64748B")
                    _si     = STATUS_ICONS.get(_status, "")
                    _tid    = node.get("table_id")
                    _pkg    = node.get("pkg_code", "")
                    _tname  = (
                        "📁 Racine du socle" if node.get("is_root")
                        else (f"{_tid} — {_lvl_cfg_view[_tid].table_name}" if _tid in _lvl_cfg_view else f"Table {_tid}")
                    )
                    indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * depth
                    prefix = "└─ " if depth > 0 else ""
                    st.markdown(
                        f'<div style="margin-left:{depth*24}px">'
                        f'<span style="color:#94A3B8">{prefix}</span>'
                        f'<b>{node.get("name", "")}</b> · {_tname}'
                        f'{" · 📦 " + _pkg if _pkg else ""} · '
                        f'<span style="color:{_sc}">{_si} {_status}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if not node.get("is_root") and _tid:
                        rc1, rc2 = st.columns([1, 1])
                        with rc1:
                            if st.button("🔄 Revérifier ce sous-arbre", key=f"scope_reverif_{_nid}"):
                                _scope = get_descendant_table_ids(_nid, _tree_sessions_view)
                                _roadmap_key_guess = None
                                for k in st.session_state.keys():
                                    if isinstance(k, str) and k.startswith("level_roadmap_") and _sel_company in k:
                                        _roadmap_key_guess = k
                                        break
                                if _roadmap_key_guess and st.session_state.get(_roadmap_key_guess):
                                    st.session_state[_roadmap_key_guess] = refresh_roadmap(
                                        profile_code=active_client or "",
                                        company_id=_sel_company,
                                        roadmap=st.session_state[_roadmap_key_guess],
                                        scope_table_ids=_scope,
                                    )
                                    st.success(f"Sous-arbre revérifié ({len(_scope)} table(s)).")
                                else:
                                    st.warning(
                                        "Aucune roadmap chargée en mémoire pour cette société — "
                                        "ouvre d'abord l'Étape 3 (Sessions) pour cette société, "
                                        "puis reviens revérifier ce sous-arbre."
                                    )
                        with rc2:
                            # AJOUTÉ (19/08/2026, 2e passe) — clôture conditionnelle :
                            # une session fille ne peut passer "Terminée" que si son
                            # propre contrôle est propre ET tous ses enfants directs
                            # sont déjà "Terminée" (can_close_session, sessions_db.py).
                            if _status == _CLOSED_STATUS_LABEL:
                                st.caption("✅ Déjà clôturée")
                            elif st.button("🔒 Clôturer", key=f"close_{_nid}"):
                                _ok, _reasons = can_close_session(_nid, _tree_sessions_view)
                                if _ok:
                                    _uok, _uerr = update_session(_nid, {"status": _CLOSED_STATUS_LABEL})
                                    if _uok:
                                        st.success("Session clôturée.")
                                        st.rerun()
                                    else:
                                        st.error(f"Échec de la clôture : {_uerr}")
                                else:
                                    st.warning("Impossible de clôturer :\n" + "\n".join(f"- {r}" for r in _reasons))
                    elif node.get("is_root"):
                        # Clôture du socle entier — même règle, appliquée à la racine :
                        # bloquée tant que le socle lui-même a des anomalies ou qu'une
                        # SEULE de ses filles directes n'est pas encore "Terminée"
                        # (chaque fille "Terminée" garantit déjà la propreté de SA
                        # propre branche, récursivement — voir can_close_session).
                        if _status == _CLOSED_STATUS_LABEL:
                            st.success("🏁 Socle clôturé — tous les niveaux et sous-niveaux sont vérifiés.")
                        elif st.button("🏁 Clôturer le socle", key=f"close_root_{_nid}"):
                            _ok, _reasons = can_close_session(_nid, _tree_sessions_view)
                            if _ok:
                                _uok, _uerr = update_session(_nid, {"status": _CLOSED_STATUS_LABEL})
                                if _uok:
                                    st.success("Socle clôturé.")
                                    st.rerun()
                                else:
                                    st.error(f"Échec de la clôture : {_uerr}")
                            else:
                                st.warning("Le socle ne peut pas encore être clôturé :\n" + "\n".join(f"- {r}" for r in _reasons))
                    for child in node.get("children", []):
                        _render_node(child, depth + 1)

                for _root in _tree:
                    _render_node(_root)
                    st.markdown("---")
    else:
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