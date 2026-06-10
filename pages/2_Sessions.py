"""
Page Sessions — Sprint 6.
Analyse complète : Axe A + B + C (Gemini IA) + D (règles métier).
Fix clés dupliquées : paramètre uid dans display_axe_results.
"""
import streamlit as st
import pandas as pd
from app.core.file_parser import parse_uploaded_file, get_file_summary
from app.core.structure_validator import validate_file_structure
from app.core.validator_axe_a import validate_file_axe_a, get_anomalies_dataframe
from app.core.validator_axe_b import validate_file_axe_b
from app.core.validator_axe_c import validate_file_axe_c, get_gemini_api_key, is_gemini_available
from app.core.validator_axe_d import validate_file_axe_d
from app.db.profiles_db import get_profiles_for_select
from app.db.rules_db import get_active_rules_for_profile
from app.db.sessions_db import (
    save_session, update_session, delete_session,
    get_all_sessions, SESSION_STATUSES, STATUS_COLORS, STATUS_ICONS
)


# ── Erreurs détectées par BC Config Package (pour badging dans les résultats) ──
BC_DETECTED = {
    "Longueur maximale dépassée",
    "Valeur Option non autorisée",
    "Type incorrect (entier attendu)",
    "Type incorrect (décimal attendu)",
    "Type incorrect (booléen attendu)",
    "Format de date incorrect",
}
# Tout le reste = valeur ajoutée de notre outil uniquement

def bc_badge(error_type: str) -> str:
    """Retourne le badge HTML : BC si détecté par BC, ⭐ si valeur ajoutée."""
    if error_type in BC_DETECTED:
        return '<span class="tag tag-bc" title="Détecté aussi par BC Config Package">🔴 BC</span>'
    return '<span class="tag tag-plus" title="Détecté uniquement par notre outil">⭐ Plus</span>'

st.set_page_config(page_title="Sessions — BC Quality Control", page_icon="📁", layout="wide")

st.markdown("""
<style>
    .step-header { background:linear-gradient(135deg,#1B3A6B,#2E6FBF);color:white;padding:.75rem 1.25rem;border-radius:8px;margin-bottom:1rem;font-weight:600; }
    .card-data  { background:#E1F5EE;border-left:4px solid #0F6E56;border-radius:8px;padding:12px 16px;margin-bottom:8px; }
    .card-ref   { background:#EFF6FF;border-left:4px solid #2E6FBF;border-radius:8px;padding:10px 14px;margin-bottom:6px; }
    .card-rule  { background:#EEEDFE;border-left:3px solid #534AB7;border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:12px; }
    .card-major { background:#FAECE7;border-left:4px solid #993C1D;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-minor { background:#FAEEDA;border-left:4px solid #854F0B;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-info  { background:#EFF6FF;border-left:4px solid #2E6FBF;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-ai    { background:#F5F3FF;border-left:4px solid #7C3AED;border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px; }
    .card-session { background:white;border:1px solid #E2E8F0;border-radius:10px;padding:14px 18px;margin-bottom:4px; }
    .session-name { font-size:14px;font-weight:600;color:#1B3A6B;margin:0; }
    .session-meta { font-size:12px;color:#64748B;margin:4px 0 0; }
    .stat-box { background:white;border:1px solid #E2E8F0;border-radius:8px;padding:10px;text-align:center; }
    .stat-num { font-size:1.6rem;font-weight:700;margin:0; }
    .stat-lbl { font-size:10px;color:#64748B;margin:0; }
    .save-box { background:#E1F5EE;border:1px solid #0F6E56;border-radius:8px;padding:10px 14px;margin:4px 0; }
    .conf-bar { height:5px;border-radius:3px;background:#E2E8F0;margin:3px 0; }
    .tag { display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;margin-right:4px; }
    .tag-major { background:#993C1D;color:white; } .tag-minor { background:#854F0B;color:white; }
    .tag-info  { background:#2E6FBF;color:white; } .tag-data  { background:#0F6E56;color:white; }
    .tag-ref   { background:#2E6FBF;color:white; } .tag-ai    { background:#7C3AED;color:white; }
    .tag-auto  { background:#0F6E56;color:white; }
    .tag-bc   { background:#1B3A6B;color:white;font-size:9px; }
    .tag-plus { background:#854F0B;color:white;font-size:9px; }
    #MainMenu { visibility:hidden; } footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS — définis avant tout appel
# ════════════════════════════════════════════════════════════════════════════

def display_axe_results(axe_result: dict, axe_label: str, uid: str = "x"):
    """
    Affiche les résultats d'un axe de validation.
    uid : suffixe unique (ex: 'a', 'b', 'd') pour éviter les clés Streamlit dupliquées.
    """
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
        a = by_sheet[s]; nb = len([x for x in a if x.get("Ligne",0)>0])
        nmaj = sum(1 for x in a if x["Sévérité"]=="Majeure")
        icon = "🔴" if nmaj>0 else ("🟠" if nb>0 else "✅")
        tab_labels.append(f"{icon} {s} ({nb})")

    if not tab_labels:
        return

    for tab, sn in zip(st.tabs(tab_labels), sheet_names):
        with tab:
            anomalies      = by_sheet.get(sn, [])
            real_anomalies = [a for a in anomalies if a.get("Ligne",0) > 0]
            info_anomalies = [a for a in anomalies if a.get("Ligne",0) == 0]

            if not real_anomalies and not info_anomalies:
                st.success("✅ Aucune anomalie."); continue

            if real_anomalies:
                t1, t2, t3 = st.columns(3)
                t1.metric("Anomalies", len(real_anomalies))
                t2.metric("🔴", sum(1 for a in real_anomalies if a["Sévérité"]=="Majeure"))
                t3.metric("🟠", sum(1 for a in real_anomalies if a["Sévérité"]=="Mineure"))

                sevs = sorted(set(a["Sévérité"] for a in real_anomalies))
                # Clé unique : uid + sheet normalisé → jamais de doublon entre axes
                safe_sn    = sn.replace(" ","_").replace("/","_")
                widget_key = f"ms_{uid}_{safe_sn}"
                filt = st.multiselect("Filtrer", sevs, default=sevs, key=widget_key)
                filtered = [a for a in real_anomalies if a["Sévérité"] in filt]

                if filtered:
                    df_an = get_anomalies_dataframe(filtered)
                    def cr(row):
                        s = row.get("Sévérité","")
                        if s=="Majeure": return ["background-color:#FAECE7"]*len(row)
                        if s=="Mineure": return ["background-color:#FAEEDA"]*len(row)
                        return [""]*len(row)
                    st.dataframe(
                        df_an.style.apply(cr, axis=1),
                        use_container_width=True, hide_index=True,
                        height=min(400, 50+len(filtered)*35)
                    )
                    with st.expander("📋 Détail"):
                        for a in filtered[:50]:
                            css = "card-major" if a["Sévérité"]=="Majeure" else "card-minor"
                            fix = f" → <b>{a['Correction suggérée']}</b>" if a.get("Correction suggérée") else ""
                            rule_tag = f'<span class="tag" style="background:#EEEDFE;color:#534AB7">⚙️ {a.get("Règle","")}</span>' if a.get("Règle") else ""
                            st.markdown(
                                f'<div class="{css}"><b>Ligne {a["Ligne"]}</b> · <b>{a["Champ"]}</b> · '
                                f'<span class="tag tag-{"major" if a["Sévérité"]=="Majeure" else "minor"}">{a["Sévérité"]}</span>'
                                f'<span class="tag" style="background:#E2E8F0;color:#1B3A6B">{a["Type d\'anomalie"]}</span>'
                                f'{bc_badge(a["Type d\'anomalie"])}{rule_tag}'
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


def display_axe_c_results(axe_c: dict):
    """Affichage spécifique Axe C avec barres de confiance."""
    if not axe_c.get("available"):
        st.warning("⚠️ **Axe C non disponible** — Clé API Gemini non configurée.")
        st.info("""
**Pour activer l'IA :**
1. Clé gratuite sur [aistudio.google.com](https://aistudio.google.com)
2. Streamlit Cloud → **Settings → Secrets** :
```
GEMINI_API_KEY = "AIzaSy..."
```
3. Redéployez l'application.
        """)
        return

    total = axe_c.get("total_suggestions", 0)
    auto  = axe_c.get("auto_corrected", 0)
    high  = axe_c.get("high_confidence", 0)
    low   = axe_c.get("low_confidence", 0)

    if total == 0:
        st.success("✅ Aucune suggestion IA retournée par Gemini.")
        st.caption(
            "Gemini n'a pas trouvé de corrections évidentes, ou les anomalies "
            "détectées n'ont pas de valeur source analysable. "
            "L'IA n'analyse que les cellules avec une valeur non vide."
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Suggestions IA",    total)
    c2.metric("⚡ Auto-corrigées", auto)
    c3.metric("🟢 Haute confiance", high)
    c4.metric("🟡 Basse confiance", low)

    by_sheet = axe_c.get("by_sheet", {})
    for sn, anomalies in by_sheet.items():
        enriched = [a for a in anomalies if a.get("suggestion_ia") and a.get("Ligne",0)>0]
        if not enriched: continue

        st.markdown(f"**{sn}** — {len(enriched)} suggestion(s)")
        for a in enriched:
            conf    = a.get("confiance_ia", 0)
            suggest = a.get("suggestion_ia", "")
            explic  = a.get("explication_ia", "")
            is_auto = a.get("auto_corrige", False)
            bar_col = "#0F6E56" if conf>=90 else ("#854F0B" if conf>=70 else "#993C1D")
            auto_tag = '<span class="tag tag-auto">⚡ Auto</span>' if is_auto else ""
            st.markdown(
                f'<div class="card-ai">'
                f'<b>Ligne {a["Ligne"]}</b> · <b>{a["Champ"]}</b> · '
                f'<span class="tag tag-ai">🤖 IA</span>{auto_tag}'
                f'<br>"{a["Valeur"]}" → <b>"{suggest}"</b>'
                f'<div class="conf-bar"><div style="width:{conf}%;background:{bar_col};height:5px;border-radius:3px"></div></div>'
                f'<span style="font-size:10px;color:{bar_col}">Confiance : {conf}%</span>'
                f'{"<br><i>"+explic+"</i>" if explic else ""}'
                f'</div>',
                unsafe_allow_html=True
            )


def reset_session():
    for k in ["step","config","parse_result","validation",
              "axe_a_result","axe_b_result","axe_c_result","axe_d_result","saved_session_id"]:
        st.session_state[k] = (1 if k=="step" else {} if k=="config" else None)


# ════════════════════════════════════════════════════════════════════════════
# PAGE
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# 📁 Sessions de contrôle")
st.markdown("---")

tab1, tab2 = st.tabs(["➕ Nouvelle session", "📋 Mes sessions"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    for key, default in [
        ("step",1),("config",{}),("parse_result",None),("validation",None),
        ("axe_a_result",None),("axe_b_result",None),
        ("axe_c_result",None),("axe_d_result",None),("saved_session_id",None),
    ]:
        if key not in st.session_state: st.session_state[key] = default

    steps = ["Informations","Upload","Structure","Analyse A+B+C+D"]
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
        col1,col2 = st.columns(2)
        with col1:
            session_name = st.text_input("Nom de la session *", placeholder="ABC - Clients - Juin 2026")
            profiles = get_profiles_for_select()
            if profiles:
                opts = ["— Sélectionner un client —"]+[p["label"] for p in profiles]
                choice = st.selectbox("Client *", opts)
                selected = next((p for p in profiles if p["label"]==choice), None)
            else:
                st.warning("Aucun profil. Créez-en un dans **Profils Clients**."); selected=None
        with col2:
            notes = st.text_area("Notes", height=60)
            if selected:
                rules = get_active_rules_for_profile(selected["code"])
                if rules:
                    st.markdown(f"**⚙️ {len(rules)} règle(s) :**")
                    for r in rules[:3]:
                        st.markdown(f'<div class="card-rule"><b>{r.get("label","")}</b> — {r.get("rule_type","")}</div>', unsafe_allow_html=True)
                    if len(rules)>3: st.caption(f"+{len(rules)-3} autre(s)")
                else: st.info("Aucune règle.")
            st.markdown("🤖 **Axe C IA :** " + ("✅ Gemini configuré" if is_gemini_available() else "⚠️ Clé Gemini manquante"))
        st.markdown("---")
        _,col_btn = st.columns([8,2])
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
                    st.session_state.step=2; st.rerun()

    # ── Étape 2 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 2:
        cfg = st.session_state.config
        st.markdown('<div class="step-header">Étape 2 — Upload du fichier client</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}** · **{cfg['nb_rules']} règle(s)**")
        st.info("Format : export **Package de Configuration BC** (.xlsx)")
        uploaded = st.file_uploader("Glissez-déposez ou cliquez", type=["xlsx","xls"], key="upl_s6")
        if uploaded:
            st.session_state.config["file_name"] = uploaded.name
            with st.spinner("🔍 Lecture..."): pr = parse_uploaded_file(uploaded); st.session_state.parse_result=pr
            if not pr["success"]:
                for e in pr["errors"]: st.error(f"❌ {e}")
            else:
                s = get_file_summary(pr)
                st.success(f"✅ **{uploaded.name}**")
                c1,c2,c3 = st.columns(3)
                c1.metric("Tables données",s.get("nb_data_tables",0)); c2.metric("Références",s.get("nb_ref_tables",0)); c3.metric("Lignes",s.get("total_data_rows",0))
                for t in s.get("data_tables",[]):
                    st.markdown(f'<div class="card-data"><span class="tag tag-data">DONNÉES</span><b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes</b></div>', unsafe_allow_html=True)
                ref_t = pr.get("ref_tables",[]); meta=pr.get("metadata",{}); tr=pr.get("total_rows",{})
                with st.expander(f"📋 Références ({len(ref_t)}) — utilisées pour Axe B"):
                    for sheet in ref_t:
                        m=meta.get(sheet,{})
                        st.markdown(f'<div class="card-ref"><span class="tag tag-ref">RÉFÉRENCE</span><b>{sheet}</b> — {m.get("label",sheet)} · {tr.get(sheet,0)} valeurs</div>', unsafe_allow_html=True)
                st.markdown("---")
                cb,cv = st.columns([2,3])
                with cb:
                    if st.button("← Étape précédente", use_container_width=True): st.session_state.step=1; st.rerun()
                with cv:
                    if st.button("🔍 Vérifier la structure →", type="primary", use_container_width=True, disabled=not s.get("data_tables")):
                        with st.spinner("..."): val=validate_file_structure(pr); st.session_state.validation=val
                        st.session_state.step=3; st.rerun()
        else:
            cb,_ = st.columns([2,8])
            with cb:
                if st.button("← Étape précédente", use_container_width=True): st.session_state.step=1; st.rerun()

    # ── Étape 3 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 3:
        cfg=st.session_state.config; val=st.session_state.validation; pr=st.session_state.parse_result
        st.markdown('<div class="step-header">Étape 3 — Vérification structurelle</div>', unsafe_allow_html=True)
        sv=val.get("summary",{})
        if val["is_valid"]: st.success(f"**{sv.get('status','✅')}**")
        else:               st.error(f"**{sv.get('status','❌')}**")
        for e in val.get("blocking_errors",[]): st.error(e)
        for w in val.get("warnings",[]): st.warning(w)
        for t in val.get("data_tables",[]):
            st.markdown(f'<div class="card-data"><span class="tag tag-data">DONNÉES</span><b>{t["sheet"]}</b> — {t["label"]} · <b>{t["rows"]} lignes · {t["cols"]} champs</b></div>', unsafe_allow_html=True)
        st.markdown("---")
        cb,cv = st.columns([2,5])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step=2; st.session_state.parse_result=None; st.session_state.validation=None; st.rerun()
        with cv:
            if val["is_valid"]:
                gemini_ok = is_gemini_available()
                btn_lbl = ("🚀 Lancer l'analyse complète (Axe A + B + C + D)" if gemini_ok
                           else "🚀 Lancer l'analyse complète (Axe A + B + D)")
                if st.button(btn_lbl, type="primary", use_container_width=True):
                    api_key      = get_gemini_api_key()
                    active_rules = cfg.get("active_rules",[])
                    client_code  = cfg.get("client_code","")
                    with st.spinner("⏳ Axe A..."):
                        axe_a=validate_file_axe_a(pr); st.session_state.axe_a_result=axe_a
                    with st.spinner("⏳ Axe B..."):
                        axe_b=validate_file_axe_b(pr, profile_code=client_code); st.session_state.axe_b_result=axe_b
                    if api_key:
                        with st.spinner("🤖 Axe C (IA)..."):
                            axe_c=validate_file_axe_c(axe_a,axe_b,pr,api_key=api_key); st.session_state.axe_c_result=axe_c
                    else:
                        st.session_state.axe_c_result={"available":False}
                    if active_rules:
                        with st.spinner("⚙️ Axe D (règles)..."):
                            axe_d=validate_file_axe_d(pr,active_rules); st.session_state.axe_d_result=axe_d
                    else:
                        st.session_state.axe_d_result={"total_anomalies":0,"major":0,"minor":0,"info":0,"lines_analyzed":0,"by_sheet":{},"all_anomalies":[],"no_rules":True}
                    st.session_state.saved_session_id=None; st.session_state.step=4; st.rerun()
            else:
                st.error("❌ Corrigez les erreurs structurelles.")

    # ── Étape 4 ──────────────────────────────────────────────────────────────
    elif st.session_state.step == 4:
        cfg=st.session_state.config
        axe_a=st.session_state.axe_a_result
        axe_b=st.session_state.axe_b_result
        axe_c=st.session_state.axe_c_result or {"available":False}
        axe_d=st.session_state.axe_d_result or {"total_anomalies":0,"major":0,"minor":0,"info":0,"by_sheet":{},"all_anomalies":[]}
        pr=st.session_state.parse_result

        st.markdown('<div class="step-header">Étape 4 — Résultats de l\'analyse qualité</div>', unsafe_allow_html=True)
        st.caption(f"Session : **{cfg['session_name']}** · Client : **{cfg['client_name']}** · **{cfg.get('file_name','')}**")

        a_tot=axe_a.get("total_anomalies",0); b_tot=axe_b.get("total_anomalies",0)
        c_tot=axe_c.get("total_suggestions",0); d_tot=axe_d.get("total_anomalies",0)
        a_maj=axe_a.get("major",0); b_maj=axe_b.get("major",0); d_maj=axe_d.get("major",0)
        a_min=axe_a.get("minor",0); b_min=axe_b.get("minor",0); d_min=axe_d.get("minor",0)
        total=a_tot+b_tot+d_tot; major=a_maj+b_maj+d_maj; minor=a_min+b_min+d_min
        c_auto=axe_c.get("auto_corrected",0); lines=axe_a.get("lines_analyzed",0)

        c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
        for cw,v,l,col in [
            (c1,lines,"Lignes","#1B3A6B"),
            (c2,total,"Total","#993C1D" if total>0 else "#0F6E56"),
            (c3,major,"🔴 Maj.","#993C1D" if major>0 else "#0F6E56"),
            (c4,a_tot,"🔵 Axe A","#534AB7" if a_tot>0 else "#64748B"),
            (c5,b_tot,"🟢 Axe B","#0F6E56" if b_tot>0 else "#64748B"),
            (c6,c_tot,"🤖 Axe C","#7C3AED" if c_tot>0 else "#64748B"),
            (c7,d_tot,"⚙️ Axe D","#854F0B" if d_tot>0 else "#64748B"),
        ]:
            with cw:
                st.markdown(f'<div class="stat-box"><p class="stat-num" style="color:{col}">{v}</p><p class="stat-lbl">{l}</p></div>', unsafe_allow_html=True)

        st.markdown("---")

        if total==0 and c_tot==0:
            st.success("🎉 **Aucune anomalie sur les 4 axes !**")
        else:
            rt1,rt2,rt3,rt4,rt5 = st.tabs([
                "📊 Résumé",
                f"🔵 Axe A ({a_tot})",
                f"🟢 Axe B ({b_tot})",
                f"🤖 Axe C — IA ({c_tot})",
                f"⚙️ Axe D — Règles ({d_tot})",
            ])
            with rt1:
                st.markdown("### Vue consolidée")
                if c_auto>0: st.info(f"🤖 **{c_auto} correction(s) auto-appliquée(s) par l'IA** (confiance ≥ 90%)")
                all_an = axe_a.get("all_anomalies",[])+axe_b.get("all_anomalies",[])+axe_d.get("all_anomalies",[])
                real   = [a for a in all_an if a.get("Ligne",0)>0]
                infos  = [a for a in all_an if a.get("Ligne",0)==0]
                if real:
                    def cs(row):
                        s=row.get("Sévérité","")
                        if s=="Majeure": return ["background-color:#FAECE7"]*len(row)
                        if s=="Mineure": return ["background-color:#FAEEDA"]*len(row)
                        return [""]*len(row)
                    st.dataframe(get_anomalies_dataframe(real).style.apply(cs,axis=1), use_container_width=True, hide_index=True, height=min(500,50+len(real)*35))
                if infos:
                    st.markdown("---")
                    for a in infos:
                        st.markdown(f'<div class="card-info"><span class="tag tag-info">INFO</span><b>{a["Champ"]}</b> — {a["Message"]}</div>', unsafe_allow_html=True)

            with rt2: display_axe_results(axe_a, "Axe A", uid="a")
            with rt3: display_axe_results(axe_b, "Axe B", uid="b")
            with rt4: display_axe_c_results(axe_c)
            with rt5:
                if axe_d.get("no_rules"):
                    st.warning(
                        "⚠️ **Aucune règle métier configurée** pour ce client. "
                        "Allez dans **Règles Métier** pour ajouter des règles."
                    )
                    st.info(
                        "**Règles à créer pour déclencher l'Axe D sur le fichier de test :**\n\n"
                        "**Règle 1** — Valeur par défaut\n"
                        "- Champ : `Code pays/région` · Condition : `Si vide` · Action : `FR`\n\n"
                        "**Règle 2** — Transformation\n"
                        "- Champ : `Nom` · Condition : `'woodgrove bank'` · Action : `'Woodgrove Bank'`"
                    )
                else:
                    display_axe_results(axe_d, "Axe D", uid="d")

        if pr:
            with st.expander("👀 Données source"):
                for sn in pr.get("data_tables",[]):
                    df=pr["sheets"].get(sn)
                    if df is not None and not df.empty:
                        meta=pr.get("metadata",{}).get(sn,{})
                        st.markdown(f"**{sn}** — {meta.get('label','')} · {len(df)} lignes")
                        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

        st.markdown("---")
        cb,cr,cs,cst = st.columns([2,2,3,3])
        with cb:
            if st.button("← Étape précédente", use_container_width=True):
                st.session_state.step=3
                for k in ["axe_a_result","axe_b_result","axe_c_result","axe_d_result","saved_session_id"]:
                    st.session_state[k]=None
                st.rerun()
        with cr:
            if st.button("🔄 Recommencer", use_container_width=True): reset_session(); st.rerun()
        with cs:
            if st.session_state.saved_session_id:
                st.markdown(f'<div class="save-box">✅ <b>Sauvegardée</b><br><span style="font-size:11px;color:#64748B">{st.session_state.saved_session_id}</span></div>', unsafe_allow_html=True)
            else:
                if st.button("💾 Sauvegarder la session", type="primary", use_container_width=True):
                    ok,res=save_session({
                        "session_name":    cfg["session_name"],
                        "profile_code":    cfg["client_code"],
                        "file_name":       cfg.get("file_name",""),
                        "notes":           cfg.get("notes",""),
                        "status":          "Analyse terminée" if major>0 else "Terminée",
                        "total_anomalies": total,
                        "major_anomalies": major,
                        "minor_anomalies": minor,
                    })
                    if ok: st.session_state.saved_session_id=res; st.success("✅ Sauvegardée !"); st.rerun()
                    else:  st.error(f"❌ {res}")
        with cst:
            if major==0: st.success("✅ Prêt pour Sprint 7")
            else:        st.warning(f"⚠️ {major} anomalie(s) majeure(s)")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — MES SESSIONS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 📋 Mes sessions de contrôle")
    for key,default in [("edit_session_id",None),("confirm_delete_ses",None)]:
        if key not in st.session_state: st.session_state[key]=default

    profiles = get_profiles_for_select()
    cf1,_ = st.columns([3,7])
    with cf1:
        fopts = ["Tous les clients"]+[p["label"] for p in profiles]
        fch   = st.selectbox("Filtrer par client", fopts, key="filter_ses")
    fcode = next((p["code"] for p in profiles if p["label"]==fch),None) if fch!="Tous les clients" else None
    sessions = get_all_sessions(profile_code=fcode)
    st.markdown("---")

    if not sessions:
        st.info("Aucune session. Créez-en une et cliquez sur **💾 Sauvegarder**.")
    else:
        st.markdown(f"**{len(sessions)} session(s)**")
        for s in sessions:
            sid   = s.get("id",""); status=s.get("status","Nouvelle")
            sc    = STATUS_COLORS.get(status,"#64748B"); si=STATUS_ICONS.get(status,"")
            tot_a = s.get("total_anomalies",0); maj_a=s.get("major_anomalies",0); min_a=s.get("minor_anomalies",0)
            crd   = s.get("created_at","")[:16].replace("T"," ") if s.get("created_at") else ""
            upd   = s.get("updated_at","")[:16].replace("T"," ") if s.get("updated_at") else ""
            fn    = s.get("file_name","")
            an_s  = (f'<span style="color:#993C1D">🔴 {maj_a}</span> · <span style="color:#854F0B">🟠 {min_a}</span>' if tot_a>0 else '<span style="color:#0F6E56">✅ Aucune anomalie</span>')

            ci,ca = st.columns([7,3])
            with ci:
                st.markdown(f'<div class="card-session"><p class="session-name">{s.get("name","")}</p><p class="session-meta">Client : <b>{s.get("profile_code","")}</b> · <span style="color:{sc};font-weight:500">{si} {status}</span></p><p class="session-meta">{an_s}</p><p class="session-meta">{"📄 "+fn+" · " if fn else ""}🕐 {crd}{"  ·  ✏️ "+upd if upd!=crd else ""}</p></div>', unsafe_allow_html=True)
            with ca:
                st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
                ce,cd = st.columns(2)
                with ce:
                    if st.button("✏️ Éditer", key=f"es_{sid}", use_container_width=True):
                        st.session_state.edit_session_id=sid; st.session_state.confirm_delete_ses=None
                with cd:
                    if st.button("🗑️", key=f"ds_{sid}", use_container_width=True):
                        st.session_state.confirm_delete_ses=sid; st.session_state.edit_session_id=None
                st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.edit_session_id == sid:
                st.markdown("---")
                st.markdown(f"**✏️ Modifier — {s.get('name','')}**")
                e1,e2 = st.columns(2)
                with e1:
                    nn = st.text_input("Nom", value=s.get("name",""), key=f"en_{sid}")
                    ns = st.selectbox("Statut", SESSION_STATUSES, index=SESSION_STATUSES.index(status) if status in SESSION_STATUSES else 0, key=f"est_{sid}")
                with e2:
                    no = st.text_area("Notes", value=s.get("notes",""), height=100, key=f"eno_{sid}")
                sv1,sv2,_ = st.columns([2,2,6])
                with sv1:
                    if st.button("💾 Enregistrer", key=f"esv_{sid}", type="primary", use_container_width=True):
                        ok,err=update_session(sid,{"name":nn.strip(),"status":ns,"notes":no.strip()})
                        if ok: st.success("✅ Mis à jour !"); st.session_state.edit_session_id=None; st.rerun()
                        else:  st.error(f"❌ {err}")
                with sv2:
                    if st.button("Annuler", key=f"eca_{sid}", use_container_width=True):
                        st.session_state.edit_session_id=None; st.rerun()
                st.markdown("---")

            if st.session_state.confirm_delete_ses == sid:
                st.warning(f"⚠️ Supprimer **{s.get('name','')}** ? Action irréversible.")
                dy,dn,_ = st.columns([2,2,6])
                with dy:
                    if st.button("✅ Confirmer", key=f"dcy_{sid}", type="primary"):
                        ok,err=delete_session(sid)
                        if ok: st.success("Supprimée."); st.session_state.confirm_delete_ses=None; st.rerun()
                        else:  st.error(err)
                with dn:
                    if st.button("❌ Annuler", key=f"dcn_{sid}"):
                        st.session_state.confirm_delete_ses=None; st.rerun()
