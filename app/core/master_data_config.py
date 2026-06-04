"""
Configuration des Master Data BC.
Utilisé pour l'auto-détection des tables dans le fichier uploadé.
"""

# Tables de DONNÉES — le client saisit ses données métier
# Clé = numéro de table BC, Valeur = nom lisible
DATA_TABLES = {
    "15":   "Plan comptable",
    "18":   "Clients",
    "23":   "Fournisseurs",
    "27":   "Articles",
    "37":   "En-têtes vente",
    "38":   "En-têtes achat",
    "51":   "Ressources",
    "156":  "Ressources",
    "5050": "Contacts",
    "5600": "Immobilisations",
    "5741": "Articles de transfert",
    "1381": "Modèles",
}

# Tables de RÉFÉRENCE — fournissent des valeurs de liste pour la validation
# Utilisées en Sprint 5 pour la validation des références croisées
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
    "270": "Banques",
    "286": "Secteurs",
    "289": "Modes de règlement",
    "291": "Transporteurs",
    "292": "Conditions de relance",
    "308": "Souches de n°",
    "320": "Groupes compta. TVA marché",
    "323": "Groupes compta. marché TVA",
    "324": "Groupes compta. produit TVA",
    "325": "Groupes compta. TVA produit",
    "340": "Groupes remises client",
    "348": "Sections analytiques",
    "349": "Valeurs de section analytique",
    "396": "Catégories de compte",
    "413": "Partenaires IC",
    "5714": "Centres de gestion",
    "5790": "Prestations transporteur",
    "5957": "Zones service",
    "7600": "Calendriers",
}


def categorize_table(table_id: str) -> str:
    """
    Catégorise une table BC selon son ID.
    Retourne : 'data', 'reference', ou 'system'
    """
    if table_id in DATA_TABLES:
        return "data"
    if table_id in REFERENCE_TABLES:
        return "reference"
    # Tables système BC (8xxx) — configuration du package lui-même
    if table_id.startswith("8") and len(table_id) == 4:
        return "system"
    return "reference"  # Par défaut : référence


def get_table_label(table_id: str, table_name_from_file: str = "") -> str:
    """
    Retourne le libellé lisible d'une table.
    Utilise le nom du fichier si la table n'est pas dans notre config.
    """
    if table_id in DATA_TABLES:
        return DATA_TABLES[table_id]
    if table_id in REFERENCE_TABLES:
        return REFERENCE_TABLES[table_id]
    return table_name_from_file or f"Table {table_id}"
