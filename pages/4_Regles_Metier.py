"""
Page Règles Métier — Sprint 4 update.
Champ BC cible = liste déroulante selon la Master Data sélectionnée.
"""
import streamlit as st
from app.db.supabase_client import test_connection
from app.db.profiles_db import get_profiles_for_select
from app.db.rules_db import (
    get_rules_by_master_data, get_rules_for_profile,
    create_rule, delete_rule, toggle_rule, copy_rules_to_profile,
    RULE_TYPES, RULE_TYPES_HELP, SEVERITIES, AUTO_CORRECT_TYPES
)
from app.core.validator_axe_a import FIELD_DEFS

st.set_page_config(
    page_title="Règles Métier — BC Quality Control",
    page_icon="⚙️",
    layout="wide"
)

st.markdown("""
<style>
    .rule-card {
        background: white; border: 1px solid #E2E8F0;
        border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;
    }
    .rule-card.inactive { opacity: 0.5; }
    .rule-label  { font-size: 13px; font-weight: 600; color: #1B3A6B; }
    .rule-detail { font-size: 12px; color: #64748B; margin-top: 3px; }
    .badge {
        display: inline-block; font-size: 10px; font-weight: 600;
        padding: 2px 7px; border-radius: 4px; margin-right: 5px;
    }
    .badge-major { background: #FAECE7; color: #993C1D; }
    .badge-minor { background: #FAEEDA; color: #854F0B; }
    .badge-info  { background: #EFF6FF; color: #2E6FBF; }
    .badge-auto  { background: #E1F5EE; color: #0F6E56; }
    .badge-type  { background: #EEEDFE; color: #534AB7; }
    .section-title {
        font-size: 14px; font-weight: 600; color: #1B3A6B;
        padding: 8px 0; border-bottom: 2px solid #EFF6FF;
        margin-bottom: 10px;
    }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
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

# Pré-sélectionner si on vient de la page Profils Clients
default_idx = 0
if "selected_profile_for_rules" in st.session_state:
    codes = [p["code"] for p in profiles]
    pre   = st.session_state.get("selected_profile_for_rules", "")
    if pre in codes:
        default_idx = codes.index(pre)

selected_label = st.selectbox(
    "Client",
    [p["label"] for p in profiles],
    index=default_idx
)
selected_code = next(
    (p["code"] for p in profiles if p["label"] == selected_label), None
)
if not selected_code:
    st.stop()

st.markdown("---")

# ── Mapping Master Data label → table_id BC ───────────────────────────────────
# Permet de charger les champs depuis FIELD_DEFS selon la Master Data choisie
MASTER_DATA_TABLE_MAP = {
    "Clients":          "18",
    "Fournisseurs":     "23",
    "Articles":         "27",
    "Plan comptable":   "15",
    "Général":          None,
}


def get_fields_for_master_data(master_data_name: str) -> list[str]:
    """
    Retourne la liste des champs BC pour une Master Data donnée.
    Source : FIELD_DEFS de validator_axe_a.py
    """
    table_id = MASTER_DATA_TABLE_MAP.get(master_data_name)
    if not table_id or table_id not in FIELD_DEFS:
        return []
    return sorted(FIELD_DEFS[table_id].keys())


tab1, tab2, tab3 = st.tabs([
    "📋 Règles existantes",
    "➕ Ajouter une règle",
    "📤 Copier depuis un autre client"
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — LISTE DES RÈGLES
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    rules_by_md = get_rules_by_master_data(selected_code)

    if not rules_by_md:
        st.info("Aucune règle pour ce client. Utilisez **'Ajouter une règle'**.")
    else:
        total  = sum(len(r) for r in rules_by_md.values())
        active = sum(
            1 for rules in rules_by_md.values()
            for r in rules if r.get("active", True)
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Total règles",     total)
        c2.metric("Règles actives",   active)
        c3.metric("Règles inactives", total - active)
        st.markdown("---")

        for master_data, rules in rules_by_md.items():
            st.markdown(
                f'<div class="section-title">📌 {master_data} '
                f'<span style="font-weight:400;color:#94A3B8">'
                f'({len(rules)} règle(s))</span></div>',
                unsafe_allow_html=True
            )

            for rule in rules:
                rule_id   = rule.get("id", "")
                is_active = rule.get("active", True)
                severity  = rule.get("severity", "Mineure")
                auto      = rule.get("auto_correct", False)
                rule_type = rule.get("rule_type", "")
                condition = rule.get("condition", "")
                action    = rule.get("action", "")
                field     = rule.get("field_name", "")

                sev_class = {
                    "Majeure": "badge-major",
                    "Mineure": "badge-minor",
                    "Info":    "badge-info"
                }.get(severity, "badge-minor")

                parts = []
                if field:     parts.append(f"Champ : <b>{field}</b>")
                if condition: parts.append(f"Si : {condition}")
                if action:    parts.append(f"Alors : {action}")
                detail_html = " · ".join(parts)

                auto_badge = (
                    '<span class="badge badge-auto">⚡ Auto</span>'
                    if auto else ""
                )

                col_r, col_t, col_d = st.columns([7, 1, 1])
                with col_r:
                    css = "rule-card" + ("" if is_active else " inactive")
                    st.markdown(
                        f'<div class="{css}">'
                        f'<span class="rule-label">{rule.get("label","")}</span>'
                        f'<div style="margin:4px 0">'
                        f'<span class="badge badge-type">{rule_type}</span>'
                        f'<span class="badge {sev_class}">{severity}</span>'
                        f'{auto_badge}'
                        f'</div>'
                        f'<div class="rule-detail">{detail_html}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                with col_t:
                    new_state = st.toggle(
                        "Actif", value=is_active,
                        key=f"tgl_{rule_id}",
                        label_visibility="collapsed"
                    )
                    if new_state != is_active:
                        ok, err = toggle_rule(rule_id, new_state)
                        if ok: st.rerun()
                with col_d:
                    if st.button("🗑️", key=f"del_{rule_id}"):
                        ok, err = delete_rule(rule_id)
                        if ok: st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — AJOUTER UNE RÈGLE
# ════════════════════════════════════════════════════════════════════════════
with tab2:

    st.markdown("### Ajouter une règle métier")

    col1, col2 = st.columns(2)

    with col1:
        rule_label = st.text_input(
            "Libellé de la règle *",
            placeholder="Ex : Pays par défaut = France"
        )

        # Liste des Master Data disponibles
        master_data_options = list(MASTER_DATA_TABLE_MAP.keys())
        rule_md = st.selectbox(
            "Master Data *",
            master_data_options,
            key="rule_md_select"
        )

        # ── Champ BC cible : liste déroulante selon Master Data ───────────────
        available_fields = get_fields_for_master_data(rule_md)

        if available_fields:
            # Option vide au début pour les règles qui s'appliquent à toute la ligne
            field_options = ["— Sélectionner un champ (optionnel) —"] + available_fields
            selected_field_label = st.selectbox(
                "Champ BC cible",
                field_options,
                key="rule_field_select",
                help="Champs BC disponibles pour cette Master Data. "
                     "Laissez vide si la règle s'applique à la ligne entière."
            )
            rule_field = (
                selected_field_label
                if selected_field_label != "— Sélectionner un champ (optionnel) —"
                else ""
            )

            # Afficher les contraintes du champ sélectionné
            if rule_field and rule_field in FIELD_DEFS.get(
                MASTER_DATA_TABLE_MAP.get(rule_md, ""), {}
            ):
                table_id   = MASTER_DATA_TABLE_MAP[rule_md]
                field_info = FIELD_DEFS[table_id][rule_field]
                hints      = []
                if field_info.get("req"):
                    hints.append("✅ Obligatoire")
                if field_info.get("max"):
                    hints.append(f"📏 Max {field_info['max']} caractères")
                if field_info.get("type") != "Text":
                    hints.append(f"🏷️ Type : {field_info['type']}")
                if field_info.get("options"):
                    opts = [v for v in field_info["options"] if v.strip()]
                    hints.append(f"📋 Options : {', '.join(opts)}")
                if hints:
                    st.caption(" · ".join(hints))
        else:
            # Saisie libre pour les Master Data sans définition (Général...)
            rule_field = st.text_input(
                "Champ BC cible",
                placeholder="Ex : Country/Region Code",
                key="rule_field_text"
            )

        rule_type = st.selectbox(
            "Type de règle *",
            RULE_TYPES,
            help="\n".join(f"• {k} : {v}" for k, v in RULE_TYPES_HELP.items())
        )

    with col2:
        rule_cond = st.text_input(
            "Condition (Si...)",
            placeholder="Ex : Si Pays est vide",
            help="Laissez vide si la règle s'applique toujours."
        )
        rule_action = st.text_area(
            "Action (Alors...)",
            placeholder="Ex : Mettre 'FR'",
            height=100
        )
        rule_sev  = st.selectbox("Sévérité", SEVERITIES)
        rule_auto = st.checkbox(
            "⚡ Correction automatique",
            value=rule_type in AUTO_CORRECT_TYPES if rule_type else False,
            help="Si coché, la correction est appliquée sans validation manuelle."
        )

    st.markdown("---")
    if st.button(
        "💾 Enregistrer la règle",
        type="primary",
        use_container_width=True,
        key="save_rule"
    ):
        if not rule_label.strip():
            st.error("Le libellé de la règle est obligatoire.")
        else:
            ok, err = create_rule({
                "profile_code": selected_code,
                "label":        rule_label.strip(),
                "master_data":  rule_md,
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
            auto_txt = " *(correction automatique possible)*" \
                if rt in AUTO_CORRECT_TYPES else ""
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
        source_label = st.selectbox(
            "Copier depuis",
            [p["label"] for p in others]
        )
        source_code = next(
            (p["code"] for p in others if p["label"] == source_label), None
        )
        if source_code:
            src_rules = get_rules_for_profile(source_code)
            st.info(f"Ce profil contient **{len(src_rules)} règle(s)**.")
            if src_rules and st.button(
                f"📋 Copier {len(src_rules)} règle(s)",
                type="primary"
            ):
                ok, msg_c, nb = copy_rules_to_profile(source_code, selected_code)
                if ok:
                    st.success(f"✅ {msg_c}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg_c}")
