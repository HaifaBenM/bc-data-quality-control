"""
Validation Axe A — Contraintes BC standard.
Vérifie types, longueurs, champs obligatoires, valeurs Option et doublons.
Source des contraintes : BC standard + terrain (indépendant de la connexion API).
"""
import re
import pandas as pd
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# DÉFINITIONS DES CHAMPS BC PAR TABLE
# Clé = numéro table BC, Valeur = dict {nom_champ_français: contraintes}
# ══════════════════════════════════════════════════════════════════════════════

FIELD_DEFS = {

    # ── Table 18 — Clients ────────────────────────────────────────────────────
    "18": {
        "N°":                          {"type": "Text",    "max": 20,   "req": True},
        "Nom":                         {"type": "Text",    "max": 100,  "req": True},
        "Nom 2":                       {"type": "Text",    "max": 50,   "req": False},
        "Nom de recherche":            {"type": "Text",    "max": 100,  "req": False},
        "Adresse":                     {"type": "Text",    "max": 100,  "req": False},
        "Adresse (2ème ligne)":        {"type": "Text",    "max": 50,   "req": False},
        "Ville":                       {"type": "Text",    "max": 30,   "req": False},
        "Code postal":                 {"type": "Text",    "max": 20,   "req": False},
        "Code pays/région":            {"type": "Text",    "max": 10,   "req": False},
        "N° téléphone":                {"type": "Text",    "max": 30,   "req": False},
        "N° télécopie":                {"type": "Text",    "max": 30,   "req": False},
        "Adresse e-mail":              {"type": "Email",   "max": 80,   "req": False},
        "Page d'accueil":              {"type": "Text",    "max": 80,   "req": False},
        "Contact":                     {"type": "Text",    "max": 100,  "req": False},
        "Groupe compta. client":       {"type": "Text",    "max": 20,   "req": True},
        "Groupe compta. marché":       {"type": "Text",    "max": 20,   "req": True},
        "Groupe compta. marché TVA":   {"type": "Text",    "max": 20,   "req": False},
        "Code conditions paiement":    {"type": "Text",    "max": 10,   "req": False},
        "Code devise":                 {"type": "Text",    "max": 10,   "req": False},
        "Code vendeur":                {"type": "Text",    "max": 20,   "req": False},
        "Crédit autorisé DS":          {"type": "Decimal", "max": None, "req": False},
        "Bloqué":                      {"type": "Option",  "max": None, "req": False,
                                        "options": ["", " ", "Expédier", "Facture", "Tous", "Livraison", "Tout"]},
        "Code mode de paiement":       {"type": "Text",    "max": 10,   "req": False},
        "Code condition relance":      {"type": "Text",    "max": 10,   "req": False},
        "Code magasin":                {"type": "Text",    "max": 10,   "req": False},
        "N° TVA":                      {"type": "Text",    "max": 20,   "req": False},
        "N° SIRET":                    {"type": "Text",    "max": 14,   "req": False},
        "Code langue":                 {"type": "Text",    "max": 10,   "req": False},
        "Priorité":                    {"type": "Integer", "max": None, "req": False},
        "Groupe prix client":          {"type": "Text",    "max": 10,   "req": False},
        "Groupe remises client":       {"type": "Text",    "max": 20,   "req": False},
        "N° condition remise fact.":   {"type": "Text",    "max": 20,   "req": False},
        "% acompte":                   {"type": "Decimal", "max": None, "req": False},
        "Application":                 {"type": "Option",  "max": None, "req": False,
                                        "options": ["", " ", "Manuel", "Par date échéance", "Par date document"]},
        "Regrouper les expéditions":   {"type": "Boolean", "max": None, "req": False},
        "Code transporteur":           {"type": "Text",    "max": 10,   "req": False},
    },

    # ── Table 23 — Fournisseurs ───────────────────────────────────────────────
    "23": {
        "N°":                          {"type": "Text",    "max": 20,   "req": True},
        "Nom":                         {"type": "Text",    "max": 100,  "req": True},
        "Nom 2":                       {"type": "Text",    "max": 50,   "req": False},
        "Nom de recherche":            {"type": "Text",    "max": 100,  "req": False},
        "Adresse":                     {"type": "Text",    "max": 100,  "req": False},
        "Adresse (2ème ligne)":        {"type": "Text",    "max": 50,   "req": False},
        "Ville":                       {"type": "Text",    "max": 30,   "req": False},
        "Code postal":                 {"type": "Text",    "max": 20,   "req": False},
        "Code pays/région":            {"type": "Text",    "max": 10,   "req": False},
        "N° téléphone":                {"type": "Text",    "max": 30,   "req": False},
        "Adresse e-mail":              {"type": "Email",   "max": 80,   "req": False},
        "Contact":                     {"type": "Text",    "max": 100,  "req": False},
        "Groupe compta. fournisseur":  {"type": "Text",    "max": 20,   "req": True},
        "Groupe compta. marché":       {"type": "Text",    "max": 20,   "req": True},
        "Groupe compta. marché TVA":   {"type": "Text",    "max": 20,   "req": False},
        "Code conditions paiement":    {"type": "Text",    "max": 10,   "req": False},
        "Code devise":                 {"type": "Text",    "max": 10,   "req": False},
        "Code acheteur":               {"type": "Text",    "max": 20,   "req": False},
        "Bloqué":                      {"type": "Option",  "max": None, "req": False,
                                        "options": ["", " ", "Paiement", "Facture", "Tous", "Tout"]},
        "N° TVA":                      {"type": "Text",    "max": 20,   "req": False},
        "N° SIRET":                    {"type": "Text",    "max": 14,   "req": False},
        "Code mode de paiement":       {"type": "Text",    "max": 10,   "req": False},
        "% acompte":                   {"type": "Decimal", "max": None, "req": False},
        "N° condition remise fact.":   {"type": "Text",    "max": 20,   "req": False},
    },

    # ── Table 27 — Articles ───────────────────────────────────────────────────
    "27": {
        "N°":                          {"type": "Text",    "max": 20,   "req": True},
        "Description":                 {"type": "Text",    "max": 100,  "req": True},
        "Description 2":               {"type": "Text",    "max": 50,   "req": False},
        "Recherche description":        {"type": "Text",    "max": 100,  "req": False},
        "Type":                        {"type": "Option",  "max": None, "req": False,
                                        "options": ["", " ", "Stock", "Service", "Hors stock"]},
        "Unité de mesure de base":     {"type": "Text",    "max": 10,   "req": True},
        "N° tarif douanier":           {"type": "Text",    "max": 20,   "req": False},
        "Prix unitaire":               {"type": "Decimal", "max": None, "req": False},
        "Coût unitaire":               {"type": "Decimal", "max": None, "req": False},
        "Coût unitaire (standard)":    {"type": "Decimal", "max": None, "req": False},
        "Coût unitaire dernier":       {"type": "Decimal", "max": None, "req": False},
        "Groupe compta. stock":        {"type": "Text",    "max": 20,   "req": True},
        "Groupe compta. produit":      {"type": "Text",    "max": 20,   "req": True},
        "Groupe compta. produit TVA":  {"type": "Text",    "max": 20,   "req": False},
        "Code catégorie article":      {"type": "Text",    "max": 20,   "req": False},
        "N° article fournisseur":      {"type": "Text",    "max": 50,   "req": False},
        "N° GTIN":                     {"type": "Text",    "max": 14,   "req": False},
        "Bloqué":                      {"type": "Boolean", "max": None, "req": False},
        "Ventes bloquées":             {"type": "Boolean", "max": None, "req": False},
        "Achats bloqués":              {"type": "Boolean", "max": None, "req": False},
        "Poids net":                   {"type": "Decimal", "max": None, "req": False},
        "Poids brut":                  {"type": "Decimal", "max": None, "req": False},
    },

    # ── Table 15 — Plan comptable ─────────────────────────────────────────────
    "15": {
        "N°":                          {"type": "Text",    "max": 20,   "req": True},
        "Nom":                         {"type": "Text",    "max": 100,  "req": True},
        "Type compte":                 {"type": "Option",  "max": None, "req": True,
                                        "options": ["", " ", "Reportage", "Total", "Début total", "Fin total"]},
        "Catégorie compte":            {"type": "Option",  "max": None, "req": False,
                                        "options": ["", " ", "Actif", "Passif", "Fonds propres",
                                                    "Produits", "Charges", "Coût des marchandises"]},
        "Sous-catégorie compte":       {"type": "Text",    "max": 80,   "req": False},
        "Type comptabilisation":       {"type": "Option",  "max": None, "req": False,
                                        "options": ["", " ", "Vente", "Achat"]},
        "Groupe compta. marché":       {"type": "Text",    "max": 20,   "req": False},
        "Groupe compta. produit":      {"type": "Text",    "max": 20,   "req": False},
        "Groupe compta. marché TVA":   {"type": "Text",    "max": 20,   "req": False},
        "Groupe compta. produit TVA":  {"type": "Text",    "max": 20,   "req": False},
        "Validation directe":          {"type": "Boolean", "max": None, "req": False},
        "Bloqué":                      {"type": "Boolean", "max": None, "req": False},
        "N° report de débit":          {"type": "Text",    "max": 20,   "req": False},
        "N° report de crédit":         {"type": "Text",    "max": 20,   "req": False},
    },

    # ── Table 3 — Conditions de paiement ──────────────────────────────────────
    "3": {
        "Code":                        {"type": "Text",    "max": 10,   "req": True},
        "Description":                 {"type": "Text",    "max": 100,  "req": False},
        "Calcul date échéance":        {"type": "Text",    "max": 32,   "req": False},
        "Calcul date d'escompte":      {"type": "Text",    "max": 32,   "req": False},
        "% remise":                    {"type": "Decimal", "max": None, "req": False},
    },

    # ── Table 4 — Devises ─────────────────────────────────────────────────────
    "4": {
        "Code":                        {"type": "Text",    "max": 10,   "req": True},
        "Description":                 {"type": "Text",    "max": 100,  "req": False},
        "Symbole devise":              {"type": "Text",    "max": 10,   "req": False},
    },

    # ── Table 9 — Pays/Régions ────────────────────────────────────────────────
    "9": {
        "Code":                        {"type": "Text",    "max": 10,   "req": True},
        "Nom":                         {"type": "Text",    "max": 50,   "req": False},
    },
}

# Champ clé (identifiant) par table
KEY_FIELD = {
    "18": "N°", "23": "N°", "27": "N°", "15": "N°", "5050": "N°",
    "3": "Code", "4": "Code", "9": "Code",
    "default": "N°",
}

# Formats de date acceptés
DATE_FORMATS = [
    "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
    "%d.%m.%Y", "%m/%d/%Y", "%Y%m%d",
]

# Valeurs booléennes reconnues
BOOL_TRUE  = {"oui", "yes", "true", "vrai", "1", "x", "✓"}
BOOL_FALSE = {"non", "no", "false", "faux", "0", ""}


# ══════════════════════════════════════════════════════════════════════════════
# FONCTIONS DE VALIDATION INDIVIDUELLES
# ══════════════════════════════════════════════════════════════════════════════

def _is_empty(value) -> bool:
    """Retourne True si la valeur est vide ou NaN."""
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() in ("nan", "none", "nat")


def _to_str(value) -> str:
    """Convertit proprement une valeur en chaîne."""
    if _is_empty(value):
        return ""
    return str(value).strip()


def _validate_integer(value: str) -> bool:
    """Vérifie si la valeur est un entier valide."""
    try:
        # Accepter les formats avec séparateurs
        clean = value.replace(" ", "").replace("\u202f", "")
        int(float(clean))
        return True
    except (ValueError, TypeError):
        return False


def _validate_decimal(value: str) -> bool:
    """Vérifie si la valeur est un décimal valide."""
    try:
        clean = (
            value.replace(" ", "")
                 .replace("\u202f", "")
                 .replace(",", ".")  # virgule décimale française
        )
        float(clean)
        return True
    except (ValueError, TypeError):
        return False


def _validate_date(value: str) -> bool:
    """Vérifie si la valeur est une date valide dans un format connu."""
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def _validate_boolean(value: str) -> bool:
    """Vérifie si la valeur est un booléen reconnu."""
    return value.lower().strip() in BOOL_TRUE | BOOL_FALSE


def _validate_email(value: str) -> bool:
    """Vérifie le format d'une adresse e-mail."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, value))


# ══════════════════════════════════════════════════════════════════════════════
# MOTEUR DE VALIDATION AXEA
# ══════════════════════════════════════════════════════════════════════════════

def validate_axe_a(
    df:           pd.DataFrame,
    table_id:     str,
    sheet_name:   str = "",
) -> list[dict]:
    """
    Valide un DataFrame BC contre les contraintes Axe A.

    Args:
        df         : DataFrame du fichier client (en-têtes = noms de champs BC)
        table_id   : numéro de table BC (ex: "18" pour Clients)
        sheet_name : nom de l'onglet (pour les messages d'anomalie)

    Retourne une liste d'anomalies avec la structure :
    {
        line, field, value, error_type, severity, message,
        suggested_fix, axis, sheet
    }
    """
    anomalies = []
    field_defs = FIELD_DEFS.get(table_id, {})
    key_field  = KEY_FIELD.get(table_id, "N°")

    # ── Pré-calcul pour la détection de doublons ──────────────────────────────
    seen_keys = {}  # {valeur_clé: premier_numéro_ligne}

    for row_idx, row in df.iterrows():
        line_num = int(row_idx) + 1  # 1-based

        for col in df.columns:
            raw_val  = row.get(col)
            str_val  = _to_str(raw_val)
            is_empty = _is_empty(raw_val)

            field_def = field_defs.get(str(col), {})

            # ── 1. Formule Excel ──────────────────────────────────────────────
            if str_val.startswith("="):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Formule Excel",
                    severity="Majeure",
                    message=f"La cellule '{col}' contient une formule Excel. "
                            "Convertir en valeur statique avant import.",
                ))
                continue

            # ── 2. Champ obligatoire vide ─────────────────────────────────────
            if field_def.get("req") and is_empty:
                anomalies.append(_anomaly(
                    line=line_num, field=col, value="", sheet=sheet_name,
                    error_type="Champ obligatoire vide",
                    severity="Majeure",
                    message=f"'{col}' est obligatoire et ne peut pas être vide.",
                ))
                continue  # Pas d'autres contrôles si vide et obligatoire

            # Ignorer les champs vides non obligatoires
            if is_empty:
                continue

            # ── 3. Longueur maximale ──────────────────────────────────────────
            max_len = field_def.get("max")
            if max_len and len(str_val) > max_len:
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Longueur maximale dépassée",
                    severity="Majeure",
                    message=f"'{col}' : {len(str_val)} caractères saisis "
                            f"(maximum BC = {max_len}).",
                    suggested_fix=str_val[:max_len],
                ))

            # ── 4. Type de données ────────────────────────────────────────────
            field_type = field_def.get("type", "Text")

            if field_type == "Integer" and not _validate_integer(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Type incorrect (entier attendu)",
                    severity="Majeure",
                    message=f"'{col}' doit être un nombre entier, "
                            f"valeur saisie : '{str_val}'.",
                ))

            elif field_type == "Decimal" and not _validate_decimal(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Type incorrect (décimal attendu)",
                    severity="Majeure",
                    message=f"'{col}' doit être un nombre décimal, "
                            f"valeur saisie : '{str_val}'. "
                            "Utiliser '.' ou ',' comme séparateur décimal.",
                ))

            elif field_type == "Date" and not _validate_date(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Format de date incorrect",
                    severity="Majeure",
                    message=f"'{col}' : '{str_val}' n'est pas une date valide. "
                            "Formats acceptés : JJ/MM/AAAA, AAAA-MM-JJ.",
                ))

            elif field_type == "Boolean" and not _validate_boolean(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Type incorrect (booléen attendu)",
                    severity="Mineure",
                    message=f"'{col}' : '{str_val}' n'est pas un booléen. "
                            "Valeurs acceptées : Oui/Non, True/False, 1/0.",
                ))

            elif field_type == "Email" and str_val and not _validate_email(str_val):
                anomalies.append(_anomaly(
                    line=line_num, field=col, value=str_val, sheet=sheet_name,
                    error_type="Format e-mail incorrect",
                    severity="Mineure",
                    message=f"'{col}' : '{str_val}' ne semble pas "
                            "être une adresse e-mail valide.",
                ))

            # ── 5. Valeur Option ──────────────────────────────────────────────
            elif field_type == "Option":
                allowed = field_def.get("options", [])
                if allowed and str_val not in allowed:
                    allowed_display = ", ".join(
                        f"'{v}'" for v in allowed if v.strip()
                    )
                    anomalies.append(_anomaly(
                        line=line_num, field=col, value=str_val, sheet=sheet_name,
                        error_type="Valeur Option non autorisée",
                        severity="Majeure",
                        message=f"'{col}' : '{str_val}' n'est pas autorisé. "
                                f"Valeurs BC : {allowed_display}.",
                    ))

        # ── 6. Doublons sur le champ clé ──────────────────────────────────────
        if key_field in df.columns:
            key_val = _to_str(row.get(key_field))
            if key_val:
                if key_val in seen_keys:
                    anomalies.append(_anomaly(
                        line=line_num, field=key_field, value=key_val,
                        sheet=sheet_name,
                        error_type="Doublon (clé primaire)",
                        severity="Majeure",
                        message=f"'{key_field}' = '{key_val}' est dupliqué. "
                                f"Déjà présent à la ligne {seen_keys[key_val]}.",
                    ))
                else:
                    seen_keys[key_val] = line_num

    return anomalies


def _anomaly(
    line: int, field: str, value: str, sheet: str,
    error_type: str, severity: str, message: str,
    suggested_fix: str = None,
) -> dict:
    """Construit un dictionnaire d'anomalie normalisé."""
    return {
        "Ligne":             line,
        "Onglet":            sheet,
        "Champ":             field,
        "Valeur":            value,
        "Type d'anomalie":   error_type,
        "Sévérité":          severity,
        "Message":           message,
        "Correction suggérée": suggested_fix or "",
        "Axe":               "A",
    }


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION COMPLÈTE D'UN FICHIER PARSÉ
# ══════════════════════════════════════════════════════════════════════════════

def validate_file_axe_a(parse_result: dict) -> dict:
    """
    Lance la validation Axe A sur TOUTES les tables analysables du fichier
    (data_tables + ref_tables).

    Avant : seules les tables classées "data" par categorize_table() étaient
    contrôlées. Une table comme Payment Terms ou G/L Account, classée "ref"
    car elle sert aussi de source de lookup pour Axe B, n'était donc jamais
    elle-même contrôlée — même quand elle dispose déjà de contraintes dans
    FIELD_DEFS (ex: Table 15).

    Maintenant : toute table non-système (data + ref) est contrôlée.
    Les tables sans entrée dans FIELD_DEFS ne génèrent simplement aucune
    anomalie (comportement inchangé pour elles), donc ce changement est
    rétrocompatible — il ajoute de la couverture, n'en retire jamais.

    Args:
        parse_result : résultat du parsing (depuis file_parser.py)

    Retourne :
    {
        total_anomalies, major, minor, info,
        by_sheet: {sheet_name: [anomalies]},
        all_anomalies: [toutes les anomalies]
    }
    """
    result = {
        "total_anomalies": 0,
        "major":           0,
        "minor":           0,
        "info":            0,
        "lines_analyzed":  0,
        "by_sheet":        {},
        "all_anomalies":   [],
    }

    data_tables = parse_result.get("data_tables", [])
    ref_tables  = parse_result.get("ref_tables", [])
    # Toutes les tables non-système sont désormais contrôlées par Axe A.
    tables_to_validate = data_tables + ref_tables

    metadata = parse_result.get("metadata", {})
    sheets   = parse_result.get("sheets", {})

    for sheet_name in tables_to_validate:
        df = sheets.get(sheet_name)
        if df is None or df.empty:
            continue

        meta       = metadata.get(sheet_name, {})
        table_id   = meta.get("table_id", "")

        result["lines_analyzed"] += len(df)

        # Lancer la validation Axe A
        anomalies = validate_axe_a(
            df=df,
            table_id=table_id,
            sheet_name=sheet_name,
        )

        result["by_sheet"][sheet_name] = anomalies
        result["all_anomalies"].extend(anomalies)

    # Comptages
    result["total_anomalies"] = len(result["all_anomalies"])
    result["major"] = sum(
        1 for a in result["all_anomalies"] if a["Sévérité"] == "Majeure"
    )
    result["minor"] = sum(
        1 for a in result["all_anomalies"] if a["Sévérité"] == "Mineure"
    )
    result["info"] = sum(
        1 for a in result["all_anomalies"] if a["Sévérité"] == "Info"
    )

    return result


def get_anomalies_dataframe(anomalies: list) -> pd.DataFrame:
    """
    Convertit la liste d'anomalies en DataFrame pour affichage Streamlit.
    """
    if not anomalies:
        return pd.DataFrame()

    df = pd.DataFrame(anomalies)

    # Ordre des colonnes
    cols = [
        "Ligne", "Onglet", "Champ", "Valeur",
        "Type d'anomalie", "Sévérité", "Message",
        "Correction suggérée", "Axe"
    ]
    existing_cols = [c for c in cols if c in df.columns]
    return df[existing_cols]
