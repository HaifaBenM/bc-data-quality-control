import base64
import streamlit as st
import pandas as pd
from datetime import datetime
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a
from app.core.validator_axe_b import validate_file_axe_b
from app.core.validator_axe_c import validate_file_axe_c, get_gemini_api_key, is_gemini_available, validate_coherence_axe_c
from app.core.auth import require_role, is_consultant
from app.core.execution_planner import get_execution_plan, build_plan_from_bc
from app.core.integration_levels import (
    load_level_config, traverse_dependencies, build_roadmap, build_roadmap_from_prereqs,
    is_level_unlocked, refresh_roadmap, all_validated,
    check_table_filled, _has_blocking_sub_anomalies, compute_dynamic_levels,
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
    save_roadmap_table_history, get_roadmap_table_history,
)
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import (
    get_access_token, get_companies, get_packages_qc, get_gl_account_fields_live,
    diagnose_standard_api_account, run_bc_import_check, apply_configuration_package,
)
from app.db.sessions_db import (
    save_session, update_session, delete_session,
    get_all_sessions, SESSION_STATUSES, STATUS_COLORS, STATUS_ICONS,
    get_sessions_for_company, build_sessions_tree,
    resolve_parent_candidates, get_descendant_table_ids, can_close_session,
    get_session_file_blob,
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
.anomaly-big-num {
    font-size: 2.6rem; font-weight: 800; line-height: 1; margin: 0;
}
.anomaly-big-lbl { font-size: .85rem; color: #64748B; margin: .2rem 0 0; }
.anomaly-bc-pill {
    display: inline-block; margin-top: .5rem; padding: .25rem .7rem;
    border-radius: 999px; font-size: .8rem; font-weight: 600;
}
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
    padding: .55rem .75rem; font-size: .92rem;
    background: #F8FAFC; border-radius: 6px; margin-bottom: .3rem;
}
.level-check-sub { font-size: .78rem; color: #B45309; margin: .1rem 0 .3rem 2.6rem; }
/* AJOUTÉ (26/08/2026) — demande Rami : l'expander natif Streamlit (bordure
   grise plate) jurait avec les cartes .level-check-item (fond bleu clair,
   coins arrondis) utilisées partout ailleurs dans la roadmap. Harmonise
   tous les expanders de la page avec ce même langage visuel — bénéfice
   valable aussi pour "Données source" et le détail des sub_anomalies, pas
   seulement le nouveau groupe "Plan comptable". */
div[data-testid="stExpander"] {
    border: 1px solid #DCE7F5; border-radius: 8px; background: #F8FAFC;
}
div[data-testid="stExpander"] summary {
    font-size: .92rem; padding: .55rem .75rem;
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
.tree-card {
    background: white; border: 1px solid #E2E8F0; border-left: 4px solid #94A3B8;
    border-radius: 8px; padding: .7rem 1rem; margin: .3rem 0;
}
.tree-card-root { background: #FFFBEB; }
.tree-card-title { font-size: .95rem; font-weight: 600; color: #1B3A6B; }
.tree-card-meta { font-size: .8rem; color: #64748B; margin-top: .2rem; }
.tree-connector { color: #CBD5E1; font-size: .85rem; margin-right: .3rem; }
.status-pill {
    display: inline-block; padding: .12rem .55rem; border-radius: 999px;
    font-size: .72rem; font-weight: 600; margin-left: .4rem;
}
.pkg-pill {
    display: inline-block; padding: .12rem .5rem; border-radius: 5px;
    font-size: .72rem; font-weight: 500; margin-left: .4rem;
    background: #EEF4FD; color: #1B3A6B;
}
.session-row-actions { margin: .2rem 0 .6rem; }
/* RÉVISÉ (27/08/2026, 2e passe) — demande Rami : encore plus grand —
   popover élargi davantage, police des filtres et du mot "Filtres"
   (déclencheur) agrandis. Plusieurs sélecteurs de repli car le nom exact
   des attributs data-testid varie selon la version de Streamlit — ceux
   qui ne correspondent à rien sont simplement ignorés, sans risque. */
div[data-testid="stPopoverBody"], div[data-testid="stPopover"] > div {
    min-width: 380px;
}
div[data-testid="stPopoverBody"] label,
div[data-testid="stPopoverBody"] div[data-baseweb="select"],
div[data-testid="stPopoverBody"] div[data-baseweb="select"] * {
    font-size: 1.05rem !important;
}
div[data-testid="stPopover"] button p,
div[data-testid="stPopover"] button span {
    font-size: 1.05rem !important;
}
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
            return {}
        tid = p.get("bc_tenant_id", "").strip()
        cid = p.get("bc_client_id", "").strip()
        cs  = p.get("bc_client_secret", "").strip()
        env = p.get("bc_environment", "").strip()
        if not all([tid, cid, cs, env, company_id]):
            return {}
        tok  = get_access_token(tid, cid, cs)
        live = get_gl_account_fields_live(tid, env, company_id, tok)
        return live or {}
    except Exception:
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
                #
                # RÉVISÉ (26/08/2026, jour J) — demande Rami : les anomalies
                # "Trigger OnInsert" (trigger_simulator.py — ex. "Groupe
                # compta. produit doit exister") n'ont jamais eu de
                # classification propre et retombaient à tort sur
                # VALEUR_CORRIGIBLE — alors que leur nature est identique
                # aux Prérequis BC requis : le problème n'est pas une valeur
                # à corriger DANS le fichier, c'est une donnée qui doit
                # exister CÔTÉ BC (groupe comptable, ici). Reclassé en
                # conséquence, avant le setdefault générique.
                if a.get("Type d'anomalie") == "Trigger OnInsert":
                    clean.setdefault("Classification", "PREALABLE_BC_REQUIS")
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


def _filter_resolved_prereqs(all_anomalies: list, resolved_by_table: dict | None, hide_all_prereqs: bool = False, validated_table_ids: set | None = None) -> tuple[list, int]:
    """AJOUTÉ (23/08/2026) — factorisé pour être utilisé à la fois pour les
    compteurs du haut de l'Étape 4 et pour le tableau détaillé
    (display_merged_analysis), afin que les deux restent cohérents entre
    eux. Voir le commentaire dans display_merged_analysis pour le contexte
    complet (anomalies PREALABLE_BC_REQUIS déjà résolues dans la roadmap).

    hide_all_prereqs (AJOUTÉ 26/08/2026) — demande Rami : règle globale plus
    simple en complément du filtrage par code précis ci-dessous — dès que
    TOUTE la roadmap est cochée (verte ou mémoire inter-sessions, voir
    all_validated()), on masque TOUTES les anomalies "Prérequis BC requis"
    restantes d'un coup, même celles dont le code précis n'aurait pas été
    retrouvé dans last_codes (correspondance imparfaite possible, ex.
    variation de casse) — la roadmap fait foi une fois complète.

    validated_table_ids (AJOUTÉ 26/08/2026, 2e passe) — bug trouvé : le
    filtrage par code précis (`val in resolved_by_table[tid]`) exige une
    valeur non vide (`if val and ...`) — une anomalie cascade comme
    "Souches de n° n'existe pas... Code=''" (valeur VIDE par construction,
    ce n'est pas un code invalide mais une absence totale de souche
    configurée) ne peut donc JAMAIS être filtrée par cette voie, même si la
    table 308 est déjà validée ✓ dans la roadmap. Ce nouveau critère
    complète le premier : si le NIVEAU de la table référencée est validé
    (peu importe BC réel ou mémoire), on masque TOUTES ses anomalies
    PREALABLE_BC_REQUIS, avec ou sans valeur précise à faire correspondre."""
    if not resolved_by_table and not hide_all_prereqs and not validated_table_ids:
        return all_anomalies, 0
    kept, resolved_count = [], 0
    for a in all_anomalies:
        if a.get("Classification") == "PREALABLE_BC_REQUIS":
            if hide_all_prereqs:
                resolved_count += 1
                continue
            try:
                tid = int(a.get("Table référencée", -1))
            except (TypeError, ValueError):
                tid = -1
            if validated_table_ids and tid in validated_table_ids:
                resolved_count += 1
                continue
            val = str(a.get("Valeur", "")).strip()
            if val and val in (resolved_by_table or {}).get(tid, set()):
                resolved_count += 1
                continue
        kept.append(a)
    return kept, resolved_count


def display_merged_analysis(merged: dict, axe_c: dict, cfg: dict, pr: dict = None, resolved_by_table: dict | None = None, roadmap: list | None = None):
    """
    RÉVISÉ (26/08/2026) — demande Rami : fusion de l'ancien tableau de
    lecture (display_unified_results) et du tableau de correction
    (display_correction_workflow) en UN SEUL tableau — Valeur source /
    Correction suggérée / Nouvelle valeur, avec filtres par colonne
    (Sévérité, Type d'anomalie, Champ, Classification) et un bouton
    "Propager" (équivalent utile de la poignée de recopie Excel — pas de
    glisser-déposer possible techniquement dans ce composant, mais même
    résultat : appliquer une correction à toutes les lignes partageant la
    même valeur source dans le même champ).

    ⚠️ Le fichier généré n'a pas été validé par un import BC réel — à tester
    avant de le présenter comme "100% intégrable" en démo.
    """
    # AJOUTÉ (27/08/2026, jour de la démo) — demande Rami : le diagnostic IA
    # ne s'affichait que pendant l'exécution du clic "Lancer l'analyse
    # qualité" et disparaissait au rerun suivant, impossible à copier à
    # temps. Persisté en session_state (voir le bloc qui le calcule), lu et
    # réaffiché ici en permanence — présent à chaque rendu de l'Étape 4,
    # peu importe ce qui a déclenché le rerun. Message clair et présentable
    # en plus du détail technique brut, spécifiquement quand le quota
    # gratuit Gemini est épuisé (429 / RESOURCE_EXHAUSTED) — utile à
    # montrer tel quel en démo plutôt qu'un message d'erreur brut.
    _ia_err = st.session_state.get("_ia_diag_error", "")
    if _ia_err and ("429" in _ia_err or "RESOURCE_EXHAUSTED" in _ia_err or "quota" in _ia_err.lower()):
        st.warning(
            "⚠️ **Quota gratuit de l'IA momentanément épuisé** — la détection "
            "d'incohérences fonctionne normalement, mais le service Google "
            "Gemini limite le nombre de requêtes gratuites par période. "
            "Ce n'est pas un défaut de l'outil, juste une limite temporaire "
            "du service tiers utilisé."
        )
    if st.session_state.get("_ia_diag_text") and is_consultant():
        with st.expander("🔬 Diagnostic cohérence IA (clique l'icône en haut à droite du bloc pour copier)"):
            st.code(st.session_state["_ia_diag_text"], language="text")

    all_anomalies = merged.get("all_anomalies", [])

    # AJOUTÉ (23/08/2026) ; RÉVISÉ (26/08/2026, règle globale hide_all_prereqs)
    # — une anomalie "Prérequis BC requis" reste affichée tant que son code
    # précis n'est pas retrouvé dans BC/mémoire (résolved_by_table), OU
    # disparaît d'un coup dès que toute la roadmap est cochée (verte ou
    # mémoire inter-sessions) — la roadmap fait foi une fois complète, même
    # si une correspondance de code précise a pu échouer (accents/casse).
    _hide_all_prereqs = bool(roadmap) and all_validated(roadmap)
    # AJOUTÉ (26/08/2026, 2e passe) — voir docstring validated_table_ids de
    # _filter_resolved_prereqs : masque les anomalies d'une table dont le
    # NIVEAU est déjà validé, même sans correspondance de code précise
    # (cas des anomalies cascade à valeur vide, ex. "Souches de n°").
    _validated_table_ids = {e.level_info.table_id for e in (roadmap or []) if e.status == "validated"}
    all_anomalies, _resolved_count = _filter_resolved_prereqs(
        all_anomalies, resolved_by_table, hide_all_prereqs=_hide_all_prereqs,
        validated_table_ids=_validated_table_ids,
    )

    real = [a for a in all_anomalies if a.get("Ligne", 0) > 0]
    info = [a for a in all_anomalies if a.get("Ligne", 0) == 0]

    if not real and not info:
        if _resolved_count:
            st.success(
                f"🎉 **Aucune anomalie active !** ({_resolved_count} prérequis BC "
                f"déjà résolu(s) — roadmap complète ou codes confirmés, retiré(s) de l'affichage.)"
            )
        else:
            st.success("🎉 **Aucune anomalie détectée !** Les données sont conformes.")
        st.session_state["prerequisites_report"] = []
        return

    if _resolved_count:
        st.caption(
            f"✅ {_resolved_count} anomalie(s) « Prérequis BC requis » déjà résolue(s) "
            f"— retirée(s) de l'affichage ci-dessous."
        )

    has_ia = axe_c.get("available") and axe_c.get("total_suggestions", 0) > 0
    auto_c = axe_c.get("auto_corrected", 0)
    if has_ia and auto_c > 0:
        st.info(f"🤖 **{auto_c} correction(s) appliquée(s) automatiquement** par l'IA")

    by_sheet: dict[str, list] = {}
    for a in all_anomalies:
        by_sheet.setdefault(a.get("Onglet", ""), []).append(a)
    for _sn in merged.get("by_sheet", {}):
        by_sheet.setdefault(_sn, [])
    sheet_names = list(merged.get("by_sheet", {}).keys()) or list(by_sheet.keys())
    tab_labels = []
    for sn in sheet_names:
        a = by_sheet[sn]
        nb = len([x for x in a if x.get("Ligne", 0) > 0])
        nmaj = sum(1 for x in a if x.get("Sévérité") == "Majeure")
        icon = "🔴" if nmaj > 0 else ("🟠" if nb > 0 else "✅")
        tab_labels.append(f"{icon} {sn} ({nb})")

    if not tab_labels:
        return

    _sheet_labels = dict(zip(sheet_names, tab_labels))
    sn = st.segmented_control(
        "Feuille", options=sheet_names,
        format_func=lambda s: _sheet_labels.get(s, s),
        key="unified_results_sheet_select",
        label_visibility="collapsed",
        default=sheet_names[0],
    )
    if sn is None:
        sn = sheet_names[0]

    anomalies = by_sheet.get(sn, [])
    real_anomalies = [a for a in anomalies if a.get("Ligne", 0) > 0]
    info_anomalies = [a for a in anomalies if a.get("Ligne", 0) == 0]

    if not real_anomalies and not info_anomalies:
        st.success("✅ Aucune anomalie.")
        st.session_state["prerequisites_report"] = build_prerequisites_report(
            [a for a in all_anomalies if a.get("Ligne", 0) > 0],
            profile_code=cfg.get("client_code", ""), company_id=cfg.get("company_id", ""),
        )
        return

    nb_maj = sum(1 for a in real_anomalies if a.get("Sévérité") == "Majeure")
    nb_min = sum(1 for a in real_anomalies if a.get("Sévérité") == "Mineure")
    nb_ia = sum(1 for a in real_anomalies if a.get("suggestion_ia"))
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Anomalies", len(real_anomalies))
    t2.metric("🔴 Majeures", nb_maj)
    t3.metric("🟠 Mineures", nb_min)
    # RÉVISÉ (26/08/2026) — demande Rami : rendre "IA suggère" cliquable,
    # avec le détail des modifications proposées par l'IA — st.metric ne
    # supporte aucune interaction, remplacé par un st.popover (même
    # composant déjà utilisé ailleurs dans l'app) qui affiche le chiffre
    # comme libellé et le détail de chaque suggestion au clic.
    with t4:
        with st.popover(f"🤖 IA suggère : {nb_ia}", use_container_width=True):
            _ia_rows = [a for a in real_anomalies if a.get("suggestion_ia")]
            if not _ia_rows:
                st.caption("Aucune suggestion IA sur cet onglet pour l'instant.")
            for _a in _ia_rows[:30]:
                st.markdown(
                    f"**{_a.get('Champ', '')}** (ligne {_a.get('Ligne', '')}, "
                    f"{_a.get('Identifiant métier', '')}) : "
                    f"`{_a.get('Valeur', '')}` → **{_a.get('suggestion_ia', '')}** "
                    f"({_a.get('confiance_ia', 0)}% de confiance)"
                )
                if _a.get("Message"):
                    st.caption(_a["Message"])
                st.markdown("---")
            if len(_ia_rows) > 30:
                st.caption(f"... et {len(_ia_rows) - 30} autre(s), non affichée(s) ici.")

    # AJOUTÉ (26/08/2026) — demande Rami : filtres façon Excel. Streamlit
    # n'a pas de filtre par en-tête de colonne comme Excel — ces menus
    # déroulants au-dessus du tableau font le même travail (rétrécir les
    # lignes affichées par valeur de colonne), juste présentés autrement.
    # Champ et Classification ajoutés en plus de Sévérité/Type d'anomalie
    # déjà existants, pour couvrir toutes les colonnes utiles à la
    # recherche d'une ligne précise à corriger.
    # RÉVISÉ (27/08/2026, 3e passe) — demande Rami : déclencheur encore plus
    # compact (taille bouton normal, pas de colonne dédiée) tout en gardant
    # les 4 filtres sur UNE SEULE ligne une fois ouverts — impossible avec
    # un st.expander (son contenu reste contraint à la largeur de la
    # colonne qui le contient, même étroite). st.popover s'affiche en
    # panneau flottant : déclencheur compact ET contenu pleine largeur au
    # clic, sans dépendre l'un de l'autre.
    # RÉVISÉ (27/08/2026, 4e passe) — demande Rami : "pas beau, pas lisible"
    # — 4 colonnes côte à côte dans un popover (nativement étroit) tronquait
    # tout (valeurs sélectionnées, icônes de suppression illisibles,
    # entassées). Empilé verticalement à la place : chaque filtre prend
    # toute la largeur du popover, plus de troncature.
    with st.popover("🔍 Filtres"):
        sevs = sorted(set(a.get("Sévérité", "") for a in real_anomalies))
        filt_sev = st.multiselect("Sévérité", sevs, default=sevs, key=f"fs_{sn}")

        types = sorted(set(a.get("Type d'anomalie", "") for a in real_anomalies))
        filt_type = st.multiselect("Type d'anomalie", types, default=types, key=f"ft_{sn}")

        champs = sorted(set(a.get("Champ", "") for a in real_anomalies))
        filt_champ = st.multiselect("Champ", champs, default=champs, key=f"fc_{sn}")

        _cls_label = {
            "PREALABLE_BC_REQUIS": "🟣 Prérequis BC requis",
            "VALEUR_CORRIGIBLE":   "✏️ Corrigible",
            # AJOUTÉ (26/08/2026, jour J) — nouvelle classification apportée
            # par la détection de cohérence (validate_coherence_axe_c),
            # jamais mappée jusqu'ici — s'affichait vide dans la colonne.
            "SUGGESTION_IA":       "🧠 Suggestion IA",
        }
        clss = sorted(set(a.get("Classification", "") for a in real_anomalies))
        filt_cls = st.multiselect(
            "Classification", clss, default=clss, key=f"fcl_{sn}",
            format_func=lambda c: _cls_label.get(c, c or "(aucune)"),
        )

    filtered = [
        a for a in real_anomalies
        if a.get("Sévérité", "") in filt_sev
        and a.get("Type d'anomalie", "") in filt_type
        and a.get("Champ", "") in filt_champ
        and a.get("Classification", "") in filt_cls
    ]

    if not filtered:
        st.info("Aucune ligne ne correspond aux filtres sélectionnés.")
    else:
        _sev_icon = {"Majeure": "🔴 Majeure", "Mineure": "🟠 Mineure"}
        _has_ia_col = any(a.get("suggestion_ia") for a in filtered)

        # AJOUTÉ (26/08/2026) — demande Rami : sélection en lot, comme avant
        # sur l'ancien tableau de correction, désormais applicable au
        # tableau fusionné entier.
        _editor_gen_key = f"merged_editor_gen_{sn}"
        if _editor_gen_key not in st.session_state:
            st.session_state[_editor_gen_key] = 0

        # RÉVISÉ (27/08/2026, 5e passe) — demande Rami : l'icône seule
        # "fait amateur" — retour à un seul bouton à bascule avec texte
        # complet ("✅ Tout sélectionner" / "⬜ Tout désélectionner"), qui
        # change de libellé selon l'état courant au lieu de 2 boutons
        # séparés.
        _all_sel_key = f"_all_selected_state_{sn}"
        if _all_sel_key not in st.session_state:
            st.session_state[_all_sel_key] = False
        _toggle_label = "⬜ Tout désélectionner" if st.session_state[_all_sel_key] else "✅ Tout sélectionner"

        if is_consultant():
            csel1, csel3, _csel_spacer = st.columns([1.4, 1.4, 5.2])
        else:
            csel1, _csel_spacer = st.columns([1.4, 6.6])
            csel3 = None
        with csel1:
            if st.button(_toggle_label, key=f"btn_toggle_select_{sn}", use_container_width=True):
                st.session_state[_all_sel_key] = not st.session_state[_all_sel_key]
                st.session_state[f"_merged_select_override_{sn}"] = st.session_state[_all_sel_key]
                st.session_state[_editor_gen_key] += 1
                st.rerun()
        _select_override = st.session_state.pop(f"_merged_select_override_{sn}", None)
        # AJOUTÉ (26/08/2026) — overrides posés par "🔁 Propager" ci-dessous
        # (valeur manuelle appliquée à toutes les lignes de même Champ +
        # Valeur source qui n'avaient pas encore de correction saisie).
        _propagate_overrides: dict = st.session_state.get(f"_propagate_overrides_{sn}", {})

        # AJOUTÉ (26/08/2026, 2e passe) ; RÉVISÉ (27/08/2026, retrait Copier) —
        # affichage du message persisté posé par "🔁 Propager" lors du run
        # précédent, juste avant son propre st.rerun() — voir commentaire sur
        # le piège "message avant rerun jamais visible" plus bas.
        _propagate_fb = st.session_state.pop(f"_propagate_feedback_{sn}", None)
        if _propagate_fb:
            (st.success if _propagate_fb[0] == "success" else st.info)(_propagate_fb[1])

        def _row(a: dict) -> dict:
            _key = (a.get("Champ", ""), str(a.get("Valeur", "")).strip())
            _is_corrigible = a.get("Classification") in ("VALEUR_CORRIGIBLE", "SUGGESTION_IA")
            _suggestion = a.get("Correction suggérée", "")
            # RÉVISÉ (26/08/2026, jour J) — demande Rami : une anomalie
            # d'incohérence IA n'a pas de "Correction suggérée" classique
            # (désormais dans sa propre colonne "🤖 Suggestion IA", voir
            # coherence_detector.py) — sans repli, "Nouvelle valeur"
            # resterait vide et impossible à appliquer directement. Repli
            # sur suggestion_ia uniquement quand Correction suggérée est
            # vide, pour que la ligne reste éditable/applicable de bout en
            # bout comme les autres.
            if not _suggestion:
                _suggestion = a.get("suggestion_ia", "")
            _nouvelle = _propagate_overrides.get(_key, _suggestion)
            _appliquer = (
                _select_override if _select_override is not None
                else (_is_corrigible and bool(str(_nouvelle).strip()))
            )
            # RÉVISÉ (27/08/2026, jour de la démo) — demande Rami : retirer
            # "Correction suggérée" de l'affichage, la remplacer à sa place
            # par "🤖 Suggestion IA" — une seule colonne de suggestion
            # visible, quelle que soit son origine (similarité de texte ou
            # IA). Rien ne change en interne : "Correction suggérée" (a.get
            # ci-dessus, via _suggestion) continue de servir au pré-
            # remplissage de "Nouvelle valeur" — seule la colonne AFFICHÉE
            # change.
            _ia_display = ""
            if a.get("suggestion_ia"):
                _ia_display = f"{a['suggestion_ia']} ({a.get('confiance_ia', 0)}%)"
            elif a.get("Correction suggérée"):
                _ia_display = a["Correction suggérée"]
            out = {
                "Appliquer":          _appliquer,
                "Onglet":             a.get("Onglet", ""),
                "Ligne":              a.get("Ligne", ""),
                "Identifiant métier": a.get("Identifiant métier", ""),
                "Champ":              a.get("Champ", ""),
                "Type d'anomalie":    a.get("Type d'anomalie", ""),
                "Sévérité":           _sev_icon.get(a.get("Sévérité", ""), a.get("Sévérité", "")),
                "Classification":     _cls_label.get(a.get("Classification", ""), ""),
                "Message":            a.get("Message", ""),
                "Valeur source":      a.get("Valeur", ""),
                "🤖 Suggestion IA":    _ia_display,
                "Nouvelle valeur":    _nouvelle,
            }
            return out

        edit_rows = [_row(a) for a in filtered]

        # RÉVISÉ (26/08/2026) — même plafond que l'ancien tableau de
        # correction (perf/stabilité WebSocket, voir historique) — appliqué
        # maintenant au tableau fusionné dans son ensemble. Les lignes hors
        # plafond gardent leur comportement par défaut (calculé ci-dessus,
        # overrides de propagation compris) et sont quand même incluses
        # dans le fichier généré.
        _MAX_EDITABLE_ROWS = 400
        _overflow_rows = edit_rows[_MAX_EDITABLE_ROWS:]
        edit_rows_display = edit_rows[:_MAX_EDITABLE_ROWS]

        if _overflow_rows:
            st.caption(
                f"⚠️ {len(_overflow_rows)} ligne(s) supplémentaire(s) non affichée(s) ci-dessous "
                f"(volume trop important pour l'édition interactive) — incluses dans le fichier "
                f"généré avec leur valeur par défaut, non modifiables dans ce run."
            )

        _column_config = {
            "Appliquer": st.column_config.CheckboxColumn(help="Cocher pour inclure cette ligne dans le fichier généré"),
            "Nouvelle valeur": st.column_config.TextColumn(help="Modifiable — tapez la valeur correcte pour cette cellule"),
        }
        edited = st.data_editor(
            pd.DataFrame(edit_rows_display),
            use_container_width=True,
            hide_index=True,
            height=min(450, 50 + len(edit_rows_display) * 35),
            disabled=[
                "Onglet", "Ligne", "Identifiant métier", "Champ", "Type d'anomalie",
                "Sévérité", "Classification", "Message", "Valeur source", "🤖 Suggestion IA",
            ],
            column_config=_column_config,
            key=f"merged_editor_{sn}_{st.session_state[_editor_gen_key]}",
        )

        if csel3 is not None:
            with csel3:
                if st.button("🔁 Propager", key=f"btn_propagate_{sn}",
                             help="Applique chaque correction saisie à toutes les autres lignes ayant la même valeur source dans le même champ"):
                    # RÉVISÉ (27/08/2026, jour de la démo) — bug évité : la
                    # comparaison utilisait "Correction suggérée", colonne
                    # retirée de l'affichage (fusionnée dans "🤖 Suggestion IA",
                    # qui inclut un "(X%)" que "Nouvelle valeur" n'a jamais —
                    # comparer directement aurait détecté un "changement" sur
                    # CHAQUE ligne, même non modifiée). Comparaison désormais
                    # contre la valeur ORIGINALE de "Nouvelle valeur" (avant
                    # toute édition), qui reflète fidèlement ce qui était
                    # pré-rempli par défaut.
                    _original_nv_by_key = {
                        (r["Ligne"], r["Champ"]): r["Nouvelle valeur"] for r in edit_rows_display
                    }
                    _new_overrides = dict(_propagate_overrides)
                    _propagated = 0
                    for _, row in edited.iterrows():
                        _nv = str(row["Nouvelle valeur"]).strip()
                        _orig_nv = str(_original_nv_by_key.get((row["Ligne"], row["Champ"]), "")).strip()
                        if _nv and _nv != _orig_nv:
                            _key = (row["Champ"], str(row["Valeur source"]).strip())
                            _new_overrides[_key] = _nv
                    # Compte les lignes qui vont effectivement changer au prochain rerun
                    for r in edit_rows:
                        _key = (r["Champ"], str(r["Valeur source"]).strip())
                        if _key in _new_overrides and str(r["Nouvelle valeur"]).strip() != _new_overrides[_key]:
                            _propagated += 1
                    st.session_state[f"_propagate_overrides_{sn}"] = _new_overrides
                    st.session_state[_editor_gen_key] += 1
                    # RÉVISÉ (26/08/2026, 2e passe) — bug trouvé : st.success/
                    # st.info juste avant st.rerun() ne s'affichaient jamais (le
                    # rerun efface le rendu en cours avant qu'il atteigne
                    # l'écran — même piège déjà rencontré cette semaine).
                    # Message persisté en session_state, affiché au prochain
                    # rendu à la place.
                    if _propagated:
                        st.session_state[f"_propagate_feedback_{sn}"] = ("success", f"✅ {_propagated} ligne(s) mise(s) à jour avec la même correction.")
                    else:
                        st.session_state[f"_propagate_feedback_{sn}"] = ("info", "ℹ️ Rien à propager — soit aucune autre ligne ne partage la même valeur source dans ce champ, soit toutes l'ont déjà.")
                    st.rerun()

        cgen1, cgen2, cgen3 = st.columns([1, 1, 2])
        with cgen1:
            gen_clicked = st.button("0️⃣ Générer le fichier corrigé", type="primary", use_container_width=True, key=f"gen_{sn}")

        if gen_clicked:
            original_bytes = st.session_state.get("original_file_bytes")
            if not original_bytes:
                st.error("❌ Fichier original introuvable en mémoire — remontez à l'étape 2.")
            else:
                selected = edited[
                    (edited["Appliquer"] == True)
                    & (edited["Nouvelle valeur"].astype(str).str.strip() != "")
                ]
                corrections = [
                    {"sheet": row["Onglet"], "excel_row": int(row["Ligne"]), "column_name": row["Champ"], "new_value": row["Nouvelle valeur"]}
                    for _, row in selected.iterrows()
                ]
                corrections += [
                    {"sheet": r["Onglet"], "excel_row": int(r["Ligne"]), "column_name": r["Champ"], "new_value": r["Nouvelle valeur"]}
                    for r in _overflow_rows
                    if r["Appliquer"] and str(r["Nouvelle valeur"]).strip()
                ]
                try:
                    generated_bytes = apply_corrections(original_bytes, corrections) if corrections else original_bytes
                    _guid_cols_by_sheet: dict[str, set[str]] | None = None
                    _early_key = f"early_axeab_{cfg.get('pkg_code', '')}_{cfg.get('company_id', '')}_{cfg.get('file_name', '')}"
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
                            _guid_cols_by_sheet = None
                    generated_bytes = clear_id_reference_columns(generated_bytes, guid_column_names=_guid_cols_by_sheet)
                    st.session_state["generated_file_bytes"] = generated_bytes
                    st.session_state["generated_file_name"] = f"CORRIGE_{cfg.get('file_name', 'fichier.xlsx')}"
                    # AJOUTÉ (27/08/2026) — demande Rami : une nouvelle
                    # génération de fichier doit repartir sur un état
                    # d'intégration BC neuf — sinon un ancien message
                    # d'erreur ("BC a rejeté l'import...") d'un test
                    # précédent restait affiché malgré un fichier régénéré
                    # entre-temps, laissant croire que le nouveau fichier
                    # posait le même problème.
                    st.session_state[f"bc_integration_{sn}"] = {"stage": "idle"}
                    st.success(f"✅ Fichier généré — {len(corrections)} correction(s) appliquée(s).")
                except Exception as e:
                    st.error(f"❌ Erreur lors de la génération : {e}")

        if st.session_state.get("generated_file_bytes"):
            with cgen2:
                st.download_button(
                    "⬇️ Télécharger le fichier corrigé",
                    data=st.session_state["generated_file_bytes"],
                    file_name=st.session_state.get("generated_file_name", "fichier_corrige.xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_generated_file",
                    use_container_width=True,
                )

            # AJOUTÉ (27/08/2026) — demande Rami, point 2 des chantiers
            # post-démo : intégration directe du fichier corrigé dans BC,
            # pour que le client puisse le faire sans dépendre du
            # consultant. Réutilise run_bc_import_check (créer le package
            # si besoin, déposer le fichier CORRIGÉ, importer sans écrire —
            # "Valider"). L'étape "Appliquer" (écriture réelle, irréversible
            # côté BC) est volontairement séparée et exige une confirmation
            # explicite avant de se déclencher.
            st.markdown("---")
            st.markdown('<div class="step-header">🚀 Intégrer directement dans BC</div>', unsafe_allow_html=True)

            _integ_key = f"bc_integration_{sn}"
            if _integ_key not in st.session_state:
                st.session_state[_integ_key] = {"stage": "idle"}
            _integ = st.session_state[_integ_key]

            if _integ["stage"] in ("idle", "imported"):
                _integ_btn_col1, _ = st.columns([1, 3])
                with _integ_btn_col1:
                    _btn1_clicked = st.button("1️⃣ Vérifier avant intégration", key=f"btn_integ_check_{sn}", use_container_width=True)
                if _btn1_clicked:
                    with st.spinner("Vérification BC en cours..."):
                        try:
                            _p = get_profile_by_code(cfg.get("client_code", ""))
                            _tid = _p.get("bc_tenant_id", "").strip()
                            _cid = _p.get("bc_client_id", "").strip()
                            _cs  = _p.get("bc_client_secret", "").strip()
                            _env = _p.get("bc_environment", "").strip()
                            if not all([_tid, _cid, _cs, _env, cfg.get("company_id")]):
                                st.session_state[_integ_key] = {"stage": "idle", "error": "Credentials BC incomplets pour ce profil."}
                            else:
                                _tok = get_access_token(_tid, _cid, _cs)
                                _pkg_code_integ = f"QC-{cfg.get('session_name', 'temp')}"[:20]
                                _res = run_bc_import_check(
                                    _tid, _env, cfg["company_id"], _tok,
                                    _pkg_code_integ, f"Intégration QC — {cfg.get('session_name', '')}",
                                    st.session_state["generated_file_bytes"],
                                )
                                if _res.get("success"):
                                    st.session_state[_integ_key] = {
                                        "stage": "imported",
                                        "package_id": _res["package_id"],
                                        "package_code": _pkg_code_integ,
                                        "status": _res.get("status"),
                                        "creds": (_tid, _env, cfg["company_id"], _tok),
                                    }
                                    # AJOUTÉ (27/08/2026) — demande Rami : un
                                    # indicateur clair de fin de vérification —
                                    # le sondage BC peut prendre jusqu'à 20s,
                                    # un simple retour de spinner ne suffisait
                                    # pas à signaler "c'est fini".
                                    st.toast("✅ Vérification BC terminée.")
                                else:
                                    st.session_state[_integ_key] = {"stage": "idle", "error": _res.get("error", "")}
                                    st.toast("⚠️ Vérification BC terminée — erreur détectée.")
                        except Exception as _integ_exc:
                            st.session_state[_integ_key] = {"stage": "idle", "error": f"{type(_integ_exc).__name__} : {_integ_exc}"}
                            st.toast("⚠️ Vérification BC terminée — erreur technique.")

            _integ = st.session_state[_integ_key]
            if _integ.get("error"):
                st.markdown(f'<div class="card-major">🔴 {_integ["error"]}</div>', unsafe_allow_html=True)

            if _integ["stage"] == "imported":
                _integ_status = _integ.get("status") or {}
                _import_status_str = str(_integ_status.get("importStatus", "")).lower()
                _nb_err_integ = _integ_status.get("numberOfErrors", "?")
                # RÉVISÉ (27/08/2026, 2e passe) — bug trouvé : "Error" tombait
                # dans le même message que "InProgress" ("pas encore
                # confirmé... relance dans quelques secondes"), alors que
                # "Error" est un vrai échec BC (relancer ne sert à rien) —
                # message trompeur. Distingue maintenant clairement les deux
                # cas, et affiche le vrai message d'erreur BC (importError)
                # quand il y en a un, au lieu de suggérer d'attendre.
                if _import_status_str == "error":
                    st.markdown(
                        f'<div class="card-major">🔴 BC a rejeté l\'import — '
                        f'{_integ_status.get("importError") or "aucun détail fourni par BC."}</div>',
                        unsafe_allow_html=True,
                    )
                elif _import_status_str != "completed":
                    st.markdown(
                        f'<div class="card-minor">⏳ BC n\'a pas encore confirmé la fin de l\'import '
                        f'(statut actuel : {_integ_status.get("importStatus", "inconnu")}) — relance '
                        f'"Vérifier avant intégration" dans quelques secondes.</div>',
                        unsafe_allow_html=True,
                    )
                elif _nb_err_integ == 0:
                    st.markdown('<div class="card-ref">✅ 0 erreur — le fichier peut être appliqué dans BC.</div>', unsafe_allow_html=True)
                    st.warning("⚠️ L'étape suivante écrit réellement les données dans Business Central — action irréversible.")
                    _confirm = st.checkbox("Je confirme vouloir intégrer ces données dans Business Central", key=f"confirm_apply_{sn}")
                    _btn2_clicked = False
                    if _confirm:
                        _integ_btn_col2, _ = st.columns([1, 3])
                        with _integ_btn_col2:
                            _btn2_clicked = st.button("2️⃣ Appliquer dans BC", type="primary", key=f"btn_integ_apply_{sn}", use_container_width=True)
                    if _btn2_clicked:
                        with st.spinner("Intégration dans BC en cours..."):
                            try:
                                _tid, _env, _company_id, _tok = _integ["creds"]
                                apply_configuration_package(_tid, _env, _company_id, _tok, _integ["package_id"])

                                # AJOUTÉ (27/08/2026) — après une intégration réussie :
                                # marque automatiquement la session comme "Terminée"
                                # (confirmé par Rami) et met à jour la mémoire
                                # inter-sessions pour la table concernée si c'est
                                # une session fille (même règle que la sauvegarde
                                # complète — voir plus bas dans ce fichier).
                                _sid = st.session_state.get("resumed_session_id") or st.session_state.get("saved_session_id")
                                if _sid:
                                    try:
                                        update_session(_sid, {"status": "Terminée"})
                                    except Exception:
                                        pass
                                _tid_mem = cfg.get("table_id")
                                if _tid_mem:
                                    try:
                                        from app.core.bc_excel_processor import extract_key_values_by_table
                                        from app.db.metadata_db import save_pending_codes
                                        _codes_all = extract_key_values_by_table(st.session_state["generated_file_bytes"])
                                        _codes_scoped = {k: v for k, v in _codes_all.items() if k == _tid_mem}
                                        if _codes_scoped and _sid:
                                            save_pending_codes(
                                                session_id=_sid, profile_code=cfg.get("client_code", ""),
                                                company_id=cfg.get("company_id", ""), codes_by_table=_codes_scoped,
                                            )
                                    except Exception:
                                        pass

                                st.session_state[_integ_key] = {"stage": "applied"}
                                st.success("✅ Données intégrées dans Business Central avec succès. Session marquée « Terminée ».")
                            except Exception as _apply_exc:
                                st.error(f"❌ Échec de l'intégration : {_apply_exc}")
                else:
                    st.markdown(
                        f'<div class="card-major">🔴 {_nb_err_integ} erreur(s) détectée(s) par BC sur le fichier corrigé — '
                        f'corrige-les avant de pouvoir intégrer.</div>',
                        unsafe_allow_html=True,
                    )

            if _integ["stage"] == "applied":
                st.markdown('<div class="card-ref">✅ Intégration terminée.</div>', unsafe_allow_html=True)

    if info_anomalies:
        st.markdown("---")
        st.markdown("**ℹ️ Champs non vérifiables (référence absente) :**")
        for a in info_anomalies:
            st.markdown(
                f'<div class="card-info"><span class="tag tag-info">INFO</span>'
                f'<b>{a.get("Champ", "")}</b> — {a.get("Message", "")}</div>',
                unsafe_allow_html=True
            )

    st.session_state["prerequisites_report"] = build_prerequisites_report(
        [a for a in all_anomalies if a.get("Ligne", 0) > 0],
        profile_code=cfg.get("client_code", ""), company_id=cfg.get("company_id", ""),
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
              # AJOUTÉ (23/08/2026) — marqueur de reprise (voir bouton
              # "▶️ Reprendre") : un "Recommencer" explicite doit repartir
              # sur une session neuve, jamais continuer à écraser celle
              # qui avait été reprise.
              "resumed_session_id",
              # AJOUTÉ (24/08/2026) — même piège Streamlit que ses_name_input
              # (index= ignoré une fois la clé de widget déjà instanciée) :
              # sans ce nettoyage, le sélecteur de société Étape 1 garde la
              # société précédemment choisie après un "Recommencer" ou une
              # reprise, au lieu de refléter cfg["company_id"] — cause
              # confirmée d'un vidage de cache visant la mauvaise société
              # (24/08, diagnostic Section analytique/table 349).
              "ses_company_sel", "ses_pkg_sel",
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


def _quick_save_session(cfg: dict, status: str = "Nouvelle") -> None:
    """AJOUTÉ (23/08/2026) — demande Rami : pouvoir sauvegarder à n'importe
    quelle étape (2 ou 3), pas seulement à la fin (Étape 4, déjà existante,
    non touchée ici). Sauvegarde avec les infos disponibles à ce stade —
    PAS de détection racine/fille (dépend de l'analyse complète, non faite
    ici) : toujours en racine par défaut, SAUF si une session a été reprise
    (session_state.resumed_session_id) — dans ce cas l'architecture mère/
    fille déjà enregistrée est conservée telle quelle, pas réinitialisée.

    RÉVISÉ (23/08/2026, 2e passe) — mise à jour en place si la session en
    cours a été reprise via "▶️ Reprendre" (voir resumed_session_id) : sans
    ça, reprendre une session puis la sauvegarder créait une NOUVELLE
    session à chaque fois (3 sessions pour une seule modifiée deux fois,
    signalé par Rami)."""
    original_bytes  = st.session_state.get("original_file_bytes")
    _resumed_id     = st.session_state.get("resumed_session_id")
    _payload = {
        "session_name":       cfg.get("session_name", ""),
        "profile_code":       cfg.get("client_code", ""),
        "file_name":          cfg.get("file_name", ""),
        "notes":              cfg.get("notes", ""),
        "date_controle":      cfg.get("date_controle", ""),
        "company_id":         cfg.get("company_id", ""),
        "company_name":       cfg.get("company_name", ""),
        "status":             status,
        "total_anomalies":    0,
        "major_anomalies":    0,
        "minor_anomalies":    0,
        "original_file_b64": (
            base64.b64encode(original_bytes).decode("ascii") if original_bytes else ""
        ),
        "generated_file_b64":  "",
        "generated_file_name": "",
        "prerequisites_report": [],
        "table_id":            cfg.get("table_id"),
        "parent_session_id":   cfg.get("parent_session_id"),
        "is_root":             cfg.get("is_root", True),
        "pkg_code":            cfg.get("pkg_code", ""),
    }
    if _resumed_id:
        ok, res = update_session(_resumed_id, {**_payload, "name": _payload["session_name"]})
        res = _resumed_id if ok else res
    else:
        ok, res = save_session(_payload)
    if ok:
        # RÉVISÉ (26/08/2026) — demande Rami : "pourquoi c'est moi qui dois
        # supprimer manuellement" — la vraie cause n'était pas l'ancienneté
        # des sessions, mais le fait qu'un simple CHECKPOINT (Étape 2/3, où
        # on ne sait pas encore si la session sera racine ou fille — ce
        # choix ne se fait qu'à l'Étape 4) alimentait déjà la mémoire pour
        # TOUS les onglets du fichier. Un fichier Stock a naturellement un
        # onglet "27 Article" (son sujet principal, pas un prérequis pour
        # quelqu'un d'autre) — le déclarer "en attente d'intégration"
        # n'avait jamais de sens ici. Un checkpoint ne contribue plus du
        # tout à la mémoire inter-sessions ; seule la sauvegarde complète
        # (Étape 4, qui connaît le rôle racine/fille et la table précise)
        # le fait désormais, et seulement pour la table concernée — voir
        # plus bas dans ce fichier, bloc "💾 Sauvegarder la session".
        _mem_warning = None

        _saved_name = cfg.get("session_name", "")
        reset_session()
        st.session_state["_just_saved_banner"] = (
            f"✅ Session « {_saved_name} » enregistrée (checkpoint). "
            f"Retrouve-la dans « 📋 Mes sessions » — utilise « ▶️ Reprendre » pour continuer plus tard."
        )
        if _mem_warning and is_consultant():
            st.session_state["_just_saved_mem_warning"] = f"⚠️ {_mem_warning}"
        st.rerun()
    else:
        st.error(f"❌ {res}")


# ════════════════════════════════════════════════════════════════════════════
# PAGE
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"# 📁 Sessions Intégration — {active_client_name}")
st.markdown("---")

# RÉVISÉ (23/08/2026) — remis "Nouvelle session" en premier : le mettre en
# 2e position (pour ouvrir par défaut sur "Mes sessions") cassait la
# navigation pendant le remplissage d'une session — st.tabs() retombe sur
# le PREMIER onglet à chaque st.rerun() (déclenché à chaque changement
# d'étape), donc l'utilisateur se retrouvait éjecté vers "Mes sessions" à
# chaque clic "Suivant". La stabilité pendant la création (usage bien plus
# fréquent) prime sur l'onglet par défaut au tout premier chargement de
# la page.
tab_main, tab_ses = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

with tab_main:
    for key, default in [
        ("step", 1), ("config", {}), ("parse_result", None), ("validation", None),
        ("merged_result", None), ("axe_c_result", None), ("saved_session_id", None),
        ("original_file_bytes", None), ("generated_file_bytes", None),
        ("generated_file_name", None), ("prerequisites_report", None),
        ("level_pkg_resolve", {}), ("resumed_session_id", None),
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
        # AJOUTÉ (23/08/2026) — demande Rami : après une sauvegarde réussie,
        # repartir directement sur un formulaire neuf (au lieu de rester sur
        # l'Étape 4 jusqu'à un clic manuel sur "Recommencer"). Bannière de
        # confirmation affichée une seule fois, puis nettoyée.
        _just_saved = st.session_state.pop("_just_saved_banner", None)
        if _just_saved:
            st.success(_just_saved)
        _just_saved_mem = st.session_state.pop("_just_saved_mem_warning", None)
        if _just_saved_mem:
            st.warning(_just_saved_mem)
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
                    "🏢 Société BC *", _names, index=None,
                    placeholder="Choisir une société...", key="ses_company_sel"
                )
                sel_company_id = _company_opts.get(sel_company_name) if sel_company_name else None
            else:
                st.info("Aucune société BC disponible.")
                sel_company_id, sel_company_name = _default_cid, _default_cname

            sel_pkg_code = active_pkg_code
            sel_pkg_name = active_pkg_name

            if not active_pkg_code and sel_company_id:
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
                        index=None, placeholder="Choisir un package...",
                        key="ses_pkg_sel",
                    )
                    sel_pkg_code, sel_pkg_name = _pkg_opts.get(_pkg_choice, ("", ""))
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

            # DÉPLACÉ (22/08/2026) depuis l'Étape 3 : plus logique à la
            # création de session qu'au milieu de l'analyse des prérequis.
            # Vide UNIQUEMENT bc_metadata_cache (entity_type='reference') —
            # n'a AUCUN effet sur la mémoire inter-sessions
            # (session_pending_codes), mécanisme complètement séparé.
            # Label raccourci + tooltip (22/08/2026) : le nom complet
            # précédent ("Vider le cache des valeurs de référence
            # (Supabase)") était trop long pour un bouton pleine largeur,
            # l'explication technique est déplacée dans le `help=`.
            if is_consultant():
                with st.container(border=True):
                    st.caption("🛠️ Outil consultant")
                    if st.button(
                        "🔄 Vider le cache",
                        key="btn_clear_ref_cache",
                        use_container_width=True,
                        help=(
                            "Force le rechargement des valeurs de référence BC "
                            "(groupes comptables, devises, catégories...) depuis "
                            "Business Central au prochain contrôle. À utiliser si "
                            "des codes créés récemment dans BC ne sont pas encore "
                            "reconnus par l'outil."
                        ),
                    ):
                        try:
                            ok, err = clear_reference_cache(
                                profile_code = active_client,
                                company_id   = sel_company_id,
                            )
                            if ok:
                                st.success("Cache vidé — sera rechargé depuis BC au prochain contrôle.")
                            else:
                                st.error(f"Échec du vidage : {err}")
                        except Exception as e:
                            st.error(f"Échec du vidage : {e}")
                        st.rerun()

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
                # AJOUTÉ (23/08/2026) — demande Rami : possibilité de
                # sauvegarder à cette étape aussi (checkpoint), pas
                # seulement à la toute fin.
                # RÉVISÉ (27/08/2026, 5e passe) — bouton compact au lieu de
                # pleine largeur pour un texte court.
                _qs2_col, _ = st.columns([1.8, 3])
                with _qs2_col:
                    if st.button("💾 Enregistrer maintenant (checkpoint)", key="quicksave_step2", use_container_width=True):
                        _quick_save_session(st.session_state.config, status="Nouvelle")
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
        # AJOUTÉ (23/08/2026) — bannière affichée une fois après un
        # "▶️ Reprendre" depuis "Mes sessions" (voir plus bas dans le
        # fichier) — Streamlit ne permet pas de changer l'onglet actif par
        # le code, donc ce message guide l'utilisateur vers l'onglet à
        # ouvrir manuellement.
        _resume_banner = st.session_state.pop("_resume_banner", None)
        if _resume_banner:
            st.info(_resume_banner)
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
            #
            # RÉVISÉ (23/08/2026) — le bouton dédié (d'abord pleine largeur,
            # puis icône ⚙️ isolée) a été retiré : visuellement à part, sans
            # rapport clair avec le reste de l'écran ("fait amateur", retour
            # Rami). Fusionné dans "🔄 Revérifier" ci-dessous à la place —
            # recharge level_config à chaque clic, coût Supabase négligeable
            # (petite table de référence), et le consultant obtient le même
            # résultat sans bouton séparé à comprendre.

            # AJOUTÉ (19/08/2026) : get_reference_values_by_table_id() n'a
            # aucune expiration — une entrée en cache reste utilisée
            # indéfiniment même si BC a changé depuis (ex. 251 Groupe compta.
            # produit signalé "introuvable" par le Trigger Simulator alors
            # que les groupes existent bien dans BC, si le cache date d'avant
            # leur création). Bouton consultant, même logique que celui de
            # level_config ci-dessus — vidage manuel à la demande, pas de
            # rafraîchissement automatique.
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
                        client_code = cfg.get("client_code", "")
                        _exec_plan = get_execution_plan(
                            profile_code=client_code,
                            company_id=cfg.get("company_id", ""),
                            package_code=cfg.get("pkg_code", ""),
                        )

                        _meta_loader = MetadataLoader(client_code, cfg.get("company_id", ""))
                        _sim_ctx     = SimulationContext()
                        with st.spinner("⏳ Analyse des prérequis BC..."):
                            _axe_a = validate_file_axe_a(pr, execution_plan=_exec_plan)

                            _axe_b = validate_file_axe_b(
                                pr,
                                profile_code    = client_code,
                                company_id      = cfg.get("company_id", ""),
                                sim_context     = _sim_ctx,
                                metadata_loader = _meta_loader,
                                execution_plan  = _exec_plan,
                            )
                        # Mis en cache pour réutilisation au clic "Lancer l'analyse" —
                        # évite de relancer Axe A/Axe B une seconde fois pour rien.
                        st.session_state[_early_axeb_key] = {
                            "axe_a": _axe_a, "axe_b": _axe_b, "exec_plan": _exec_plan,
                        }
                        _early_merged = merge_results(_axe_a, _axe_b, {"available": False}, parse_result=pr)
                        _real = [a for a in _early_merged.get("all_anomalies", []) if a.get("Ligne", 0) > 0]
                        # AJOUTÉ (27/08/2026, 2e passe) — demande Rami, point 3 :
                        # le nombre affiché avant la roadmap doit être celui
                        # détecté par L'OUTIL LUI-MÊME (déjà calculé ici pour
                        # construire la roadmap), pas un appel BC en direct à
                        # chaque fois — la comparaison avec le nombre BC réel
                        # se fait séparément, à la demande (bouton dédié plus
                        # bas). Mis en cache pour survivre aux reruns suivants
                        # de l'Étape 3 sans recalcul.
                        st.session_state[f"_anomaly_count_{_roadmap_key}"] = len(_real)
                        _prereqs = build_prerequisites_report(
                            _real, profile_code=client_code, company_id=cfg.get("company_id", "")
                        )
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
                        _prereqs = _prereqs + _gl_anomalies
                        # build_roadmap_from_prereqs regroupe désormais génériquement
                        # les lignes de _prereqs par table et les attache en
                        # sub_anomalies à CHAQUE niveau concerné (pas seulement GL
                        # Account) — demandé par Rami le 27/07 : plusieurs tables
                        # prérequis doivent chacune afficher leur propre détail.
                        #
                        # AJOUTÉ (19/08/2026) — previous_table_ids : garde affichées
                        # (cochées ✓ une fois propres) les tables déjà vues dans CETTE
                        # session de travail, au lieu qu'elles disparaissent purement
                        # et simplement dès qu'elles n'ont plus d'anomalie détectée.
                        # Repli sur set() si aucun roadmap précédent en mémoire (1er
                        # scan) — comportement inchangé dans ce cas.
                        _prev_roadmap = st.session_state.get(_roadmap_key)
                        _previous_table_ids = (
                            {e.level_info.table_id for e in _prev_roadmap} if _prev_roadmap else set()
                        )
                        # RETIRÉ (26/08/2026, 2e passe) — _file_referenced_table_ids
                        # (25/08) causait du bruit : une trentaine de tables sans
                        # aucune anomalie réelle remontaient dans la roadmap
                        # (simple relation de champ théorique, jamais une vraie
                        # valeur invalide). Voir le commentaire dans
                        # build_roadmap_from_prereqs (integration_levels.py) pour
                        # le détail complet — confirmé par comparaison directe
                        # avec les vraies erreurs BC (Rami, 26/08).
                        #
                        # AJOUTÉ (26/08/2026, mercredi) — demande Rami : niveau
                        # calculé dynamiquement depuis le graphe réel de
                        # dépendances du fichier (fields_ref), au lieu d'une
                        # classification maintenue à la main table par table.
                        # Voir compute_dynamic_levels() pour le détail complet
                        # et la validation sur MDD-Comptabilité. Ce calcul reste
                        # valable et utile — seule l'INCLUSION des tables (ci-
                        # dessus) est revenue à l'ancien critère (anomalie réelle
                        # ou déjà vue), le NIVEAU continue d'être calculé pour
                        # toute table qui, par ailleurs, qualifie déjà.
                        _dynamic_levels = compute_dynamic_levels(_exec_plan.fields_ref, forced_root_table_id=15)
                        # RÉVISÉ (23/08/2026) — demande Rami : forcer TOUTES les
                        # tables déjà résolues à rester cochées ✓ en permanence,
                        # y compris à travers un "▶️ Reprendre" (qui vide
                        # session_state, donc perd _prev_roadmap ci-dessus —
                        # persisté séparément dans bc_metadata_cache, voir
                        # save/get_roadmap_table_history).
                        _persisted_table_ids = get_roadmap_table_history(
                            client_code, cfg.get("company_id", ""), cfg.get("pkg_code", "")
                        )
                        _previous_table_ids |= _persisted_table_ids
                        st.session_state[_roadmap_key] = build_roadmap_from_prereqs(
                            _prereqs, _level_cfg, previous_table_ids=_previous_table_ids,
                            profile_code=client_code, company_id=cfg.get("company_id", ""),
                            dynamic_levels=_dynamic_levels,
                        )
                        _current_table_ids = {e.level_info.table_id for e in st.session_state[_roadmap_key]}
                        if _current_table_ids - _persisted_table_ids:
                            save_roadmap_table_history(
                                client_code, cfg.get("company_id", ""), cfg.get("pkg_code", ""),
                                _persisted_table_ids | _current_table_ids,
                            )
                    except Exception as e:
                        st.session_state[_roadmap_key] = []
                        st.warning(f"⚠️ Détection des niveaux impossible pour l'instant : {e}")

                _roadmap = st.session_state[_roadmap_key]

                def _do_revalidate_roadmap():
                    with st.spinner("Vérification BC en cours..."):
                        # AJOUTÉ (23/08/2026) — fusionné depuis l'ancien bouton
                        # séparé "Recharger classification niveaux" (retiré, cf.
                        # commentaire plus haut) : recharge level_config à chaque
                        # clic, pour qu'une modif SQL faite directement dans
                        # Supabase soit prise en compte sans jamais avoir besoin
                        # d'un F5 complet. Coût négligeable (petite table de
                        # référence, un seul SELECT).
                        try:
                            st.session_state.level_config = load_level_config(get_supabase_client())
                        except Exception:
                            pass  # repli silencieux sur la classification déjà en mémoire

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
                            # RÉVISÉ (26/08/2026) — bug trouvé : la session en
                            # cours (si déjà sauvegardée une première fois —
                            # checkpoint ou complète) n'était jamais exclue de
                            # sa propre vérification mémoire inter-sessions.
                            # Résultat : ses propres codes fraîchement extraits
                            # à la sauvegarde se comptaient comme une
                            # "confirmation externe" — la session se validait
                            # elle-même en boucle (cas réel : Article validé en
                            # mémoire 🟡 sans aucune autre session ni BC réel
                            # derrière).
                            _current_session_id = (
                                st.session_state.get("resumed_session_id")
                                or st.session_state.get("saved_session_id")
                            )
                            st.session_state[_roadmap_key] = refresh_roadmap(
                                cfg["client_code"], cfg["company_id"], _roadmap,
                                gl_account_check=_gl_check,
                                exclude_session_id=_current_session_id,
                            )
                        except Exception as _refresh_e:
                            st.error(f"Erreur lors de la revérification : {type(_refresh_e).__name__}: {_refresh_e}")
                            st.stop()
                    st.rerun()

                if _roadmap:
                    _total   = len(_roadmap)
                    _done    = sum(1 for e in _roadmap if e.status == "validated")
                    _pct     = int(100 * _done / _total) if _total else 0

                    # RÉVISÉ (27/08/2026, 4e passe) — demande Rami : "pas beau,
                    # 2 boutons l'un sur l'autre, le nombre est trop petit" —
                    # fusion de l'ancien bloc "Prérequis BC détectés" (avec son
                    # bouton Revérifier) et du bloc "nombre d'anomalies" (avec
                    # son bouton Comparer avec BC) en UNE SEULE carte : gros
                    # chiffre à gauche, les deux boutons côte à côte à droite
                    # (plus jamais empilés verticalement).
                    _anomaly_count = st.session_state.get(f"_anomaly_count_{_roadmap_key}")
                    with st.container(border=True):
                        _hcol1, _hcol2, _hcol3 = st.columns([3, 1.5, 1.5])
                        with _hcol1:
                            if _anomaly_count is not None:
                                _num_color = "#0F6E56" if _anomaly_count == 0 else "#993C1D"
                                st.markdown(
                                    f'<div class="anomaly-big-num" style="color:{_num_color}">{_anomaly_count}</div>'
                                    f'<div class="anomaly-big-lbl">anomalie(s) détectée(s) par l\'outil sur ce fichier</div>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown('<div class="step-header">🧱 Prérequis BC détectés</div>', unsafe_allow_html=True)
                        with _hcol2:
                            if st.button("🔄 Revérifier", key="btn_refresh_levels", use_container_width=True):
                                _do_revalidate_roadmap()
                        with _hcol3:
                            _cmp_clicked = st.button("🔎 Comparer avec BC", key="btn_bc_check", use_container_width=True)

                        _bc_check_key = f"bc_check_{_roadmap_key}"
                        if _cmp_clicked:
                            with st.spinner("Vérification BC en cours..."):
                                _original_bytes_e3 = st.session_state.get("original_file_bytes")
                                try:
                                    _p = get_profile_by_code(active_client)
                                    _tid = _p.get("bc_tenant_id", "").strip()
                                    _cid = _p.get("bc_client_id", "").strip()
                                    _cs  = _p.get("bc_client_secret", "").strip()
                                    _env = _p.get("bc_environment", "").strip()
                                    if not all([_tid, _cid, _cs, _env, cfg.get("company_id"), _original_bytes_e3]):
                                        st.session_state[_bc_check_key] = {"success": False, "error": "Credentials BC ou fichier original manquants."}
                                    else:
                                        _tok = get_access_token(_tid, _cid, _cs)
                                        _pkg_code_check = f"QC-{cfg.get('session_name', 'temp')}"[:20]
                                        st.session_state[_bc_check_key] = run_bc_import_check(
                                            _tid, _env, cfg["company_id"], _tok,
                                            _pkg_code_check, f"Vérification QC — {cfg.get('session_name', '')}",
                                            _original_bytes_e3,
                                        )
                                except Exception as _bc_exc:
                                    st.session_state[_bc_check_key] = {"success": False, "error": f"{type(_bc_exc).__name__} : {_bc_exc}"}

                        _bc_check = st.session_state.get(_bc_check_key)
                        if _bc_check and _anomaly_count is not None:
                            if not _bc_check.get("success"):
                                st.caption(f"⚠️ {_bc_check.get('error', '')}")
                            else:
                                _nb_err_bc = (_bc_check.get("status") or {}).get("numberOfErrors", "?")
                                _match = _nb_err_bc == _anomaly_count
                                _pill_bg  = "#E1F5EE" if _match else "#FAEEDA"
                                _pill_fg  = "#0F6E56" if _match else "#854F0B"
                                _icon = "✅" if _match else "⚠️"
                                st.markdown(
                                    f'<span class="anomaly-bc-pill" style="background:{_pill_bg};color:{_pill_fg}">'
                                    f'{_icon} BC réel : {_nb_err_bc}</span>',
                                    unsafe_allow_html=True,
                                )

                        st.markdown(f"**Progression — {_pct}%**")
                        st.progress(_pct / 100)

                        try:
                            # RÉVISÉ (25/08/2026) — demande Rami : un vrai groupe visuel
                            # "COMPTABILITÉ" (en-tête + tables regroupées dessous), pas
                            # juste un tag entre parenthèses collé au libellé. Les tables
                            # d'un même sub_level peuvent être sur des niveaux numériques
                            # différents (ex. Comptabilité : -2 à 1, pour respecter le vrai
                            # ordre de dépendance Microsoft — 323/324 avant 250/251 avant
                            # Compte général avant 92/93/94) — donc un simple tri
                            # (niveau, sub_level) ne les garde PAS contigus si d'autres
                            # tables sans sub_level partagent ces mêmes niveaux. On
                            # partitionne explicitement : chaque sub_level devient UN bloc
                            # contigu (trié par niveau/table_id en interne), affiché avant
                            # les entrées sans sub_level (comportement inchangé pour elles).
                            _grouped: dict[str, list] = {}
                            _ungrouped: list = []
                            for _e in _roadmap:
                                _sl = _e.level_info.sub_level
                                if _sl:
                                    _grouped.setdefault(_sl, []).append(_e)
                                else:
                                    _ungrouped.append(_e)

                            def _render_level_card(_entry, _show_sub_level_tag: bool = True, _nested: bool = False):
                                _unlocked = is_level_unlocked(_entry.level_info.level, _roadmap)
                                _label = f"{_entry.level_info.table_id} — {_entry.level_info.table_name}"
                                if _show_sub_level_tag and _entry.level_info.sub_level:
                                    _label = f"{_label} ({_entry.level_info.sub_level})"
                                _memory_sub = ""

                                if _entry.status == "validated":
                                    # AJOUTÉ (20/08/2026) — distinction honnête : le cercle
                                    # vert (✓) reste réservé au confirmé BC réel ; un statut
                                    # validé uniquement via la mémoire d'une autre session
                                    # affiche un repère orange (🟡) distinct, avec une légende
                                    # explicite — le client doit voir la différence, ce n'est
                                    # pas la même garantie (décision Rami, 20/08).
                                    if getattr(_entry, "validated_via", None) == "memory":
                                        _circle, _lbl_cls = (
                                            '<div class="level-check-circle-done" '
                                            'style="background:#F59E0B;">🟡</div>',
                                            "level-check-label-done",
                                        )
                                        _memory_sub = "🟡 En attente d'intégration BC (mémoire inter-sessions)"
                                    else:
                                        _circle, _lbl_cls = '<div class="level-check-circle-done">✓</div>', "level-check-label-done"
                                elif not _unlocked:
                                    _circle, _lbl_cls = '<div class="level-check-circle-todo"></div>', "level-check-label-locked"
                                else:
                                    _circle, _lbl_cls = '<div class="level-check-circle-todo"></div>', "level-check-label-todo"

                                # AJOUTÉ (26/08/2026, 2e passe) — demande Rami : les membres
                                # d'un groupe (ex. Plan comptable) affichés en point/sous-point
                                # indenté, même langage visuel que la légende mémoire
                                # inter-sessions (pas de drill-down/expander qui détonne).
                                _nested_style = "margin-left:1.8rem" if _nested else ""
                                st.markdown(
                                    f'<div class="level-check-item" style="{_nested_style}">{_circle}'
                                    f'<span class="{_lbl_cls}">{_label}</span></div>'
                                    f'{"<div class=" + chr(34) + "level-check-sub" + chr(34) + ">" + _memory_sub + "</div>" if _memory_sub else ""}',
                                    unsafe_allow_html=True,
                                )
                                # getattr défensif : un RoadmapEntry déjà présent dans
                                # st.session_state (construit par une version antérieure du
                                # code, avant l'ajout de ce champ) n'a pas sub_anomalies —
                                # confirmé par l'AttributeError remontée par Rami le 27/07.
                                #
                                # AJOUTÉ (20/08/2026) : une fois le niveau validé (✓), le
                                # détail des anomalies ne s'affiche plus — Rami : "une fois
                                # un niveau validé les erreurs ne doivent plus être
                                # affichées". sub_anomalies reste figé (scan initial, jamais
                                # recalculé par Revérifier — voir _has_blocking_sub_anomalies)
                                # donc continuer à l'afficher après validation montrerait des
                                # anomalies déjà résolues comme si elles étaient encore là.
                                _sub_anomalies = getattr(_entry, "sub_anomalies", None)
                                if _sub_anomalies and _entry.status != "validated":
                                    # RÉVISÉ (23/08/2026) — simplification écran client (demande
                                    # Bilel) : le détail brut (dataframe technique) reste réservé
                                    # au consultant. Le client voit juste un compteur simple.
                                    if is_consultant():
                                        with st.expander(
                                            f"⚠️ {len(_sub_anomalies)} champ(s) manquant(s) sur des comptes référencés",
                                            expanded=False,
                                        ):
                                            st.dataframe(
                                                pd.DataFrame(_sub_anomalies),
                                                use_container_width=True, hide_index=True,
                                            )
                                            # AJOUTÉ (23/08/2026) — diagnostic : codes BC/mémoire
                                            # réellement vus au dernier Revérifier, à comparer
                                            # visuellement contre "Code manquant" ci-dessus (accents/
                                            # casse/espaces) quand un niveau reste bloqué malgré une
                                            # correction censée être faite dans BC.
                                            _lc = getattr(_entry, "last_codes", None)
                                            if _lc:
                                                st.caption(f"🔎 Codes BC/mémoire vus ({len(_lc)}) :")
                                                st.code(", ".join(sorted(_lc)) or "(aucun)")
                                            else:
                                                st.caption("🔎 Aucun code BC/mémoire trouvé pour cette table.")
                                    else:
                                        st.caption(f"　　⚠️ {len(_sub_anomalies)} point(s) à vérifier avant l'intégration BC.")

                            # RÉVISÉ (26/08/2026) — demande Rami : le setup fonctionnel
                            # transverse (n'appartenant à aucun MDD) doit apparaître AVANT
                            # le groupe "Plan comptable", donc "groupes toujours en premier"
                            # ne convient plus — on ordonnance maintenant TOUT (groupes +
                            # entrées seules) par niveau réel, un groupe étant positionné à
                            # son propre niveau minimum (celui de son premier membre).
                            _render_items = []
                            for _sl_name, _sl_entries in _grouped.items():
                                _sorted_members = sorted(
                                    _sl_entries, key=lambda e: (e.level_info.level or 0, e.level_info.table_id)
                                )
                                _min_level = _sorted_members[0].level_info.level or 0
                                _render_items.append((_min_level, 1, _sl_name, _sorted_members))
                            for _entry in _ungrouped:
                                _render_items.append((_entry.level_info.level or 0, 0, _entry, None))
                            _render_items.sort(key=lambda x: (x[0], x[1]))

                            for _lvl, _kind, _payload, _members in _render_items:
                                if _kind == 0:
                                    _render_level_card(_payload, _show_sub_level_tag=True)
                                    continue
                                # RÉVISÉ (26/08/2026, 2e passe) — demande Rami : plus de
                                # drill-down/expander ("trop moche", cercle incohérent avec
                                # le reste) — le groupe devient une carte de tête (même
                                # cercle .level-check-item que tout le reste, vert seulement
                                # si TOUS les membres sont validés) suivie de ses membres
                                # en point/sous-point indenté, toujours visibles — même
                                # langage visuel que la légende mémoire inter-sessions.
                                _all_validated = all(m.status == "validated" for m in _members)
                                if _all_validated:
                                    _grp_circle, _grp_cls = '<div class="level-check-circle-done">✓</div>', "level-check-label-done"
                                else:
                                    _grp_circle, _grp_cls = '<div class="level-check-circle-todo"></div>', "level-check-label-todo"
                                st.markdown(
                                    f'<div class="level-check-item">{_grp_circle}'
                                    f'<span class="{_grp_cls}"><b>{_payload}</b></span></div>',
                                    unsafe_allow_html=True,
                                )
                                for _m in _members:
                                    _render_level_card(_m, _show_sub_level_tag=False, _nested=True)
                        except Exception as _diag_e:
                            # DIAGNOSTIC — laissé en place tant qu'on n'a pas une confirmation
                            # de stabilité dans la durée. Sans impact visuel si tout va bien.
                            # RÉVISÉ (23/08/2026) — simplification écran client (demande
                            # Bilel) : la trace technique complète reste réservée au
                            # consultant, le client voit un message neutre.
                            if is_consultant():
                                import traceback
                                st.error("🔧 DIAGNOSTIC — erreur capturée dans la boucle d'affichage de la roadmap :")
                                st.code(traceback.format_exc())
                            else:
                                st.warning("⚠️ Affichage des prérequis momentanément indisponible. Réessaie dans un instant.")

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
                    if _all_sub_anomalies and is_consultant():
                        # RÉVISÉ (23/08/2026) — simplification écran client (demande
                        # Bilel) : export brut réservé au consultant.
                        st.download_button(
                            "⬇️ Toutes les anomalies (tous niveaux)",
                            data=build_prerequisites_excel(_all_sub_anomalies),
                            file_name="anomalies_tous_niveaux.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_all_sub_anomalies",
                        )

                    # RÉVISÉ (20/08/2026) — changement de philosophie validé avec Rami :
                    # "prêt pour la correction" ne dépend plus de "tous les niveaux
                    # validés". Avec la mémoire inter-sessions, exiger une validation
                    # BC complète avant de pouvoir corriger un fichier bloque le flux
                    # réel du client (il prépare/corrige TOUS ses MDD avant que le
                    # consultant intègre en bloc — pendant toute cette phase, BC reste
                    # naturellement incomplet). Le roadmap garde sa valeur de suivi/
                    # priorisation, mais n'est plus une porte. Le vrai garde-fou se
                    # déplace vers la clôture de session (can_close_session,
                    # sessions_db.py) et vers l'intégration BC réelle — pas vers la
                    # préparation/correction du fichier.
                    _levels_ok = True
                    _n_pending = sum(1 for e in _roadmap if e.status != "validated") if _roadmap else 0
                    if _n_pending:
                        st.info(
                            f"ℹ️ {_n_pending} niveau(x) prérequis pas encore confirmé(s) "
                            "(ni en BC, ni via une autre session) — tu peux corriger ce "
                            "fichier dès maintenant, mais vérifie ces niveaux avant "
                            "l'intégration réelle dans BC."
                        )
                # _roadmap vide => aucune dépendance de niveau détectée => _levels_ok reste True (analyse directe)
            # level_config vide/non chargée : ne bloque pas l'analyse — à corriger si level_config
            # doit être rendue obligatoire (dépend de si tu veux imposer le seed avant tout usage).

        st.markdown("---")
        # RÉVISÉ (27/08/2026, 5e passe) — demande Rami : le bouton central
        # "Lancer l'analyse qualité" dominait visuellement toute la largeur
        # de l'écran (ratio [2,5,2] laissait la colonne du milieu bien trop
        # grande) — la couleur "primary" (bleu) suffit déjà à le distinguer
        # comme action principale, pas besoin qu'il soit aussi
        # disproportionné en taille. Colonnes resserrées + spacer final pour
        # que les 3 boutons restent groupés à gauche, compacts.
        cb, cv, crc, _cstep3_spacer = st.columns([1.4, 2.4, 1.2, 3])
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
                        # CORRIGÉ (26/08/2026, jour J) — BUG RÉEL trouvé : _exec_plan
                        # n'était JAMAIS défini dans cette branche (seulement dans le
                        # else ci-dessous) — toute la détection de cohérence IA plus
                        # bas (qui a besoin de _exec_plan) plantait silencieusement
                        # (NameError) à chaque fois qu'un cache _early existait déjà —
                        # c'est-à-dire À CHAQUE FOIS en pratique, puisque l'Étape 3
                        # calcule toujours ce cache avant qu'on clique "Lancer
                        # l'analyse qualité". Cause racine probable de "aucune
                        # suggestion IA, jamais, même après tous les autres fixes".
                        _exec_plan = _early["exec_plan"]
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

                    # AJOUTÉ (26/08/2026, jour J) — FIX CRITIQUE : la détection
                    # de cohérence (validate_coherence_axe_c, coherence_
                    # detector.py — combinaisons de champs statistiquement
                    # rares) était codée et fusionnée en feature-branch mais
                    # jamais réellement appelée ici — la page n'invoquait que
                    # l'ancien validate_file_axe_c (enrichissement d'anomalies
                    # déjà détectées), jamais le nouveau détecteur autonome.
                    # Résultat : aucune suggestion IA de ce type ne remontait
                    # jamais, quel que soit le seuil. Ses anomalies ont un
                    # format légèrement différent (Sévérité="Info",
                    # Classification="SUGGESTION_IA", "Correction suggérée"
                    # déjà formatée avec 🧠 + confiance) — ajoutées ici
                    # directement à all_anomalies/by_sheet comme des entrées
                    # de plein droit, sans toucher à merge_results() (déjà
                    # fragile un jour de démo, on ne touche pas à ce qui
                    # fonctionne).
                    if not api_key:
                        st.warning("⚠️ Détection de cohérence IA sautée : clé API vide à ce point précis du code (get_gemini_api_key() a renvoyé une valeur vide).")
                    if api_key:
                        try:
                            # AJOUTÉ (26/08/2026, jour J) — diagnostic : montre
                            # précisément où la chaîne s'arrête (champs éligibles
                            # trouvés ? candidats statistiques avant l'IA ?) au
                            # lieu de deviner encore à l'aveugle.
                            # RÉVISÉ (26/08/2026, 2e passe) — retiré la condition
                            # is_consultant() : aucune trace visible ne remontait
                            # plus du tout, sans savoir si c'était parce que rien
                            # n'y était détecté, ou parce que le rôle actif
                            # masquait tout diagnostic. Affiché systématiquement
                            # tant qu'on n'a pas confirmé le vrai fix.
                            from app.core.coherence_detector import get_eligible_fields, detect_rare_pairs
                            _diag_lines = []
                            for _sn_diag in pr.get("data_tables", []):
                                _df_diag = pr.get("sheets", {}).get(_sn_diag)
                                _meta_diag = pr.get("metadata", {}).get(_sn_diag, {})
                                _tid_diag = _meta_diag.get("table_id", "")
                                if _df_diag is None or _df_diag.empty or not _tid_diag:
                                    continue
                                try:
                                    _elig = [f for f in get_eligible_fields(_exec_plan, int(_tid_diag)) if f in _df_diag.columns]
                                except (ValueError, TypeError):
                                    _elig = []
                                _cands = detect_rare_pairs(_df_diag, _elig, max_pair_ratio=0.12) if len(_elig) >= 2 else []
                                _diag_lines.append(
                                    f"{_sn_diag} (table {_tid_diag}) : {len(_elig)} champ(s) éligible(s) {_elig[:6]}, "
                                    f"{len(_cands)} candidat(s) avant IA"
                                )
                                for _c in _cands[:5]:
                                    _diag_lines.append(f"    -> {_c}")

                            with st.spinner("🧠 Détection des incohérences en cours..."):
                                _coherence = validate_coherence_axe_c(pr, _exec_plan, api_key)
                            for _sn, _coh_anomalies in _coherence.get("by_sheet", {}).items():
                                if not _coh_anomalies:
                                    continue
                                merged["all_anomalies"].extend(_coh_anomalies)
                                merged["by_sheet"].setdefault(_sn, []).extend(_coh_anomalies)

                            # RÉVISÉ (27/08/2026, jour de la démo) — demande Rami :
                            # rendre le diagnostic copiable en un clic (bouton de
                            # copie natif de st.code), et TOUJOURS visible, y
                            # compris la ligne d'erreur Gemini même vide — un seul
                            # bloc à copier-coller intégralement, plus besoin de
                            # recopier plusieurs lignes à la main.
                            from app.core.validator_axe_c import LAST_GEMINI_ERROR
                            _diag_lines.append(f"Total incohérences détectées par l'IA : {_coherence.get('total_flagged', 0)}")
                            _diag_lines.append(f"Dernière erreur Gemini (vide = aucune) : {LAST_GEMINI_ERROR or '(aucune)'}")
                            # RÉVISÉ (27/08/2026, 2e passe) — bug trouvé : ce bloc ne
                            # s'affichait QUE pendant l'exécution du clic "Lancer
                            # l'analyse qualité" — au rerun suivant (n'importe quelle
                            # interaction sur l'Étape 4), il disparaissait, rendant la
                            # copie impossible. Persisté en session_state, réaffiché
                            # en permanence dans display_merged_analysis (voir plus
                            # bas) tant qu'une nouvelle analyse n'écrase pas ces
                            # valeurs.
                            st.session_state["_ia_diag_text"]  = "\n".join(_diag_lines)
                            st.session_state["_ia_diag_error"] = LAST_GEMINI_ERROR
                        except Exception as _coh_exc:
                            st.session_state["_ia_diag_text"]  = f"Exception : {_coh_exc}"
                            st.session_state["_ia_diag_error"] = str(_coh_exc)

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

        # AJOUTÉ (23/08/2026) — demande Rami : possibilité de sauvegarder à
        # cette étape aussi (checkpoint), pas seulement à la toute fin.
        # RÉVISÉ (27/08/2026, 5e passe) — même correction : bouton compact
        # au lieu de pleine largeur pour un texte court.
        _qs3_col, _ = st.columns([1.8, 3])
        with _qs3_col:
            if st.button("💾 Enregistrer maintenant (checkpoint)", key="quicksave_step3", use_container_width=True):
                _quick_save_session(cfg, status="Nouvelle")

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

        # AJOUTÉ (23/08/2026) — demande Rami : recalcule total/major/minor en
        # excluant les anomalies "Prérequis BC requis" déjà résolues dans la
        # roadmap (BC ou mémoire inter-sessions), au lieu de garder les
        # compteurs figés du scan initial — sinon incohérent avec le tableau
        # détaillé juste en dessous (display_unified_results), qui applique
        # déjà ce même filtre. Utilisé aussi pour la sauvegarde de session
        # plus bas (total_anomalies/major_anomalies/minor_anomalies) — un
        # bénéfice secondaire bienvenu : la session sauvegardée reflète l'état
        # réel plutôt que le scan figé.
        _roadmap_key_e4 = f"level_roadmap_{cfg.get('pkg_code', '')}_{cfg.get('company_id', '')}_{cfg.get('file_name', '')}"
        _roadmap_e4 = st.session_state.get(_roadmap_key_e4) or []
        _resolved_by_table: dict[int, set] = {
            e.level_info.table_id: (e.last_codes or set())
            for e in _roadmap_e4
            if getattr(e, "last_codes", None)
        }
        _all_anomalies_e4 = merged.get("all_anomalies", [])
        _validated_table_ids_e4 = {e.level_info.table_id for e in _roadmap_e4 if e.status == "validated"}
        _filtered_e4, _resolved_count_e4 = _filter_resolved_prereqs(
            _all_anomalies_e4, _resolved_by_table,
            hide_all_prereqs=bool(_roadmap_e4) and all_validated(_roadmap_e4),
            validated_table_ids=_validated_table_ids_e4,
        )
        if _resolved_count_e4:
            _real_e4 = [a for a in _filtered_e4 if a.get("Ligne", 0) > 0]
            total = len(_real_e4)
            major = sum(1 for a in _real_e4 if a.get("Sévérité") == "Majeure")
            minor = sum(1 for a in _real_e4 if a.get("Sévérité") == "Mineure")

        # RÉVISÉ (27/08/2026, 2e passe) — demande Rami : retiré complètement
        # (pas juste réservé au consultant) — la classification de chaque
        # ligne (🟣/✏️/🧠) est déjà visible directement dans sa propre colonne
        # du tableau fusionné, cette légende séparée était redondante depuis
        # que cette colonne existe.
        display_merged_analysis(merged, axe_c, cfg, pr, resolved_by_table=_resolved_by_table, roadmap=_roadmap_e4)

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

                # RÉVISÉ (23/08/2026) — simplification écran client (demande
                # Bilel) : le choix d'architecture racine/fille est une
                # décision consultant (rattachement à la roadmap technique),
                # pas quelque chose que le client doit comprendre pour
                # sauvegarder sa session. Le client sauvegarde simplement en
                # racine ; le consultant garde le contrôle complet.
                if is_consultant():
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
                else:
                    # AJOUTÉ (23/08/2026) — auto-détection silencieuse pour le
                    # client : même logique que le consultant
                    # (resolve_parent_candidates), sans lui montrer le choix
                    # technique. Un seul cas s'auto-rattache en Fille : le
                    # fichier contient exactement UNE table identifiable ET
                    # UN SEUL parent candidat existe dans l'arbre de sessions
                    # de cette société. Tout autre cas (0 ou plusieurs tables,
                    # 0 ou plusieurs parents candidats) retombe sur Racine —
                    # même repli que le comportement par défaut déjà en place,
                    # jamais une régression silencieuse plus risquée que
                    # l'ancien état "toujours Racine".
                    _node_kind     = "Racine (socle complet)"
                    _sel_table_id  = None
                    _sel_parent_id = None
                    if len(_table_options) == 1:
                        _auto_tid = _table_options[0][0]
                        _auto_candidates = resolve_parent_candidates(_tree_sessions, _auto_tid, _lvl_cfg)
                        if len(_auto_candidates) == 1:
                            _node_kind     = "Fille (une table de la roadmap)"
                            _sel_table_id  = _auto_tid
                            _sel_parent_id = _auto_candidates[0]["id"]

                _save_col, _ = st.columns([1.5, 3])
                with _save_col:
                    _save_clicked = st.button("💾 Sauvegarder la session", type="primary", use_container_width=True)
                if _save_clicked:
                    original_bytes  = st.session_state.get("original_file_bytes")
                    generated_bytes = st.session_state.get("generated_file_bytes")
                    _save_payload = {
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
                    }
                    # RÉVISÉ (23/08/2026) — demande Rami : reprendre une
                    # session (▶️ Reprendre) puis sauvegarder créait une
                    # NOUVELLE session à chaque fois. Si la session en cours
                    # a été reprise (resumed_session_id), on MET À JOUR cet
                    # id au lieu d'en créer un nouveau.
                    _resumed_id = st.session_state.get("resumed_session_id")
                    if _resumed_id:
                        _ok, _err = update_session(_resumed_id, {**_save_payload, "name": _save_payload["session_name"]})
                        ok, res = _ok, (_resumed_id if _ok else _err)
                    else:
                        ok, res = save_session(_save_payload)
                    if ok:
                        st.session_state.saved_session_id = res
                        # AJOUTÉ (20/08/2026) — mémoire inter-sessions : les
                        # lignes de CE fichier (préférence au fichier généré,
                        # corrections déjà appliquées — sinon repli sur
                        # l'original) représentent des enregistrements que le
                        # client s'apprête à faire exister dans BC. D'autres
                        # sessions de la même société pourront désormais les
                        # reconnaître comme "en attente" plutôt que
                        # "introuvable" (voir check_table_filled_and_codes).
                        # RÉVISÉ (23/08/2026) — le retour de save_pending_codes
                        # était ignoré : un échec (ex. table Supabase
                        # manquante) disparaissait silencieusement, sans
                        # aucune trace pour comprendre pourquoi la mémoire
                        # inter-sessions ne fonctionnait pas. Reste
                        # non-bloquant pour la sauvegarde de session
                        # elle-même (déjà confirmée juste avant), mais
                        # affiche désormais l'échec au consultant.
                        # RÉVISÉ (23/08/2026, 2e passe) — bug trouvé : le
                        # st.warning() ci-dessous était placé juste avant
                        # reset_session()+st.rerun() DANS LA MÊME EXÉCUTION —
                        # Streamlit interrompt le script immédiatement à
                        # st.rerun(), donc ce message n'avait jamais le temps
                        # de s'afficher. Stocké en session_state pour survivre
                        # au rerun et s'afficher sur le formulaire neuf (même
                        # mécanisme que _just_saved_banner). Ajout aussi d'un
                        # cas jusqu'ici totalement silencieux : extraction
                        # réussie mais _codes_by_table vide (colonne clé
                        # "Code"/"N°" introuvable dans le fichier) — jamais
                        # signalé avant, aucune trace nulle part.
                        _mem_warning = None
                        # RÉVISÉ (26/08/2026) — demande Rami : la mémoire ne
                        # doit s'appliquer QUE quand cette session résout
                        # spécifiquement UNE table prérequis pour d'autres
                        # (session fille, table_id connu) — jamais pour une
                        # session racine (le fichier entier, ex. tout le
                        # Stock), dont les onglets (Article inclus) ne sont
                        # pas des "prérequis en attente" mais le sujet même
                        # de la session. Sans ça, chaque sauvegarde
                        # déclarait TOUS ses onglets comme prêts, y compris
                        # sa propre table principale — cause réelle
                        # d'Article validé à tort en mémoire. Filtré aussi
                        # à la SEULE table concernée (pas tous les onglets
                        # du fichier), même pour une fille.
                        _is_child_session = (_node_kind == "Fille (une table de la roadmap)" and _sel_table_id)
                        if _is_child_session:
                            try:
                                _bytes_for_memory = generated_bytes or original_bytes
                                if _bytes_for_memory:
                                    from app.core.bc_excel_processor import extract_key_values_by_table
                                    from app.db.metadata_db import save_pending_codes
                                    _codes_by_table_all = extract_key_values_by_table(_bytes_for_memory)
                                    _codes_by_table = {
                                        k: v for k, v in _codes_by_table_all.items() if k == _sel_table_id
                                    }
                                    if _codes_by_table:
                                        _mem_ok, _mem_err = save_pending_codes(
                                            session_id=res,
                                            profile_code=cfg["client_code"],
                                            company_id=cfg.get("company_id", ""),
                                            codes_by_table=_codes_by_table,
                                        )
                                        if not _mem_ok:
                                            _mem_warning = f"Mémoire inter-sessions non enregistrée : {_mem_err}"
                                    else:
                                        _mem_warning = (
                                            "Mémoire inter-sessions : aucun code extrait pour la table "
                                            f"{_sel_table_id} (colonne clé \"Code\"/\"N°\" introuvable, "
                                            "ou onglet correspondant absent du fichier)."
                                        )
                            except Exception as _mem_exc:
                                _mem_warning = f"Mémoire inter-sessions non enregistrée : {_mem_exc}"
                        # RÉVISÉ (23/08/2026) — demande Rami : repartir
                        # directement sur un formulaire neuf après la
                        # sauvegarde, plutôt que de rester sur l'Étape 4
                        # jusqu'à un clic manuel sur "Recommencer". Le
                        # fichier/rapport restent consultables depuis
                        # "Mes sessions" (déjà sauvegardés juste avant).
                        _saved_name = cfg.get("session_name", "")
                        reset_session()
                        st.session_state["_just_saved_banner"] = (
                            f"✅ Session « {_saved_name} » enregistrée avec succès. "
                            f"Retrouve le fichier et le rapport dans « 📋 Mes sessions »."
                        )
                        if _mem_warning and is_consultant():
                            st.session_state["_just_saved_mem_warning"] = f"⚠️ {_mem_warning}"
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
            _sel_col, _ = st.columns([1, 2])
            with _sel_col:
                _sel_company = st.selectbox(
                    "Société", options=[c[0] for c in _companies],
                    format_func=lambda cid: _company_labels.get(cid, cid),
                    index=None, placeholder="Choisir une société...",
                    key="ses_tree_company",
                )
            # RÉVISÉ (27/08/2026) — demande Rami : liste déroulante vide par
            # défaut. Repli minimal (sans ré-indenter tout le bloc de rendu
            # de l'arbre qui suit) : sans société choisie, on simule une
            # liste de sessions vide, ce qui déclenche déjà naturellement
            # le message "Aucune session pour cette société" existant plus
            # bas — juste reformulé pour rester juste dans ce cas précis.
            if not _sel_company:
                _tree_sessions_view = []
            else:
                _tree_sessions_view = get_sessions_for_company(active_client or "", _sel_company)
            _tree = build_sessions_tree(_tree_sessions_view)
            if not _tree:
                st.info("Choisis une société ci-dessus pour voir son arbre de sessions." if not _sel_company else "Aucune session pour cette société.")
            else:
                _lvl_cfg_view = st.session_state.get("level_config", {})

                def _render_node(node: dict, depth: int = 0):
                    _nid    = node["id"]
                    _status = node.get("status", "Nouvelle")
                    _sc     = STATUS_COLORS.get(_status, "#64748B")
                    _si     = STATUS_ICONS.get(_status, "")
                    _tid    = node.get("table_id")
                    _pkg    = node.get("pkg_code", "")
                    _is_root = bool(node.get("is_root"))
                    _tname  = (
                        "📁 Racine du socle" if _is_root
                        else (f"{_tid} — {_lvl_cfg_view[_tid].table_name}" if _tid in _lvl_cfg_view else f"Table {_tid}")
                    )
                    # RÉVISÉ (23/08/2026) — refonte visuelle (demande Rami : la
                    # vue arbre en texte brut + "└─" n'était pas ergonomique).
                    # Carte cohérente avec le design déjà utilisé ailleurs
                    # dans l'app (.card-session, .tag), statut en pastille
                    # colorée au lieu d'un simple mot, package en petit tag.
                    _connector = ('<span class="tree-connector">└─</span>' if depth > 0 else "")
                    _pkg_html  = (f'<span class="pkg-pill">📦 {_pkg}</span>' if _pkg else "")
                    st.markdown(
                        f'<div class="tree-card{" tree-card-root" if _is_root else ""}" '
                        f'style="margin-left:{depth*28}px;border-left-color:{_sc}">'
                        f'<div class="tree-card-title">{_connector}{node.get("name", "")}</div>'
                        f'<div class="tree-card-meta">{_tname}{_pkg_html}'
                        f'<span class="status-pill" style="background:{_sc}22;color:{_sc}">{_si} {_status}</span>'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )
                    if not _is_root and _tid:
                        rc1, rc2 = st.columns([1, 1])
                        with rc1:
                            if st.button("🔄 Revérifier ce sous-arbre", key=f"scope_reverif_{_nid}", use_container_width=True):
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
                                        # RÉVISÉ (26/08/2026) — même fix qu'à l'Étape 3 :
                                        # exclut la session elle-même de sa propre
                                        # vérification mémoire (même bug de
                                        # self-confirmation en boucle).
                                        exclude_session_id=_nid,
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
                            elif st.button("🔒 Clôturer", key=f"close_{_nid}", use_container_width=True):
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
                    elif _is_root:
                        # Clôture du socle entier — même règle, appliquée à la racine :
                        # bloquée tant que le socle lui-même a des anomalies ou qu'une
                        # SEULE de ses filles directes n'est pas encore "Terminée"
                        # (chaque fille "Terminée" garantit déjà la propreté de SA
                        # propre branche, récursivement — voir can_close_session).
                        if _status == _CLOSED_STATUS_LABEL:
                            st.success("🏁 Socle clôturé — tous les niveaux et sous-niveaux sont vérifiés.")
                        else:
                            # RÉVISÉ (23/08/2026) — bouton plein largeur trop
                            # imposant visuellement à côté des cartes compactes.
                            # Contraint à une petite colonne, comme les boutons
                            # par nœud (Revérifier/Clôturer) juste au-dessus.
                            _rc, _ = st.columns([1, 3])
                            with _rc:
                                _close_root_clicked = st.button(
                                    "🏁 Clôturer le socle", key=f"close_root_{_nid}", use_container_width=True
                                )
                            if _close_root_clicked:
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
            # AJOUTÉ (23/08/2026) — demande Rami : recherche + suppression en
            # lot, pour nettoyer rapidement avant de retester la mémoire
            # inter-sessions sur une base propre. Recherche sur nom, client,
            # société et fichier — insensible à la casse, simple `in`.
            _search_col, _ = st.columns([1, 2])
            with _search_col:
                _search = st.text_input(
                    "🔎 Rechercher une session", key="ses_search",
                    placeholder="Nom, client, société, fichier...",
                )
            if _search.strip():
                _q = _search.strip().lower()
                sessions = [
                    s for s in sessions
                    if _q in (s.get("name", "") or "").lower()
                    or _q in (s.get("profile_code", "") or "").lower()
                    or _q in (s.get("company_name", "") or "").lower()
                    or _q in (s.get("file_name", "") or "").lower()
                ]

            if "bulk_select_ids" not in st.session_state:
                st.session_state.bulk_select_ids = set()
            if "confirm_bulk_delete" not in st.session_state:
                st.session_state.confirm_bulk_delete = False
            if "_bulk_gen" not in st.session_state:
                st.session_state._bulk_gen = 0

            _bcol1, _bcol2, _bcol3, _bcol4 = st.columns([2, 2, 2, 4])
            with _bcol1:
                if st.button("✅ Tout sélectionner", key="btn_bulk_select_all", use_container_width=True):
                    st.session_state.bulk_select_ids = {s["id"] for s in sessions if s.get("id")}
                    # AJOUTÉ (23/08/2026) — même pattern que l'éditeur de
                    # correction (Étape 4) : une checkbox déjà rendue garde
                    # son propre état interne Streamlit et ignore `value=`
                    # au rerun suivant. Changer sa clé force une instance
                    # neuve qui respecte bien value=True/False.
                    st.session_state._bulk_gen += 1
                    st.rerun()
            with _bcol2:
                if st.button("⬜ Tout désélectionner", key="btn_bulk_deselect_all", use_container_width=True):
                    st.session_state.bulk_select_ids = set()
                    st.session_state.confirm_bulk_delete = False
                    st.session_state._bulk_gen += 1
                    st.rerun()
            with _bcol3:
                _n_sel = len(st.session_state.bulk_select_ids & {s.get("id") for s in sessions})
                if st.button(f"🗑️ Supprimer ({_n_sel})", key="btn_bulk_delete", type="primary",
                             use_container_width=True, disabled=_n_sel == 0):
                    st.session_state.confirm_bulk_delete = True

            if st.session_state.confirm_bulk_delete:
                _to_delete = st.session_state.bulk_select_ids & {s.get("id") for s in sessions}
                # RÉVISÉ (23/08/2026) — demande Rami : le gros encadré jaune
                # (st.warning) + 2 boutons faisait double emploi avec le
                # bouton "Supprimer (N)" déjà cliqué juste au-dessus — trop
                # lourd visuellement. Simplifié en une ligne de texte + un
                # seul bouton de confirmation (pas de bouton "Annuler" séparé
                # : décocher/re-changer la sélection referme ce bloc tout
                # seul au prochain rerun).
                _cc1, _cc2 = st.columns([4, 2])
                with _cc1:
                    st.markdown(f"Supprimer **{len(_to_delete)} session(s)** sélectionnée(s) ?")
                with _cc2:
                    if st.button("✅ Confirmer", key="btn_bulk_confirm", type="primary", use_container_width=True):
                        _errs = []
                        for _sid in _to_delete:
                            _ok, _err = delete_session(_sid)
                            if not _ok:
                                _errs.append(f"{_sid} : {_err}")
                        st.session_state.bulk_select_ids = set()
                        st.session_state.confirm_bulk_delete = False
                        if _errs:
                            st.error("Certaines suppressions ont échoué :\n" + "\n".join(f"- {e}" for e in _errs))
                        else:
                            st.success(f"{len(_to_delete)} session(s) supprimée(s).")
                        st.rerun()

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
    
                # RÉVISÉ (23/08/2026) — refonte ergonomique (demande Rami) :
                # avant, checkbox / carte / boutons Éditer-Supprimer étaient
                # 3 colonnes disjointes, et les 3 boutons de téléchargement
                # formaient un gros bloc toujours visible sous la carte.
                # st.container(border=True) unifie tout en UNE carte
                # cohérente ; les téléchargements (usage occasionnel)
                # passent dans un expander replié par défaut.
                with st.container(border=True):
                    top_ck, top_info, top_actions = st.columns([0.6, 6.4, 1.6])
                    with top_ck:
                        _checked = st.checkbox(
                            "Sélectionner", key=f"bulk_chk_{sid}_{st.session_state._bulk_gen}",
                            value=sid in st.session_state.bulk_select_ids,
                            label_visibility="collapsed",
                        )
                        if _checked:
                            st.session_state.bulk_select_ids.add(sid)
                        else:
                            st.session_state.bulk_select_ids.discard(sid)
                    with top_info:
                        st.markdown(
                            f'<p class="session-name" style="margin-bottom:.2rem">{s.get("name", "")}</p>'
                            f'<p class="session-meta">Client : <b>{s.get("profile_code", "")}</b> · '
                            f'<span style="color:{sc};font-weight:500">{si} {status}</span></p>'
                            f'<p class="session-meta">{an_s}</p>'
                            f'<p class="session-meta">{"📄 " + fn + " · " if fn else ""}🕐 {crd}'
                            f'{"  ·  ✏️ " + upd if upd != crd else ""}'
                            f'{"  ·  📦 corrigé" if gen_fn else ""}'
                            f'{"  ·  🟣 " + str(len(prereq_list)) + " prérequis" if prereq_list else ""}</p>',
                            unsafe_allow_html=True
                        )
                    with top_actions:
                        tr, te, td = st.columns(3)
                        with tr:
                            if st.button("▶️", key=f"resume_{sid}",
                                         help="Reprendre — recharge le fichier et rouvre l'analyse (roadmap, niveaux)"):
                                # AJOUTÉ (23/08/2026) — demande Rami : aucun moyen de
                                # rouvrir une session sauvegardée dans le flux Étape
                                # 1-4 (roadmap, Revérifier...) — seul le résumé
                                # (nom/statut/notes + téléchargements) était
                                # accessible. Recharge le fichier original depuis
                                # Supabase et relance le parsing pour rouvrir
                                # directement à l'Étape 3.
                                _resume_b64 = get_session_file_blob(sid, "original_file_b64")
                                if not _resume_b64:
                                    st.error("Fichier original introuvable pour cette session — impossible de reprendre.")
                                else:
                                    import io as _io
                                    _resume_bytes = base64.b64decode(_resume_b64)
                                    _file_like = _io.BytesIO(_resume_bytes)
                                    _file_like.name = fn or "fichier.xlsx"
                                    _resume_pr = parse_uploaded_file(_file_like)
                                    if not _resume_pr.get("success"):
                                        st.error("Le fichier original n'a pas pu être ré-analysé (structure invalide).")
                                    else:
                                        reset_session()
                                        st.session_state.original_file_bytes = _resume_bytes
                                        st.session_state.parse_result = _resume_pr
                                        st.session_state.validation   = validate_file_structure(_resume_pr)
                                        st.session_state.config = {
                                            "client_code":   s.get("profile_code", ""),
                                            "client_name":   active_client_name,
                                            "company_id":    s.get("company_id", ""),
                                            "company_name":  s.get("company_name", ""),
                                            "pkg_code":      s.get("pkg_code", ""),
                                            "file_name":     s.get("file_name", ""),
                                            "session_name":  s.get("name", ""),
                                            "table_id":          s.get("table_id"),
                                            "parent_session_id": s.get("parent_session_id"),
                                            "is_root":           s.get("is_root", False),
                                        }
                                        st.session_state.step = 3
                                        # AJOUTÉ (23/08/2026) — marque cette session comme
                                        # "reprise" : la prochaine sauvegarde (Étape 2/3/4)
                                        # doit mettre à jour CET id au lieu d'en créer un
                                        # nouveau (voir _quick_save_session et le bouton
                                        # Sauvegarder de l'Étape 4). Assigné APRÈS
                                        # reset_session() : sinon reset_session() (qui purge
                                        # les clés de session_state d'une session en cours)
                                        # l'effacerait aussitôt.
                                        st.session_state["resumed_session_id"] = sid
                                        # Streamlit ne permet pas de changer l'onglet
                                        # actif par le code — bannière persistée pour
                                        # guider l'utilisateur vers l'autre onglet.
                                        st.session_state["_resume_banner"] = (
                                            f"▶️ Session « {s.get('name', '')} » rechargée — "
                                            f"ouvre l'onglet **➕ Nouvelle session** pour continuer."
                                        )
                                        st.rerun()
                        with te:
                            if st.button("✏️", key=f"es_{sid}", help="Modifier"):
                                st.session_state.edit_session_id    = sid
                                st.session_state.confirm_delete_ses = None
                        with td:
                            if st.button("🗑️", key=f"ds_{sid}", help="Supprimer"):
                                st.session_state.confirm_delete_ses = sid
                                st.session_state.edit_session_id    = None

                    # Fichiers & téléchargements — replié : usage occasionnel,
                    # ne doit pas dominer visuellement la carte.
                    if fn or gen_fn or prereq_list:
                        with st.expander("🗂️ Fichiers"):
                            dcol1, dcol2, dcol3 = st.columns(3)
                            with dcol1:
                                if fn:
                                    _ck = f"_blob_orig_{sid}"
                                    if st.session_state.get(_ck):
                                        st.download_button(
                                            "⬇️ Fichier chargé", data=base64.b64decode(st.session_state[_ck]),
                                            file_name=fn or "fichier_charge.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            key=f"dl_orig_{sid}", use_container_width=True,
                                        )
                                    else:
                                        if st.button("📄 Charger le fichier", key=f"load_orig_{sid}", use_container_width=True):
                                            st.session_state[_ck] = get_session_file_blob(sid, "original_file_b64")
                                            st.rerun()
                            with dcol2:
                                if gen_fn:
                                    _ck = f"_blob_gen_{sid}"
                                    if st.session_state.get(_ck):
                                        st.download_button(
                                            "⬇️ Fichier corrigé", data=base64.b64decode(st.session_state[_ck]),
                                            file_name=gen_fn or "fichier_corrige.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            key=f"dl_gen_{sid}", use_container_width=True,
                                        )
                                    else:
                                        if st.button("📄 Charger le fichier corrigé", key=f"load_gen_{sid}", use_container_width=True):
                                            st.session_state[_ck] = get_session_file_blob(sid, "generated_file_b64")
                                            st.rerun()
                            with dcol3:
                                if prereq_list:
                                    st.download_button(
                                        "⬇️ Prérequis BC", data=build_prerequisites_excel(prereq_list),
                                        file_name=f"prerequis_bc_{sid}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=f"dl_prereq_{sid}", use_container_width=True,
                                    )

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

                    if st.session_state.confirm_delete_ses == sid:
                        st.warning(f"⚠️ Supprimer **{s.get('name', '')}** ? Action irréversible.")
                        dy, dn, _ = st.columns([2, 2, 6])
                        with dy:
                            if st.button("✅ Confirmer", key=f"dcy_{sid}", type="primary", use_container_width=True):
                                ok, err = delete_session(sid)
                                if ok:
                                    st.success("Supprimée.")
                                    st.session_state.confirm_delete_ses = None
                                    st.rerun()
                                else:
                                    st.error(err)
                        with dn:
                            if st.button("❌ Annuler", key=f"dcn_{sid}", use_container_width=True):
                                st.session_state.confirm_delete_ses = None
                                st.rerun()