"""
Configuration des modules BC pour la saisie des règles métier.
Hiérarchie : Module → Tables (avec ID) → Champs (avec contraintes).

Source : Microsoft Dynamics 365 Business Central — structure standard.
Utilisé dans la page Règles Métier pour guider la saisie des règles.
"""

# ══════════════════════════════════════════════════════════════════════════════
# CHAMPS PAR TABLE BC
# Reprend les définitions de validator_axe_a.py + tables supplémentaires
# ══════════════════════════════════════════════════════════════════════════════

_FIELDS_18 = {  # Clients
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Nom":                         {"type": "Text",    "max": 100,  "req": True},
    "Nom 2":                       {"type": "Text",    "max": 50},
    "Nom de recherche":            {"type": "Text",    "max": 100},
    "Adresse":                     {"type": "Text",    "max": 100},
    "Adresse (2ème ligne)":        {"type": "Text",    "max": 50},
    "Ville":                       {"type": "Text",    "max": 30},
    "Code postal":                 {"type": "Text",    "max": 20},
    "Code pays/région":            {"type": "Text",    "max": 10},
    "N° téléphone":                {"type": "Text",    "max": 30},
    "Adresse e-mail":              {"type": "Email",   "max": 80},
    "Contact":                     {"type": "Text",    "max": 100},
    "Groupe compta. client":       {"type": "Text",    "max": 20,   "req": True},
    "Groupe compta. marché":       {"type": "Text",    "max": 20,   "req": True},
    "Groupe compta. marché TVA":   {"type": "Text",    "max": 20},
    "Code conditions paiement":    {"type": "Text",    "max": 10},
    "Code devise":                 {"type": "Text",    "max": 10},
    "Code vendeur":                {"type": "Text",    "max": 20},
    "Code magasin":                {"type": "Text",    "max": 10},
    "Crédit autorisé DS":          {"type": "Decimal"},
    "Bloqué":                      {"type": "Option",  "options": ["", "Expédier", "Facture", "Tous"]},
    "Code mode de paiement":       {"type": "Text",    "max": 10},
    "Code condition relance":      {"type": "Text",    "max": 10},
    "N° TVA":                      {"type": "Text",    "max": 20},
    "N° SIRET":                    {"type": "Text",    "max": 14},
    "Code langue":                 {"type": "Text",    "max": 10},
    "Priorité":                    {"type": "Integer"},
    "Groupe prix client":          {"type": "Text",    "max": 10},
    "Groupe remises client":       {"type": "Text",    "max": 20},
    "% acompte":                   {"type": "Decimal"},
    "Code transporteur":           {"type": "Text",    "max": 10},
    "Regrouper les expéditions":   {"type": "Boolean"},
}

_FIELDS_23 = {  # Fournisseurs
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Nom":                         {"type": "Text",    "max": 100,  "req": True},
    "Nom 2":                       {"type": "Text",    "max": 50},
    "Nom de recherche":            {"type": "Text",    "max": 100},
    "Adresse":                     {"type": "Text",    "max": 100},
    "Adresse (2ème ligne)":        {"type": "Text",    "max": 50},
    "Ville":                       {"type": "Text",    "max": 30},
    "Code postal":                 {"type": "Text",    "max": 20},
    "Code pays/région":            {"type": "Text",    "max": 10},
    "N° téléphone":                {"type": "Text",    "max": 30},
    "Adresse e-mail":              {"type": "Email",   "max": 80},
    "Contact":                     {"type": "Text",    "max": 100},
    "Groupe compta. fournisseur":  {"type": "Text",    "max": 20,   "req": True},
    "Groupe compta. marché":       {"type": "Text",    "max": 20,   "req": True},
    "Groupe compta. marché TVA":   {"type": "Text",    "max": 20},
    "Code conditions paiement":    {"type": "Text",    "max": 10},
    "Code devise":                 {"type": "Text",    "max": 10},
    "Code acheteur":               {"type": "Text",    "max": 20},
    "Bloqué":                      {"type": "Option",  "options": ["", "Paiement", "Facture", "Tous"]},
    "N° TVA":                      {"type": "Text",    "max": 20},
    "N° SIRET":                    {"type": "Text",    "max": 14},
    "Code mode de paiement":       {"type": "Text",    "max": 10},
    "% acompte":                   {"type": "Decimal"},
    "N° compte bancaire préféré":  {"type": "Text",    "max": 20},
    "Code devise paiement":        {"type": "Text",    "max": 10},
}

_FIELDS_27 = {  # Articles
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Description":                 {"type": "Text",    "max": 100,  "req": True},
    "Description 2":               {"type": "Text",    "max": 50},
    "Recherche description":       {"type": "Text",    "max": 100},
    "Type":                        {"type": "Option",  "options": ["", "Stock", "Service", "Hors stock"]},
    "Unité de mesure de base":     {"type": "Text",    "max": 10,   "req": True},
    "Prix unitaire":               {"type": "Decimal"},
    "Coût unitaire":               {"type": "Decimal"},
    "Coût unitaire (standard)":    {"type": "Decimal"},
    "Groupe compta. stock":        {"type": "Text",    "max": 20,   "req": True},
    "Groupe compta. produit":      {"type": "Text",    "max": 20,   "req": True},
    "Groupe compta. produit TVA":  {"type": "Text",    "max": 20},
    "Code catégorie article":      {"type": "Text",    "max": 20},
    "N° tarif douanier":           {"type": "Text",    "max": 20},
    "N° GTIN":                     {"type": "Text",    "max": 14},
    "N° article fournisseur":      {"type": "Text",    "max": 50},
    "Bloqué":                      {"type": "Boolean"},
    "Ventes bloquées":             {"type": "Boolean"},
    "Achats bloqués":              {"type": "Boolean"},
    "Poids net":                   {"type": "Decimal"},
    "Poids brut":                  {"type": "Decimal"},
    "Méthode valorisation":        {"type": "Option",
                                    "options": ["", "FIFO", "LIFO", "Spécifique", "Moyen", "Standard"]},
}

_FIELDS_15 = {  # Plan comptable
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Nom":                         {"type": "Text",    "max": 100,  "req": True},
    "Type compte":                 {"type": "Option",  "req": True,
                                    "options": ["", "Reportage", "Total", "Début total", "Fin total"]},
    "Catégorie compte":            {"type": "Option",
                                    "options": ["", "Actif", "Passif", "Fonds propres",
                                                "Produits", "Charges", "Coût des marchandises"]},
    "Sous-catégorie compte":       {"type": "Text",    "max": 80},
    "Type comptabilisation":       {"type": "Option",
                                    "options": ["", " ", "Vente", "Achat"]},
    "Groupe compta. marché":       {"type": "Text",    "max": 20},
    "Groupe compta. produit":      {"type": "Text",    "max": 20},
    "Groupe compta. marché TVA":   {"type": "Text",    "max": 20},
    "Groupe compta. produit TVA":  {"type": "Text",    "max": 20},
    "Validation directe":          {"type": "Boolean"},
    "Bloqué":                      {"type": "Boolean"},
    "N° report de débit":          {"type": "Text",    "max": 20},
    "N° report de crédit":         {"type": "Text",    "max": 20},
    "Centre de coûts":             {"type": "Text",    "max": 20},
    "Objet de coûts":              {"type": "Text",    "max": 20},
}

_FIELDS_5050 = {  # Contacts
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Nom":                         {"type": "Text",    "max": 100,  "req": True},
    "Type":                        {"type": "Option",  "options": ["", "Société", "Personne"]},
    "N° société":                  {"type": "Text",    "max": 20},
    "Interlocuteur":               {"type": "Text",    "max": 100},
    "Adresse":                     {"type": "Text",    "max": 100},
    "Ville":                       {"type": "Text",    "max": 30},
    "Code postal":                 {"type": "Text",    "max": 20},
    "Code pays/région":            {"type": "Text",    "max": 10},
    "N° téléphone":                {"type": "Text",    "max": 30},
    "Adresse e-mail":              {"type": "Email",   "max": 80},
    "Page d'accueil":              {"type": "Text",    "max": 80},
    "Bloqué":                      {"type": "Option",  "options": ["", "Tout"]},
    "Code langue":                 {"type": "Text",    "max": 10},
    "Code vendeur":                {"type": "Text",    "max": 20},
    "Fonction":                    {"type": "Text",    "max": 30},
}

_FIELDS_156 = {  # Ressources
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Type":                        {"type": "Option",  "req": True,
                                    "options": ["", "Personne", "Machine"]},
    "Nom":                         {"type": "Text",    "max": 100,  "req": True},
    "Unité de mesure de base":     {"type": "Text",    "max": 10},
    "Prix unitaire":               {"type": "Decimal"},
    "Coût unitaire direct":        {"type": "Decimal"},
    "Groupe compta. produit":      {"type": "Text",    "max": 20},
    "N° groupe ressources":        {"type": "Text",    "max": 20},
    "Bloqué":                      {"type": "Boolean"},
    "Code service":                {"type": "Text",    "max": 10},
    "Adresse e-mail":              {"type": "Email",   "max": 80},
}

_FIELDS_5600 = {  # Immobilisations
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Description":                 {"type": "Text",    "max": 100,  "req": True},
    "Classe immo.":                {"type": "Text",    "max": 10},
    "Sous-classe immo.":           {"type": "Text",    "max": 10},
    "Code magasin":                {"type": "Text",    "max": 10},
    "Bloqué":                      {"type": "Boolean"},
    "Date acquisition":            {"type": "Date"},
    "Groupe compta. produit":      {"type": "Text",    "max": 20},
    "N° série":                    {"type": "Text",    "max": 20},
    "Adresse":                     {"type": "Text",    "max": 100},
    "Ville":                       {"type": "Text",    "max": 30},
    "Code pays/région":            {"type": "Text",    "max": 10},
    "Responsable":                 {"type": "Text",    "max": 20},
}

_FIELDS_167 = {  # Projets (Jobs)
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "Description":                 {"type": "Text",    "max": 100,  "req": True},
    "Description 2":               {"type": "Text",    "max": 50},
    "N° client facturation":       {"type": "Text",    "max": 20,   "req": True},
    "N° client livraison":         {"type": "Text",    "max": 20},
    "Statut":                      {"type": "Option",
                                    "options": ["", "Commande", "Devis", "Terminé", "Bloqué"]},
    "Code devise":                 {"type": "Text",    "max": 10},
    "Code vendeur":                {"type": "Text",    "max": 20},
    "Date début":                  {"type": "Date"},
    "Date fin":                    {"type": "Date"},
    "Groupe compta. produit":      {"type": "Text",    "max": 20},
    "Bloqué":                      {"type": "Boolean"},
}

_FIELDS_5741 = {  # Variantes article
    "Code article":                {"type": "Text",    "max": 20,   "req": True},
    "Code":                        {"type": "Text",    "max": 10,   "req": True},
    "Description":                 {"type": "Text",    "max": 100},
    "Description 2":               {"type": "Text",    "max": 50},
    "Bloqué":                      {"type": "Boolean"},
}

_FIELDS_5900 = {  # En-têtes service
    "N°":                          {"type": "Text",    "max": 20,   "req": True},
    "N° client":                   {"type": "Text",    "max": 20,   "req": True},
    "Nom":                         {"type": "Text",    "max": 100},
    "Adresse":                     {"type": "Text",    "max": 100},
    "Ville":                       {"type": "Text",    "max": 30},
    "Code postal":                 {"type": "Text",    "max": 20},
    "Code pays/région":            {"type": "Text",    "max": 10},
    "N° contact":                  {"type": "Text",    "max": 20},
    "Code conditions paiement":    {"type": "Text",    "max": 10},
    "Statut":                      {"type": "Option",
                                    "options": ["", "En attente", "En cours", "Terminé", "Bloqué"]},
}


# ══════════════════════════════════════════════════════════════════════════════
# MODULES BC — hiérarchie fonctionnelle
# ══════════════════════════════════════════════════════════════════════════════

BC_MODULES = {
    "Ventes": {
        "icon":   "🛒",
        "tables": {
            "18":   {"label": "Clients",          "fields": _FIELDS_18},
            "5050": {"label": "Contacts",          "fields": _FIELDS_5050},
        },
    },
    "Achats": {
        "icon":   "🛍️",
        "tables": {
            "23":   {"label": "Fournisseurs",      "fields": _FIELDS_23},
        },
    },
    "Stock": {
        "icon":   "📦",
        "tables": {
            "27":   {"label": "Articles",          "fields": _FIELDS_27},
            "5741": {"label": "Variantes article", "fields": _FIELDS_5741},
        },
    },
    "Finance": {
        "icon":   "💰",
        "tables": {
            "15":   {"label": "Plan comptable",    "fields": _FIELDS_15},
        },
    },
    "Projets": {
        "icon":   "📋",
        "tables": {
            "167":  {"label": "Projets",           "fields": _FIELDS_167},
        },
    },
    "Ressources": {
        "icon":   "👷",
        "tables": {
            "156":  {"label": "Ressources",        "fields": _FIELDS_156},
        },
    },
    "Immobilisations": {
        "icon":   "🏭",
        "tables": {
            "5600": {"label": "Immobilisations",   "fields": _FIELDS_5600},
        },
    },
    "Service": {
        "icon":   "🔧",
        "tables": {
            "5900": {"label": "En-têtes service",  "fields": _FIELDS_5900},
        },
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_module_options() -> list[str]:
    """Liste des modules avec icône pour la liste déroulante."""
    return [f"{v['icon']} {k}" for k, v in BC_MODULES.items()]


def get_module_name(option: str) -> str:
    """Extrait le nom du module depuis l'option affichée ('🛒 Ventes' → 'Ventes')."""
    parts = option.split(" ", 1)
    return parts[1] if len(parts) > 1 else option


def get_table_options(module_name: str) -> list[str]:
    """
    Retourne les tables d'un module sous forme de liste déroulante.
    Format : '18 — Clients' (recherchable par ID ou nom)
    """
    module = BC_MODULES.get(module_name, {})
    tables = module.get("tables", {})
    return [f"{tid} — {info['label']}" for tid, info in tables.items()]


def get_table_id(table_option: str) -> str:
    """Extrait l'ID depuis '18 — Clients' → '18'."""
    return table_option.split(" — ")[0].strip() if " — " in table_option else ""


def get_fields_for_table(module_name: str, table_id: str) -> dict:
    """Retourne le dict de champs pour un module/table donnés."""
    module = BC_MODULES.get(module_name, {})
    tables = module.get("tables", {})
    return tables.get(table_id, {}).get("fields", {})


def get_field_options(module_name: str, table_id: str) -> list[str]:
    """Retourne la liste des noms de champs pour une table."""
    fields = get_fields_for_table(module_name, table_id)
    return sorted(fields.keys())


def get_field_info(module_name: str, table_id: str, field_name: str) -> dict:
    """Retourne les contraintes d'un champ (type, max, req, options)."""
    fields = get_fields_for_table(module_name, table_id)
    return fields.get(field_name, {})


def get_master_data_label(module_name: str, table_id: str) -> str:
    """Retourne le label Master Data pour la sauvegarde en base."""
    module = BC_MODULES.get(module_name, {})
    tables = module.get("tables", {})
    return tables.get(table_id, {}).get("label", "Général")
