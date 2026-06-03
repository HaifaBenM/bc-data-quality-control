"""
Page Règles Métier — Configurer les règles de validation par client.
Cette page sera développée au Sprint 2.
"""
import streamlit as st

st.set_page_config(
    page_title="Règles Métier — BC Quality Control",
    page_icon="⚙️",
    layout="wide"
)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("# ⚙️ Règles Métier")
st.markdown("Configurer les règles de validation spécifiques à chaque client.")
st.markdown("---")

# ── Types de règles disponibles ──────────────────────────────────────────────
st.markdown("### Types de règles disponibles")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    | Type | Description |
    |------|-------------|
    | **Valeur par défaut** | Si champ vide → mettre une valeur fixe |
    | **Transformation** | Remplacer valeur A par valeur B |
    | **Table de correspondance** | Mapper une liste de valeurs |
    | **Condition métier** | Vérifier cohérence entre champs |
    """)

with col2:
    st.markdown("""
    | Type | Description |
    |------|-------------|
    | **Format obligatoire** | Vérifier le format d'un champ |
    | **Plage de valeurs** | Vérifier un intervalle numérique |
    | **Exclusion de ligne** | Exclure certaines lignes de l'import |
    | **Détection doublon** | Signaler les lignes dupliquées |
    """)

st.markdown("---")

# ── Placeholder ──────────────────────────────────────────────────────────────
st.info("""
🚧 **Sprint 2** — Cette page permettra de :
- Sélectionner un client et voir ses règles existantes
- Ajouter une nouvelle règle via un formulaire guidé
- Activer / désactiver des règles sans les supprimer
- Tester une règle sur un jeu de données exemple
- Copier des règles d'un profil client vers un autre
""")

# ── Aperçu formulaire ────────────────────────────────────────────────────────
with st.expander("👀 Aperçu du formulaire d'une règle (non fonctionnel)"):
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Client", ["— Sélectionner —"], disabled=True)
        st.text_input("Libellé de la règle", placeholder="Pays par défaut = France", disabled=True)
        st.selectbox("Master Data", ["Clients", "Fournisseurs", "Articles"], disabled=True)
        st.selectbox("Champ cible", ["—"], disabled=True)
    with col2:
        st.selectbox("Type de règle", [
            "Valeur par défaut", "Transformation", "Table de correspondance",
            "Condition métier", "Format obligatoire", "Plage de valeurs",
            "Exclusion de ligne", "Détection doublon"
        ], disabled=True)
        st.text_input("Condition (Si...)", placeholder="Si Pays est vide", disabled=True)
        st.text_input("Action (Alors...)", placeholder="Mettre 'FR'", disabled=True)
        st.selectbox("Sévérité", ["Mineure", "Majeure", "Info"], disabled=True)
        st.checkbox("Correction automatique", disabled=True)
    st.button("💾 Enregistrer la règle", disabled=True)
