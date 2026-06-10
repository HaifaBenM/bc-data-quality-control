"""
Page Règles Métier — Sprint 6 update.
Hiérarchie fonctionnelle BC : Module → Table (avec ID) → Champ.
"""
import streamlit as st
from app.db.supabase_client import test_connection
from app.db.profiles_db import get_profiles_for_select
from app.db.rules_db import (
    get_rules_by_master_data, get_rules_for_profile,
    create_rule, delete_rule, toggle_rule, copy_rules_to_profile,
    RULE_TYPES, RULE_TYPES_HELP, SEVERITIES, AUTO_CORRECT_TYPES
)
from app.core.bc_modules_config import (
    BC_MODULES,
    get_module_options, get_module_name,
    get_table_options, get_table_id,
    get_field_options, get_field_info,
    get_master_data_label,
)

st.set_page_config(
    page_title="Règles Métier — BC Quality Control",
    page_icon="⚙️",
    layout="wide"
)

st.markdown("""
<style>
    .rule-card { background:white;border:1px solid #E2E8F0;border-radius:8px;padding:12px 16px;margin-bottom:8px; }
    .rule-card.inactive { opacity:0.5; }
    .rule-label  { font-size:13px;font-weight:600;color:#1B3A6B; }
    .rule-detail { font-size:12px;color:#64748B;margin-top:3px; }
    .badge { display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;margin-right:5px; }
    .badge-major { background:#FAECE7;color:#993C1D; }
    .badge-minor { background:#FAEEDA;color:#854F0B; }
    .badge-info  { background:#EFF6FF;color:#2E6FBF; }
    .badge-auto  { background:#E1F5EE;color:#0F6E56; }
    .badge-type  { background:#EEEDFE;color:#534AB7; }
    .badge-mod   { background:#F0FDF4;color:#166534;font-size:10px; }
    .badge-table { background:#EFF6FF;color:#1D4ED8;font-size:10px; }
    .section-title { font-size:14px;font-weight:600;color:#1B3A6B;padding:8px 0;border-bottom:2px solid #EFF6FF;margin-bottom:10px; }
    .field-info { background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:8px 12px;margin-top:4px;font-size:11px; }
    .module-header { background:linear-gradient(135deg,#1B3A6B,#2E6FBF);color:white;padding:8px 14px;border-radius:6px;margin-bottom:12px;font-weight:600;font-size:13px; }
    #MainMenu { visibility:hidden; } footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

st.markdown("# ⚙️ Règles Métier")
st.markdown("Configurez les règles de validation spécifiques à chaque client.")
st.markdown("---")

connected, msg = test_connection()
if not connected:
    st.error(f"❌ Base de données non connectée : {msg}")
    st.stop()

profiles = get_profiles_for_select()
if not profiles:
    st.warning("Aucun profil client. Créez-en un dans **Profils Clients**.")
    st.stop()

# Pré-sélectionner si on vient de Profils Clients
default_idx = 0
if "selected_profile_for_rules" in st.session_state:
    codes = [p["code"] for p in profiles]
    pre   = st.session_state.get("selected_profile_for_rules","")
    if pre in codes:
        default_idx = codes.index(pre)

selected_label = st.selectbox("Client", [p["label"] for p in profiles], index=default_idx)
selected_code  = next((p["code"] for p in profiles if p["label"]==selected_label), None)
if not selected_code:
    st.stop()

st.markdown("---")

tab1, tab2, tab3 = st.tabs([
    "📋 Règles existantes",
    "➕ Ajouter une règle",
    "📤 Copier depuis un autre client"
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LISTE
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    rules_by_md = get_rules_by_master_data(selected_code)

    if not rules_by_md:
        st.info("Aucune règle pour ce client. Utilisez **'Ajouter une règle'**.")
    else:
        total  = sum(len(r) for r in rules_by_md.values())
        active = sum(1 for rules in rules_by_md.values() for r in rules if r.get("active",True))
        c1,c2,c3 = st.columns(3)
        c1.metric("Total règles",     total)
        c2.metric("Règles actives",   active)
        c3.metric("Règles inactives", total-active)
        st.markdown("---")

        for master_data, rules in rules_by_md.items():
            st.markdown(
                f'<div class="section-title">📌 {master_data} '
                f'<span style="font-weight:400;color:#94A3B8">({len(rules)} règle(s))</span></div>',
                unsafe_allow_html=True
            )
            for rule in rules:
                rule_id   = rule.get("id","")
                is_active = rule.get("active",True)
                severity  = rule.get("severity","Mineure")
                auto      = rule.get("auto_correct",False)
                rule_type = rule.get("rule_type","")
                condition = rule.get("condition","")
                action    = rule.get("action","")
                field     = rule.get("field_name","")
                module_lbl= rule.get("module","")

                sev_class = {"Majeure":"badge-major","Mineure":"badge-minor","Info":"badge-info"}.get(severity,"badge-minor")
                auto_badge= '<span class="badge badge-auto">⚡ Auto</span>' if auto else ""
                mod_badge = f'<span class="badge badge-mod">📦 {module_lbl}</span>' if module_lbl else ""
                tbl_badge = f'<span class="badge badge-table">🗄️ {master_data}</span>'

                parts = []
                if field:     parts.append(f"Champ : <b>{field}</b>")
                if condition: parts.append(f"Si : {condition}")
                if action:    parts.append(f"Alors : {action}")
                detail_html = " · ".join(parts)

                col_r, col_t, col_d = st.columns([7,1,1])
                with col_r:
                    css = "rule-card" + ("" if is_active else " inactive")
                    st.markdown(
                        f'<div class="{css}">'
                        f'<span class="rule-label">{rule.get("label","")}</span>'
                        f'<div style="margin:4px 0">'
                        f'{mod_badge}{tbl_badge}'
                        f'<span class="badge badge-type">{rule_type}</span>'
                        f'<span class="badge {sev_class}">{severity}</span>'
                        f'{auto_badge}</div>'
                        f'<div class="rule-detail">{detail_html}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                with col_t:
                    new_state = st.toggle("Actif", value=is_active, key=f"tgl_{rule_id}", label_visibility="collapsed")
                    if new_state != is_active:
                        ok, _ = toggle_rule(rule_id, new_state)
                        if ok: st.rerun()
                with col_d:
                    if st.button("🗑️", key=f"del_{rule_id}"):
                        ok, _ = delete_rule(rule_id)
                        if ok: st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — AJOUTER
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Ajouter une règle métier")
    st.caption("Sélectionnez le module BC, puis la table, puis le champ cible.")

    col1, col2 = st.columns(2)

    with col1:
        # ── Libellé ───────────────────────────────────────────────────────────
        rule_label = st.text_input(
            "Libellé de la règle *",
            placeholder="Ex : Pays par défaut = France",
            key="rl_label"
        )

        # ── Module BC ─────────────────────────────────────────────────────────
        module_options = ["— Sélectionner un module —"] + get_module_options()
        module_choice  = st.selectbox(
            "Module BC *",
            module_options,
            key="rl_module",
            help="Module fonctionnel BC (Ventes, Achats, Stock, Finance...)"
        )
        selected_module = (
            get_module_name(module_choice)
            if module_choice != "— Sélectionner un module —" else ""
        )

        # ── Table BC ──────────────────────────────────────────────────────────
        selected_table_id    = ""
        selected_table_label = ""
        if selected_module:
            table_options = ["— Sélectionner une table —"] + get_table_options(selected_module)
            st.markdown(
                f'<div class="module-header">'
                f'{BC_MODULES[selected_module]["icon"]} {selected_module} — {len(table_options)-1} table(s)</div>',
                unsafe_allow_html=True
            )
            table_choice = st.selectbox(
                "Table BC * (recherche par ID ou nom)",
                table_options,
                key="rl_table",
                help="Tapez l'ID ou le nom de la table pour filtrer"
            )
            if table_choice != "— Sélectionner une table —":
                selected_table_id    = get_table_id(table_choice)
                selected_table_label = get_master_data_label(selected_module, selected_table_id)

        # ── Champ BC ──────────────────────────────────────────────────────────
        rule_field = ""
        field_info = {}
        if selected_table_id:
            field_options = ["— Sélectionner un champ (optionnel) —"] + get_field_options(selected_module, selected_table_id)
            field_choice  = st.selectbox(
                "Champ BC cible",
                field_options,
                key="rl_field",
                help=f"Champs de la table {selected_table_id} — {selected_table_label}"
            )
            if field_choice != "— Sélectionner un champ (optionnel) —":
                rule_field = field_choice
                field_info = get_field_info(selected_module, selected_table_id, rule_field)

                # Afficher les contraintes du champ
                hints = []
                if field_info.get("req"):              hints.append("✅ Obligatoire")
                if field_info.get("max"):              hints.append(f"📏 Max {field_info['max']} car.")
                if field_info.get("type","Text") != "Text": hints.append(f"🏷️ {field_info['type']}")
                if field_info.get("options"):
                    opts = [o for o in field_info["options"] if str(o).strip()]
                    hints.append(f"📋 Options : {', '.join(opts[:5])}")
                if hints:
                    st.markdown(
                        f'<div class="field-info">{"  ·  ".join(hints)}</div>',
                        unsafe_allow_html=True
                    )

        # ── Type de règle ─────────────────────────────────────────────────────
        rule_type = st.selectbox(
            "Type de règle *",
            RULE_TYPES,
            key="rl_type",
            help="\n".join(f"• {k} : {v}" for k,v in RULE_TYPES_HELP.items())
        )

    with col2:
        rule_cond = st.text_input(
            "Condition (Si...)",
            placeholder="Ex : Si Pays est vide  |  'ancienne valeur'",
            key="rl_cond",
            help="Laissez vide si la règle s'applique toujours."
        )
        rule_action = st.text_area(
            "Action (Alors...)",
            placeholder="Ex : 'FR'  |  'Nouvelle valeur'  |  JSON {clé: valeur}",
            height=100,
            key="rl_action"
        )
        rule_sev  = st.selectbox("Sévérité", SEVERITIES, key="rl_sev")
        rule_auto = st.checkbox(
            "⚡ Correction automatique",
            value=rule_type in AUTO_CORRECT_TYPES,
            key="rl_auto",
            help="Si coché, la correction est appliquée sans validation manuelle."
        )

    # Résumé avant enregistrement
    if selected_module and selected_table_id and rule_label:
        st.markdown("---")
        st.markdown(
            f'<div class="field-info">'
            f'<b>📝 Résumé :</b> {rule_label}<br>'
            f'Module : {BC_MODULES[selected_module]["icon"]} {selected_module} · '
            f'Table : <b>{selected_table_id} — {selected_table_label}</b>'
            f'{" · Champ : <b>" + rule_field + "</b>" if rule_field else ""}'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    if st.button("💾 Enregistrer la règle", type="primary", use_container_width=True, key="rl_save"):
        errors = []
        if not rule_label.strip():    errors.append("Le libellé est obligatoire.")
        if not selected_module:       errors.append("Sélectionnez un module BC.")
        if not selected_table_id:     errors.append("Sélectionnez une table BC.")
        if errors:
            for e in errors: st.error(e)
        else:
            ok, err = create_rule({
                "profile_code": selected_code,
                "label":        rule_label.strip(),
                "module":       selected_module,
                "master_data":  selected_table_label,
                "field_name":   rule_field,
                "rule_type":    rule_type,
                "condition":    rule_cond.strip(),
                "action":       rule_action.strip(),
                "severity":     rule_sev,
                "auto_correct": rule_auto,
                "active":       True,
            })
            if ok:
                st.success(f"✅ Règle **{rule_label}** enregistrée !")
                st.rerun()
            else:
                st.error(f"❌ {err}")

    with st.expander("💡 Guide des types de règles"):
        for rt, help_text in RULE_TYPES_HELP.items():
            auto_txt = " *(correction auto possible)*" if rt in AUTO_CORRECT_TYPES else ""
            st.markdown(f"**{rt}** : {help_text}{auto_txt}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — COPIER
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Copier les règles depuis un autre profil")
    others = [p for p in profiles if p["code"] != selected_code]
    if not others:
        st.info("Aucun autre profil disponible.")
    else:
        source_label = st.selectbox("Copier depuis", [p["label"] for p in others])
        source_code  = next((p["code"] for p in others if p["label"]==source_label), None)
        if source_code:
            src_rules = get_rules_for_profile(source_code)
            st.info(f"Ce profil contient **{len(src_rules)} règle(s)**.")
            if src_rules and st.button(f"📋 Copier {len(src_rules)} règle(s)", type="primary"):
                ok, msg_c, _ = copy_rules_to_profile(source_code, selected_code)
                if ok: st.success(f"✅ {msg_c}"); st.rerun()
                else:  st.error(f"❌ {msg_c}")
