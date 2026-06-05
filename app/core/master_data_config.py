"""
Configuration des Master Data BC.
Tables de données vs tables de référence pour l'auto-détection.
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
    "92":  "Groupes compta. client",
    "93":  "Groupes compta. fournisseur",
    "94":  "Groupes compta. stock",
    "250": "Groupes compta. marché",
    "252": "Groupes compta. produit",
    "258": "Natures transaction",
    "259": "Modes de transport",
    "289": "Modes de règlement",
    "291": "Transporteurs",
    "292": "Conditions de relance",
    "308": "Souches de n°",
    "323": "Groupes compta. marché TVA",
    "340": "Groupes remises client",
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
    """Retourne le libellé lisible d'une table."""
    if table_id in DATA_TABLES:
        return DATA_TABLES[table_id]
    if table_id in REFERENCE_TABLES:
        return REFERENCE_TABLES[table_id]
    return table_name_from_file or f"Table {table_id}"


def get_master_data_list() -> list:
    """Retourne la liste des Master Data pour les formulaires."""
    return list(DATA_TABLES.values()) + ["Général"]
