"""
Configuration des Master Data BC.
Définit les champs attendus par table pour la validation structurelle.
En Sprint 3, ces données viendront directement de l'API BC.
"""

# ── Configuration des Master Data disponibles ────────────────────────────────
MASTER_DATA_CONFIG = {

    "Clients": {
        "label": "Clients",
        "icon": "👥",
        "bc_table": "Customer",
        "bc_table_id": 18,
        "description": "Fiches clients Business Central",
        "key_fields": [
            "No.", "Name", "Address", "City", "Post Code",
            "Country/Region Code", "Phone No.", "E-Mail",
            "Customer Posting Group", "Gen. Bus. Posting Group",
            "VAT Bus. Posting Group", "Payment Terms Code",
            "Currency Code", "Salesperson Code", "Credit Limit (LCY)",
            "Blocked"
        ],
        "mandatory_fields": [
            "No.", "Name", "Customer Posting Group",
            "Gen. Bus. Posting Group", "VAT Bus. Posting Group"
        ],
        "related_tables": [
            "Ship-to Address",
            "Customer Bank Account",
            "Contact",
            "Default Dimension"
        ]
    },

    "Fournisseurs": {
        "label": "Fournisseurs",
        "icon": "🏭",
        "bc_table": "Vendor",
        "bc_table_id": 23,
        "description": "Fiches fournisseurs Business Central",
        "key_fields": [
            "No.", "Name", "Address", "City", "Post Code",
            "Country/Region Code", "Phone No.", "E-Mail",
            "Vendor Posting Group", "Gen. Bus. Posting Group",
            "VAT Bus. Posting Group", "Payment Terms Code",
            "Currency Code", "Purchaser Code", "Blocked"
        ],
        "mandatory_fields": [
            "No.", "Name", "Vendor Posting Group",
            "Gen. Bus. Posting Group", "VAT Bus. Posting Group"
        ],
        "related_tables": [
            "Vendor Bank Account",
            "Contact",
            "Default Dimension"
        ]
    },

    "Articles": {
        "label": "Articles",
        "icon": "📦",
        "bc_table": "Item",
        "bc_table_id": 27,
        "description": "Articles et produits Business Central",
        "key_fields": [
            "No.", "Description", "Type", "Base Unit of Measure",
            "Unit Price", "Unit Cost", "Item Category Code",
            "Inventory Posting Group", "Gen. Prod. Posting Group",
            "VAT Prod. Posting Group", "Blocked"
        ],
        "mandatory_fields": [
            "No.", "Description", "Base Unit of Measure",
            "Inventory Posting Group", "Gen. Prod. Posting Group"
        ],
        "related_tables": [
            "Item Unit of Measure",
            "Item Variant",
            "Default Dimension"
        ]
    },

    "Plan comptable": {
        "label": "Plan comptable",
        "icon": "📊",
        "bc_table": "G/L Account",
        "bc_table_id": 15,
        "description": "Comptes du plan comptable Business Central",
        "key_fields": [
            "No.", "Name", "Account Type", "Account Category",
            "Account Subcategory Entry No.", "Gen. Posting Type",
            "Gen. Bus. Posting Group", "Gen. Prod. Posting Group",
            "VAT Bus. Posting Group", "VAT Prod. Posting Group",
            "Direct Posting", "Blocked"
        ],
        "mandatory_fields": [
            "No.", "Name", "Account Type", "Direct Posting"
        ],
        "related_tables": [
            "Default Dimension"
        ]
    },

    "Contacts": {
        "label": "Contacts",
        "icon": "📇",
        "bc_table": "Contact",
        "bc_table_id": 5050,
        "description": "Contacts Business Central",
        "key_fields": [
            "No.", "Name", "Type", "Company No.", "Company Name",
            "Address", "City", "Post Code", "Country/Region Code",
            "Phone No.", "E-Mail", "Salesperson Code"
        ],
        "mandatory_fields": ["No.", "Name", "Type"],
        "related_tables": []
    },

    "Dimensions": {
        "label": "Dimensions",
        "icon": "📐",
        "bc_table": "Dimension",
        "bc_table_id": 348,
        "description": "Dimensions et valeurs de dimensions",
        "key_fields": ["Code", "Name", "Blocked"],
        "mandatory_fields": ["Code", "Name"],
        "related_tables": ["Dimension Value"]
    },

    "Unités de mesure": {
        "label": "Unités de mesure",
        "icon": "📏",
        "bc_table": "Unit of Measure",
        "bc_table_id": 204,
        "description": "Unités de mesure Business Central",
        "key_fields": [
            "Code", "Description", "International Standard Code"
        ],
        "mandatory_fields": ["Code", "Description"],
        "related_tables": []
    },
}


def get_master_data_list():
    """Retourne la liste des Master Data disponibles pour la liste déroulante."""
    return list(MASTER_DATA_CONFIG.keys())


def get_master_data_config(master_data_name: str) -> dict:
    """Retourne la configuration d'une Master Data par son nom."""
    return MASTER_DATA_CONFIG.get(master_data_name, {})


def get_related_tables(master_data_name: str) -> list:
    """Retourne les tables liées disponibles pour une Master Data."""
    config = get_master_data_config(master_data_name)
    return config.get("related_tables", [])
