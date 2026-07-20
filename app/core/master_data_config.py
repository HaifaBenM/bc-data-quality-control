"""
Configuration des Master Data BC.
Tables de données vs tables de référence pour l'auto-détection.

⚠️ Ce fichier sert UNIQUEMENT à l'affichage (libellés lisibles dans les
rapports). Il n'intervient PAS dans la récupération réelle des valeurs de
référence (Axe B) — celle-ci passe par _TABLE_BC_ENTITY /
_REF_TABLE_CACHE_KEYS dans app/db/metadata_db.py, dictionnaire distinct,
confirmé et utilisé en production. Une erreur ici n'affecte jamais la
fiabilité des contrôles, seulement le texte affiché.
"""

# Tables de DONNÉES — le client saisit ses données métier
DATA_TABLES = {
    "15":   "Plan comptable",
    "18":   "Clients",
    "23":   "Fournisseurs",
    "27":   "Articles",
    "37":   "En-têtes vente",
    "38":   "En-têtes achat",
    "51":   "Ressources",
    "5050": "Contacts",
    "5600": "Immobilisations",
}

# Tables de RÉFÉRENCE — listes de valeurs BC
REFERENCE_TABLES = {
    "3":   "Conditions de paiement",
    "4":   "Devises",
    "5":   "Conditions intérêts de retard",
    "6":   "Groupes prix client",
    "7":   "Groupes remises client",
    "8":   "Langues",
    "9":   "Pays/Régions",
    "10":  "Conditions de livraison",
    "13":  "Vendeurs/Acheteurs",
    "14":  "Magasins",
    "204": "Unité de mesure",  # confirmé par metadata_db._TABLE_BC_ENTITY (unitsOfMeasure)
    # Corrigé session 17/07/2026 — confirmé par metadata_db._TABLE_BC_ENTITY
    # (91: customerPostingGroups, 92: vendorPostingGroups). L'ancienne
    # version de ce dictionnaire avait 92/93 inversés par rapport à la
    # réalité BC (92=client, 93=fournisseur) — corrigé ici.
    "91":  "Groupes compta. client",
    "92":  "Groupes compta. fournisseur",
    "94":  "Groupes compta. stock",
    # ⚠️ CONFLIT NON RÉSOLU : deux tables candidates pour "VAT Business
    # Posting Group" — 74 (confirmé dans metadata_db._TABLE_BC_ENTITY) et
    # 323 (déjà présent ici de longue date). Impossible de trancher sans
    # vérification BC directe (Object Designer). Les deux entrées sont
    # laissées telles quelles — À VÉRIFIER PAR RAMI.
    "323": "Groupes compta. marché TVA",
    # Confirmé par metadata_db._TABLE_BC_ENTITY (251: generalProductPostingGroups).
    "251": "Groupes compta. produit",
    # ⚠️ CONFLIT NON RÉSOLU avec l'entrée 251 ci-dessus (même libellé
    # "Groupe compta. produit" utilisé pour deux IDs différents dans les
    # sessions précédentes). 252 n'apparaît PAS dans metadata_db._TABLE_BC_ENTITY
    # (donc pas confirmé comme table réellement utilisée pour la validation
    # des références) — probable erreur historique à corriger ou supprimer,
    # À VÉRIFIER PAR RAMI avant d'y toucher. Libellé affiché laissé propre
    # (pas d'avertissement visible dans le rapport client).
    "252": "Groupes compta. produit",
    "258": "Natures transaction",
    "259": "Modes de transport",
    "289": "Modes de règlement",
    "291": "Transporteurs",
    "292": "Conditions de relance",
    "308": "Souches de n°",
    # ⚠️ NON confirmé dans metadata_db._TABLE_BC_ENTITY — libellé conservé
    # tel quel depuis les sessions précédentes, pas re-vérifié cette session.
    "322": "Groupes taxes",
    # Corrigé session 17/07/2026 — remplace la précédente entrée "324"
    # (devinée à tort). Confirmé par metadata_db._TABLE_BC_ENTITY
    # (325: vatProductPostingGroups).
    "325": "Groupes compta. produit TVA",
    # Ajouté session 17/07/2026 — confirmé (metadata_db._TABLE_BC_ENTITY,
    # cas "ACC" table 5722 déjà rencontré en session).
    "5722": "Catégorie d'article",
    # Corrigé session 17/07/2026 — "Groupes remises client" était dupliqué
    # avec l'entrée "7" ci-dessus, qui EST la vraie table Customer Discount
    # Group. metadata_db._TABLE_BC_ENTITY ne référence pas la 340 comme
    # itemDiscountGroups, mais le nom d'origine (copié sur la 7) était
    # clairement une erreur de copier-coller. Remplacé par un libellé
    # plausible mais NON CONFIRMÉ — À VÉRIFIER PAR RAMI. Pas d'avertissement
    # dans le libellé affiché (rapport client).
    "340": "Groupes remises article",
    "349": "Sections analytiques",
    "413": "Partenaires IC",
    "5714": "Centres de gestion",
    "5790": "Prestations transporteur",
    "5957": "Zones service",
    "7600": "Calendriers",
}


def categorize_table(table_id: str) -> str:
    """Catégorise une table BC : 'data', 'reference' ou 'system'."""
    if table_id in DATA_TABLES:
        return "data"
    if table_id in REFERENCE_TABLES:
        return "reference"
    if table_id.startswith("8") and len(table_id) == 4:
        return "system"
    return "reference"


def get_table_label(table_id: str, table_name_from_file: str = "") -> str:
    """Retourne le libellé lisible d'une table (fallback statique — voir
    correction_classifier.build_prerequisites_report pour la résolution
    dynamique via BC, prioritaire)."""
    if table_id in DATA_TABLES:
        return DATA_TABLES[table_id]
    if table_id in REFERENCE_TABLES:
        return REFERENCE_TABLES[table_id]
    return table_name_from_file or f"Table {table_id}"


def get_master_data_list() -> list:
    """Retourne la liste des Master Data pour les formulaires."""
    return list(DATA_TABLES.values()) + ["Général"]