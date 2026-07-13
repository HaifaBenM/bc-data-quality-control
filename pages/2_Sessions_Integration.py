import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a
from app.core.validator_axe_b import validate_file_axe_b
from app.core.validator_axe_c import validate_file_axe_c, get_gemini_api_key, is_gemini_available
from app.core.auth import require_role
from app.core.execution_planner import get_execution_plan
from app.core.simulation_context import SimulationContext
from app.core.metadata_loader import MetadataLoader
from app.db.profiles_db import get_profile_by_code
from app.core.bc_api import get_access_token, get_companies
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
.conf-bar { background: #E2E8F0; border-radius: 3px; height: 5px; margin: 4px 0; }
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

# ── Société BC ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _load_companies_ses(client_code: str) -> tuple[list, str, str]:
    try:
        p = get_profile_by_code(client_code)
        if not p:
            return [], "", ""
        tid = p.get("bc_tenant_id","").strip()
        cid = p.get("bc_client_id","").strip()
        cs  = p.get("bc_client_secret","").strip()
        env = p.get("bc_environment","").strip()
        if not all([tid, cid, cs, env]):
            return [], "", ""
        tok       = get_access_token(tid, cid, cs)
        companies = get_companies(tid, env, tok)
        return companies, "", ""
    except Exception as e:
        return [], str(e), ""

_ses_companies, _ses_err, _ = _load_companies_ses(active_client)

_default_cid   = st.session_state.get("active_company_id", "")
_default_cname = st.session_state.get("active_company_name", "")
if not _default_cid and _ses_companies:
    _p = get_profile_by_code(active_client)
    if _p:
        _default_cid   = _p.get("bc_company_id", "") or ""
        _default_cname = _p.get("bc_company_name", "") or ""


# ── BC_DETECTED ───────────────────────────────────────────────────────────────
BC_DETECTED = {
    "Longueur maximale dépassée",
    "Valeur Option non autorisée",
    "Type incorrect (entier attendu)",
    "Type incorrect (décimal attendu)",
    "Type incorrect (booléen attendu)",
    "Format de date incorrect",
}

def bc_badge(error_type: str) -> str:
    if error_type in BC_DETECTED:
        return '<span class="tag tag-bc" title="Détecté aussi par BC Config Package">🔴 BC</span>'
    return '<span class="tag tag-plus" title="Détecté uniquement par notre outil">⭐ Plus</span>'


def merge_results(axe_a: dict, axe_b: dict, axe_c: dict) -> dict:
    merged     = {"by_sheet": {}, "all_anomalies": [], "ai_by_sheet": {}}
    all_sheets = set()
    for result in [axe_a, axe_b]:
        all_sheets.update(result.get("by_sheet", {}).keys())

    ai_map = {}
    if axe_c.get("available") and axe_c.get("by_sheet"):
        for sn, anomalies in axe_c["by_sheet"].items():
            for a in anomalies:
                if a.get("suggestion_ia"):
                    key = (sn, a.get("Ligne",0), a.get("Champ",""))
                    ai_map[key] = {
                        "suggestion":  a["suggestion_ia"],
                        "confiance":   a.get("confiance_ia", 0),
                        "explication": a.get("explication_ia",""),
                        "auto":        a.get("auto_corrige", False),
                    }

    for sn in all_sheets:
        sheet_anomalies = []
        for result in [axe_a, axe_b]:
            for a in result.get("by_sheet",{}).get(sn, []):
                clean = {k: v for k, v in a.items() if k != "Axe"}
                key   = (sn, a.get("Ligne",0), a.get("Champ",""))
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
        merged["by_sheet"][sn]       = sheet_anomalies
        merged["all_anomalies"].extend(sheet_anomalies)

    return merged


def display_unified_results(merged: dict, axe_c: dict):
    all_anomalies = merged.get("all_anomalies", [])
    real          = [a for a in all_anomalies if a.get("Ligne",0) > 0]
    info          = [a for a in all_anomalies if a.get("Ligne",0) == 0]

    if not real and not info:
        st.success("🎉 **Aucune anomalie détectée !** Les données sont conformes.")
        return

    has_ia = axe_c.get("available") and axe_c.get("total_suggestions",0) > 0
    auto_c = axe_c.get("auto_corrected", 0)
    if has_ia and auto_c > 0:
        st.info(f"🤖 **{auto_c} correction(s) appliquée(s) automatiquement** par l'IA")

    by_sheet    = merged.get("by_sheet", {})
    sheet_names = list(by_sheet.keys())
    tab_labels  = []
    for sn in sheet_names:
        a    = by_sheet[sn]
        nb   = len([x for x in a if x.get("Ligne",0)>0])
        nmaj = sum(1 for x in a if x.get("Sévérité")=="Majeure")
        icon = "🔴" if nmaj>0 else ("🟠" if nb>0 else "✅")
        tab_labels.append(f"{icon} {sn} ({nb})")

    if not tab_labels:
        return

    for tab, sn in zip(st.tabs(tab_labels), sheet_names):
        with tab:
            anomalies      = by_sheet.get(sn, [])
            real_anomalies = [a for a in anomalies if a.get("Ligne",0)>0]
            info_anomalies = [a for a in anomalies if a.get("Ligne",0)==0]

            if not real_anomalies and not info_anomalies:
                st.success("✅ Aucune anomalie."); continue

            if real_anomalies:
                nb_maj = sum(1 for a in real_anomalies if a.get("Sévérité")=="Majeure")
                nb_min = sum(1 for a in real_anomalies if a.get("Sévérité")=="Mineure")
                nb_ia  = sum(1 for a in real_anomalies if a.get("suggestion_ia"))
                t1,t2,t3,t4 = st.columns(4)
                t1.metric("Anomalies",     len(real_anomalies))
                t2.metric("🔴 Majeures",   nb_maj)
                t3.metric("🟠 Mineures",   nb_min)
                t4.metric("🤖 IA suggère", nb_ia)

                cf1, cf2 = st.columns(2)
                with cf1:
                    sevs     = sorted(set(a.get("Sévérité","") for a in real_anomalies))
                    filt_sev = st.multiselect("Sévérité", sevs, default=sevs, key=f"fs_{sn}")
                with cf2:
                    types     = sorted(set(a.get("Type d'anomalie","") for a in real_anomalies))
                    filt_type = st.multiselect("Type d'anomalie", types, default=types, key=f"ft_{sn}")

                filtered = [
                    a for a in real_anomalies
                    if a.get("Sévérité","") in filt_sev
                    and a.get("Type d'anomalie","") in filt_type
                ]

                if filtered:
                    cols_to_show = ["Ligne","Champ","Valeur","Type d'anomalie","Sévérité","Message","Correction suggérée"]
                    df_show      = pd.DataFrame([{c: a.get(c,"") for c in cols_to_show} for a in filtered])

                    def color_row(row):
                        s = row.get("Sévérité","")
                        if s=="Majeure": return ["background-color:#FAECE7"]*len(row)
                        if s=="Mineure": return ["background-color:#FAEEDA"]*len(row)
                        return [""]*len(row)

                    st.dataframe(
                        df_show.style.apply(color_row, axis=1),
                        use_container_width=True, hide_index=True,
                        height=min(400, 50+len(filtered)*35)
                    )

                    with st.expander(f"📋 Détail — {len(filtered)} anomalie(s)"):
                        for a in filtered[:50]:
                            css   = "card-major" if a.get("Sévérité")=="Majeure" else "card-minor"
                            fix   = f" → <b>{a['Correction suggérée']}</b>" if a.get("Correction suggérée") else ""
                            err_t = a.get("Type d'anomalie","")
                            ia_block = ""
                            if a.get("suggestion_ia"):
                                conf     = a.get("confiance_ia",0)
                                bar_col  = "#0F6E56" if conf>=90 else ("#854F0B" if conf>=70 else "#993C1D")
                                auto_tag = '<span class="tag tag-auto">⚡ Auto</span>' if a.get("auto_corrige") else ""
                                ia_block = (
                                    f'<div style="margin-top:6px;padding-top:6px;border-top:1px solid #E2E8F0">'
                                    f'<span class="tag tag-ai">🤖 IA</span>{auto_tag}'
                                    f' Suggestion : <b>"{a["suggestion_ia"]}"</b>'
                                    f'<div class="conf-bar"><div style="width:{conf}%;background:{bar_col};height:5px;border-radius:3px"></div></div>'
                                    f'<span style="font-size:10px;color:{bar_col}">Confiance : {conf}%</span>'
                                    f'{"<br><i>" + a.get("explication_ia","") + "</i>" if a.get("explication_ia") else ""}'
                                    f'</div>'
                                )
                            st.markdown(
                                f'<div class="{css}">'
                                f'<b>Ligne {a.get("Ligne","")}</b> · <b>{a.get("Champ","")}</b> · '
                                f'<span class="tag tag-{"major" if a.get("Sévérité")=="Majeure" else "minor"}">{a.get("Sévérité","")}</span>'
                                f'<span class="tag" style="background:#E2E8F0;color:#1B3A6B">{err_t}</span>'
                                f'{bc_badge(err_t)}'
                                f'<br>{a.get("Message","")}{fix}'
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
                        f'<b>{a.get("Champ","")}</b> — {a.get("Message","")}</div>',
                        unsafe_allow_html=True
                    )


def reset_session():
    for k in ["step","config","parse_result","validation",
              "merged_result","axe_c_result","saved_session_id"]:
        st.session_state[k] = (1 if k=="step" else {} if k=="config" else None)


# ════════════════════════════════════════════════════════════════════════════
# PAGE
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"# 📁 Sessions Intégration — {active_client_name}")
st.markdown("---")

tab_main, tab_ses = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — NOUVELLE SESSION
# ════════════════════════════════════════════════════════════════════════════
with tab_main:
    for key, default in [
        ("step",1),("config",{}),("parse_result",None),("validation",None),
        ("merged_result",None),("axe_c_result",None),("saved_session_id",None),
    ]:
        if key not in st.session_state: st.session_state[key] = default

    steps = ["Informations","Upload","Structure","Résultats"]
    cols  = st.columns(len(steps))
    for i,(c,n) in enumerate(zip(cols,steps),1):
        with c:
            if i < st.session_state.step:    st.markdown(f"✅ **{n}**")
            elif i == st.session_state.step: st.markdown(f"🔵 **{n}** ←")
            else:                            st.markdown(f"⬜ {n}")
    st.markdown("---")

    # ── Étape 1 ──────────────────────────────────────────────────────────────
    if st.session_state.step == 1:
        st.markdown('<div class="step-header">Étape 1 — Informations</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            default_name = f"{active_pkg_code} — " if active_pkg_code else ""
            session_name = st.text_input(
                "Nom de la session *",
                value=default_name,
                placeholder="MDD Vente — Juin 2026",
            )
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
                            _def_idx = _i; break
                sel_company_name = st.selectbox(
                    "🏢 Société BC *", _names, index=_def_idx, key="ses_company_sel"
                )
                sel_company_id = _company_opts[sel_company_name]
            else:
                st.info("Aucune société BC disponible.")
                sel_company_id, sel_company_name = _default_cid, _default_cname
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
                else:
                    st.session_state.config = {
                        "session_name": session_name.strip(),
                        "client_code":  active_client,
                        "client_name":  active_client_name,
                        "pkg_code":     active_pkg_code,
                        "pkg_name":     active_pkg_name,
                        "notes":        notes,
                        "file_name":    "",
                        "company_id":   sel_company_id,
                        "company_name": sel_company_name,
                    }
                    st.session_state.step = 2; st.rerun()

    # ── Étape 2 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 2:
        cfg = st.session_state.config
        st.markdown('<div class="step-header">Étape 2 — Upload du fichier client</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}**")
        st.info("Format : export **Package de Configuration BC** (.xlsx)")
        uploaded = st.file_uploader("Glissez-déposez ou cliquez", type=["xlsx","xls"], key="upl_s")
        if uploaded:
            st.session_state.config["file_name"] = uploaded.name
            with st.spinner("🔍 Lecture..."): pr = parse_uploaded_file(uploaded); st.session_state.parse_result = pr
            if not pr["success"]:
                for e in pr["errors"]: st.error(f"❌ {e}")
            else:
                s = get_file_summary(pr)
                st.success(f"✅ **{uploaded.name}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Tables de données",   s.get("nb_data_tables",0))
                c2.metric("Tables de référence", s.get("nb_ref_tables",0))
                c3.metric("Lignes",              s.get("total_data_rows",0))
                for t in s.get("data_tables",[]):
                    st.markdown(f'<div class="card-data"><span class="tag tag-data">DONNÉES</span><b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes</b></div>', unsafe_allow_html=True)
                ref_t = pr.get("ref_tables",[]); meta = pr.get("metadata",{}); tr = pr.get("total_rows",{})
                with st.expander(f"📋 Tables de référence ({len(ref_t)})"):
                    for sheet in ref_t:
                        m = meta.get(sheet,{})
                        st.markdown(f'<div class="card-ref"><span class="tag tag-ref">RÉFÉRENCE</span><b>{sheet}</b> — {m.get("label",sheet)} · {tr.get(sheet,0)} valeurs</div>', unsafe_allow_html=True)
                st.markdown("---")
                cb, cv = st.columns([2, 3])
                with cb:
                    if st.button("← Étape précédente", use_container_width=True): st.session_state.step=1; st.rerun()
                with cv:
                    if st.button("🔍 Vérifier la structure →", type="primary", use_container_width=True, disabled=not s.get("data_tables")):
                        with st.spinner("..."): val = validate_file_structure(pr); st.session_state.validation = val
                        st.session_state.step = 3; st.rerun()
        else:
            cb, _ = st.columns([2, 8])
            with cb:
                if st.button("← Étape précédente", use_container_width=True): st.session_state.step=1; st.rerun()

    # ── Étape 3 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 3:
        cfg = st.session_state.config; val = st.session_state.validation; pr = st.session_state.parse_result
        st.markdown('<div class="step-header">Étape 3 — Vérification structurelle</div>', unsafe_allow_html=True)
        sv = val.get("summary",{})
        if val["is_valid"]: st.success(f"**{sv.get('status','✅ Conforme')}**")
        else:               st.error(f"**{sv.get('status','❌ Non conforme')}**")
        for e in val.get("blocking_errors",[]): st.error(e)
        for w in val.get("warnings",[]):        st.warning(w)
        for t in val.get("data_tables",[]):
            st.markdown(f'<div class="card-data"><span class="tag tag-data">DONNÉES</span><b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes · {t["cols"]} champs</b></div>', unsafe_allow_html=True)
        st.markdown("---")
        cb, cv = st.columns([2, 5])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step=2; st.session_state.parse_result=None; st.session_state.validation=None; st.rerun()
        with cv:
            if val["is_valid"]:
                if st.button("🚀 Lancer l'analyse qualité →", type="primary", use_container_width=True):
                    api_key     = get_gemini_api_key()
                    client_code = cfg.get("client_code","")

                    with st.spinner("⏳ Analyse des contraintes..."):
                        _exec_plan = get_execution_plan(
                            profile_code = client_code,
                            company_id   = cfg.get("company_id", ""),
                            package_code = cfg.get("pkg_code", ""),
                        )

                        # ── DEBUG — à supprimer après vérification ────────
                        if _exec_plan.source == "default":
                            st.warning("⚠️ Plan par défaut — extension AL non accessible ou package non sélectionné")
                        else:
                            total_ref = sum(
                                1 for fields in _exec_plan.fields_ref.values()
                                for rid in fields.values() if rid > 0
                            )
                            total_ref_fid = sum(
                                1 for fields in _exec_plan.fields_ref_field.values()
                                for fid in fields.values() if fid > 0
                            )
                            st.info(
                                f"Plan BC — source: {_exec_plan.source} | "
                                f"tables: {len(_exec_plan.tables)} | "
                                f"champs avec refTableId: {total_ref} | "
                                f"champs avec refFieldId: {total_ref_fid}"
                            )
                        # ── FIN DEBUG ─────────────────────────────────────

                        _meta_loader = MetadataLoader(client_code, cfg.get("company_id", ""))
                        _sim_ctx     = SimulationContext()
                        axe_a        = validate_file_axe_a(pr, execution_plan=_exec_plan)

                    with st.spinner("⏳ Vérification des références..."):
                        axe_b = validate_file_axe_b(
                            pr,
                            profile_code    = client_code,
                            company_id      = cfg.get("company_id",""),
                            sim_context     = _sim_ctx,
                            metadata_loader = _meta_loader,
                            execution_plan  = _exec_plan,
                        )

                    axe_c = {"available": False, "total_suggestions":0, "auto_corrected":0, "by_sheet":{}}
                    if api_key:
                        with st.spinner("🤖 Suggestions IA en cours..."):
                            axe_c = validate_file_axe_c(axe_a, axe_b, pr, api_key=api_key)

                    merged = merge_results(axe_a, axe_b, axe_c)
                    st.session_state.merged_result = merged
                    st.session_state.axe_c_result  = axe_c

                    all_r = merged.get("all_anomalies",[])
                    real  = [a for a in all_r if a.get("Ligne",0)>0]
                    st.session_state.config["total"] = len(real)
                    st.session_state.config["major"] = sum(1 for a in real if a.get("Sévérité")=="Majeure")
                    st.session_state.config["minor"] = sum(1 for a in real if a.get("Sévérité")=="Mineure")
                    st.session_state.config["lines"] = axe_a.get("lines_analyzed",0)

                    st.session_state.saved_session_id = None
                    st.session_state.step = 4; st.rerun()
            else:
                st.error("❌ Corrigez les erreurs structurelles.")

    # ── Étape 4 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 4:
        cfg    = st.session_state.config
        merged = st.session_state.merged_result
        axe_c  = st.session_state.axe_c_result or {"available":False}
        pr     = st.session_state.parse_result

        st.markdown('<div class="step-header">Étape 4 — Résultats de l\'analyse qualité</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}** · **{cfg.get('file_name','')}**")

        total = cfg.get("total",0)
        major = cfg.get("major",0)
        minor = cfg.get("minor",0)
        lines = cfg.get("lines",0)
        auto  = axe_c.get("auto_corrected",0)

        c1,c2,c3,c4,c5 = st.columns(5)
        for cw,v,l,col in [
            (c1, lines, "Lignes analysées",  "#1B3A6B"),
            (c2, total, "Total anomalies",    "#993C1D" if total>0 else "#0F6E56"),
            (c3, major, "🔴 Majeures",        "#993C1D" if major>0 else "#0F6E56"),
            (c4, minor, "🟠 Mineures",        "#854F0B" if minor>0 else "#0F6E56"),
            (c5, auto,  "🤖 Corrigées auto",  "#7C3AED" if auto>0 else "#64748B"),
        ]:
            with cw:
                st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{v}</p><p class="stat-lbl">{l}</p></div>', unsafe_allow_html=True)

        st.markdown("---")
        col_leg1, col_leg2, _ = st.columns([2, 2, 6])
        with col_leg1:
            st.markdown('<span class="tag tag-bc">🔴 BC</span> Détecté aussi par BC Config Package', unsafe_allow_html=True)
        with col_leg2:
            st.markdown('<span class="tag tag-plus">⭐ Plus</span> Valeur ajoutée de notre outil', unsafe_allow_html=True)
        st.markdown("---")

        display_unified_results(merged, axe_c)

        if pr:
            with st.expander("👀 Données source"):
                for sn in pr.get("data_tables",[]):
                    df = pr["sheets"].get(sn)
                    if df is not None and not df.empty:
                        meta = pr.get("metadata",{}).get(sn,{})
                        st.markdown(f"**{sn}** — {meta.get('label','')} · {len(df)} lignes")
                        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        st.markdown("---")
        cb, cr, cs, cst = st.columns([2,2,3,3])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step = 3
                for k in ["merged_result","axe_c_result","saved_session_id"]: st.session_state[k] = None
                st.rerun()
        with cr:
            if st.button("🔄 Recommencer", use_container_width=True): reset_session(); st.rerun()
        with cs:
            if st.session_state.saved_session_id:
                st.markdown(f'<div class="save-box">✅ <b>Session sauvegardée</b><br><span style="font-size:11px;color:#64748B">{st.session_state.saved_session_id}</span></div>', unsafe_allow_html=True)
            else:
                if st.button("💾 Sauvegarder la session", type="primary", use_container_width=True):
                    ok, res = save_session({
                        "session_name":    cfg["session_name"],
                        "profile_code":    cfg["client_code"],
                        "file_name":       cfg.get("file_name",""),
                        "notes":           cfg.get("notes",""),
                        "status":          "Analyse terminée" if major>0 else "Terminée",
                        "total_anomalies": total,
                        "major_anomalies": major,
                        "minor_anomalies": minor,
                    })
                    if ok: st.session_state.saved_session_id = res; st.success("✅ Sauvegardée !"); st.rerun()
                    else:  st.error(f"❌ {res}")
        with cst:
            if major==0: st.success("✅ Prêt pour Sprint 7")
            else:        st.warning(f"⚠️ {major} anomalie(s) majeure(s)")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — MES SESSIONS
# ════════════════════════════════════════════════════════════════════════════
with tab_ses:
    st.markdown("### 📋 Mes sessions de contrôle")
    for key, default in [("edit_session_id",None),("confirm_delete_ses",None)]:
        if key not in st.session_state: st.session_state[key] = default

    sessions = get_all_sessions(profile_code=active_client)
    st.markdown("---")

    if not sessions:
        st.info("Aucune session. Créez-en une et cliquez sur **💾 Sauvegarder**.")
    else:
        st.markdown(f"**{len(sessions)} session(s)**")
        for s in sessions:
            sid   = s.get("id",""); status = s.get("status","Nouvelle")
            sc    = STATUS_COLORS.get(status,"#64748B"); si = STATUS_ICONS.get(status,"")
            tot_a = s.get("total_anomalies",0); maj_a = s.get("major_anomalies",0); min_a = s.get("minor_anomalies",0)
            crd   = s.get("created_at","")[:16].replace("T"," ") if s.get("created_at") else ""
            upd   = s.get("updated_at","")[:16].replace("T"," ") if s.get("updated_at") else ""
            fn    = s.get("file_name","")
            an_s  = (f'<span style="color:#993C1D">🔴 {maj_a} majeures</span> · <span style="color:#854F0B">🟠 {min_a} mineures</span>' if tot_a>0 else '<span style="color:#0F6E56">✅ Aucune anomalie</span>')

            ci, ca = st.columns([7, 3])
            with ci:
                st.markdown(f'<div class="card-session"><p class="session-name">{s.get("name","")}</p><p class="session-meta">Client : <b>{s.get("profile_code","")}</b> · <span style="color:{sc};font-weight:500">{si} {status}</span></p><p class="session-meta">{an_s}</p><p class="session-meta">{"📄 "+fn+" · " if fn else ""}🕐 {crd}{"  ·  ✏️ "+upd if upd!=crd else ""}</p></div>', unsafe_allow_html=True)
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
                st.markdown(f"**✏️ Modifier — {s.get('name','')}**")
                e1, e2 = st.columns(2)
                with e1:
                    nn = st.text_input("Nom", value=s.get("name",""), key=f"en_{sid}")
                    ns = st.selectbox("Statut", SESSION_STATUSES, index=SESSION_STATUSES.index(status) if status in SESSION_STATUSES else 0, key=f"est_{sid}")
                with e2:
                    no = st.text_area("Notes", value=s.get("notes",""), height=100, key=f"eno_{sid}")
                sv1, sv2, _ = st.columns([2, 2, 6])
                with sv1:
                    if st.button("💾 Enregistrer", key=f"esv_{sid}", type="primary", use_container_width=True):
                        ok, err = update_session(sid, {"name":nn.strip(),"status":ns,"notes":no.strip()})
                        if ok: st.success("✅ Mis à jour !"); st.session_state.edit_session_id = None; st.rerun()
                        else:  st.error(f"❌ {err}")
                with sv2:
                    if st.button("Annuler", key=f"eca_{sid}", use_container_width=True):
                        st.session_state.edit_session_id = None; st.rerun()
                st.markdown("---")

            if st.session_state.confirm_delete_ses == sid:
                st.warning(f"⚠️ Supprimer **{s.get('name','')}** ? Action irréversible.")
                dy, dn, _ = st.columns([2, 2, 6])
                with dy:
                    if st.button("✅ Confirmer", key=f"dcy_{sid}", type="primary"):
                        ok, err = delete_session(sid)
                        if ok: st.success("Supprimée."); st.session_state.confirm_delete_ses = None; st.rerun()
                        else:  st.error(err)
                with dn:
                    if st.button("❌ Annuler", key=f"dcn_{sid}"):
                        st.session_state.confirm_delete_ses = None; st.rerun()