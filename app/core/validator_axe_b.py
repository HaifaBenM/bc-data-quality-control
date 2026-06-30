"""
Validation Axe B — Vérification des codes de référence BC.
Vérifie que les codes saisis existent dans les tables de référence.

Sources (par ordre de priorité) :
  1. Onglets de référence du fichier uploadé (ex: "Conditions de paiement")
  2. Cache Supabase (chargé depuis BC en Sprint 3)
  3. Si aucune source → champ non vérifiable (Info, pas d'erreur bloquante)
"""
import pandas as pd
from app.db.metadata_db import get_reference_values


# ══════════════════════════════════════════════════════════════════════════════
# MAPPING : champ de données → table de référence
# Clé = table_id BC, Valeur = {champ_données: config_référence}
# ══════════════════════════════════════════════════════════════════════════════

REFERENCE_MAP = {

    # ── Table 18 — Clients ─────────────────────────────────────────────────────
    "18": {
        "Code conditions paiement": {
            "patterns":  ["Conditions de paiement", "Condition paiement"],
            "key":       "Code",
            "label":     "Conditions de paiement",
            "cache_key": "paymentTerms",
        },
        "Code devise": {
            "patterns":  ["Devise", "4 Devise"],
            "key":       "Code",
            "label":     "Devises",
            "cache_key": "currencies",
        },
        "Code pays/région": {
            "patterns":  ["Pays", "9 Pays", "Paysrégion"],
            "key":       "Code",
            "label":     "Pays/Régions",
            "cache_key": "countriesRegions",
        },
        "Code vendeur": {
            "patterns":  ["Vendeur", "VendeurAcheteur", "13 Vendeur"],
            "key":       "Code",
            "label":     "Vendeurs/Acheteurs",
            "cache_key": "salespeople",
        },
        "Code magasin": {
            "patterns":  ["Magasin", "14 Magasin"],
            "key":       "Code",
            "label":     "Magasins",
            "cache_key": "locations",
        },
        "Groupe compta. client": {
            "patterns":  ["Groupe compta. client", "92 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. client",
            "cache_key": None,
        },
        "Groupe compta. marché": {
            "patterns":  ["Groupe compta. marché", "250 Groupe compta. marché"],
            "key":       "Code",
            "label":     "Groupes compta. marché",
            "cache_key": None,
        },
        "Groupe compta. marché TVA": {
            "patterns":  ["marché TVA", "323 Groupe", "TVA marché"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        "Code mode de paiement": {
            "patterns":  ["Mode de règlement", "289 Mode", "Mode paiement"],
            "key":       "Code",
            "label":     "Modes de règlement",
            "cache_key": "paymentMethods",
        },
        "Code condition relance": {
            "patterns":  ["Relance", "292 Condition"],
            "key":       "Code",
            "label":     "Conditions de relance",
            "cache_key": None,
        },
        "Code transporteur": {
            "patterns":  ["Transporteur", "291 Transporteur"],
            "key":       "Code",
            "label":     "Transporteurs",
            "cache_key": None,
        },
        "Groupe prix client": {
            "patterns":  ["Prix client", "6 Groupe prix"],
            "key":       "Code",
            "label":     "Groupes prix client",
            "cache_key": None,
        },
        "Groupe remises client": {
            "patterns":  ["Remise client", "7 Groupe remise"],
            "key":       "Code",
            "label":     "Groupes remises client",
            "cache_key": None,
        },
        "Code langue": {
            "patterns":  ["Langue", "8 Langue"],
            "key":       "Code",
            "label":     "Langues",
            "cache_key": None,
        },
    },

    # ── Table 23 — Fournisseurs ────────────────────────────────────────────────
    "23": {
        "Code conditions paiement": {
            "patterns":  ["Conditions de paiement"],
            "key":       "Code",
            "label":     "Conditions de paiement",
            "cache_key": "paymentTerms",
        },
        "Code devise": {
            "patterns":  ["Devise"],
            "key":       "Code",
            "label":     "Devises",
            "cache_key": "currencies",
        },
        "Code pays/région": {
            "patterns":  ["Pays", "Paysrégion"],
            "key":       "Code",
            "label":     "Pays/Régions",
            "cache_key": "countriesRegions",
        },
        "Groupe compta. fournisseur": {
            "patterns":  ["Groupe compta. fournisseur", "93 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. fournisseur",
            "cache_key": None,
        },
        "Groupe compta. marché": {
            "patterns":  ["Groupe compta. marché", "250 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché",
            "cache_key": None,
        },
        "Groupe compta. marché TVA": {
            "patterns":  ["marché TVA", "323 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        "Code mode de paiement": {
            "patterns":  ["Mode de règlement"],
            "key":       "Code",
            "label":     "Modes de règlement",
            "cache_key": "paymentMethods",
        },
        "Code acheteur": {
            "patterns":  ["Vendeur", "VendeurAcheteur"],
            "key":       "Code",
            "label":     "Acheteurs",
            "cache_key": "salespeople",
        },
    },

    # ── Table 27 — Articles ────────────────────────────────────────────────────
    "27": {
        "Unité de mesure de base": {
            "patterns":  ["Unité de mesure", "204 Unité"],
            "key":       "Code",
            "label":     "Unités de mesure",
            "cache_key": "unitOfMeasures",
        },
        "Groupe compta. stock": {
            "patterns":  ["Groupe compta. stock", "94 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. stock",
            "cache_key": None,
        },
        "Groupe compta. produit": {
            "patterns":  ["Groupe compta. produit", "252 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. produit",
            "cache_key": None,
        },
        "Groupe compta. produit TVA": {
            "patterns":  ["produit TVA", "325 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. produit TVA",
            "cache_key": None,
        },
        "Code catégorie article": {
            "patterns":  ["Catégorie article"],
            "key":       "Code",
            "label":     "Catégories d'articles",
            "cache_key": "itemCategories",
        },
    },

    # ── Table 15 — Plan comptable ──────────────────────────────────────────────
    "15": {
        "Groupe compta. marché": {
            "patterns":  ["Groupe compta. marché", "250 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché",
            "cache_key": None,
        },
        "Groupe compta. produit": {
            "patterns":  ["Groupe compta. produit", "252 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. produit",
            "cache_key": None,
        },
        "Groupe compta. marché TVA": {
            "patterns":  ["marché TVA", "323 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. marché TVA",
            "cache_key": None,
        },
        "Groupe compta. produit TVA": {
            "patterns":  ["produit TVA", "325 Groupe"],
            "key":       "Code",
            "label":     "Groupes compta. produit TVA",
            "cache_key": None,
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _normalize(value: str) -> str:
    """Normalise une valeur pour comparaison : strip + espaces insécables."""
    return (
        str(value)
        .strip()
        .replace("\xa0", " ")   # espace insécable → espace normal
        .replace("\u202f", " ") # espace fine insécable
        .strip()
    )


def _find_ref_sheet(all_sheets: dict, patterns: list) -> str | None:
    """
    Trouve le nom de l'onglet de référence dans le fichier.
    Cherche par correspondance partielle (case-insensitive).
    """
    for sheet_name in all_sheets.keys():
        sheet_norm = sheet_name.lower().replace(" ", "").replace("-", "")
        for pattern in patterns:
            pat_norm = pattern.lower().replace(" ", "").replace("-", "")
            if pat_norm in sheet_norm or sheet_norm in pat_norm:
                return sheet_name
    return None


def _get_valid_codes(df: pd.DataFrame, key_field: str = "Code") -> set:
    """
    Extrait les codes valides depuis un DataFrame de référence.
    Gère les espaces insécables et la casse.
    """
    # Trouver la colonne clé (peut avoir des espaces ou des variantes)
    actual_key = None
    for col in df.columns:
        if _normalize(str(col)).lower() == key_field.lower():
            actual_key = col
            break

    if actual_key is None and len(df.columns) > 0:
        actual_key = df.columns[0]  # Fallback : première colonne

    if actual_key is None:
        return set()

    codes = set()
    for val in df[actual_key].dropna():
        normalized = _normalize(str(val))
        if normalized and normalized.lower() != "nan":
            codes.add(normalized)
            codes.add(normalized.upper())
            codes.add(normalized.lower())

    return codes


# ══════════════════════════════════════════════════════════════════════════════
# MOTEUR DE VALIDATION AXE B
# ══════════════════════════════════════════════════════════════════════════════

def validate_axe_b(
    df:          pd.DataFrame,
    table_id:    str,
    all_sheets:  dict,
    sheet_name:  str = "",
    profile_code: str = "",
) -> list[dict]:
    """
    Valide les codes de référence d'un DataFrame BC contre les tables de référence.

    Args:
        df           : DataFrame des données client (ex: 18 Client)
        table_id     : numéro de table BC (ex: "18")
        all_sheets   : tous les onglets du fichier {sheet_name: DataFrame}
        sheet_name   : nom de l'onglet des données (pour les messages)
        profile_code : code profil pour accéder au cache Supabase

    Retourne liste d'anomalies (même structure qu'Axe A).
    """
    anomalies  = []
    field_refs = REFERENCE_MAP.get(table_id, {})

    if not field_refs:
        return anomalies

    # Pré-calculer les codes valides par référence (éviter recalcul à chaque ligne)
    ref_codes_cache = {}   # {field_name: (set_codes, source_label, found)}
    not_found_fields = set()  # champs dont la référence est introuvable

    for field_name, ref_config in field_refs.items():
        if field_name not in df.columns:
            continue  # Ce champ n'est pas dans ce fichier, ignorer

        # 1. Chercher dans le fichier
        ref_sheet = _find_ref_sheet(all_sheets, ref_config["patterns"])
        if ref_sheet:
            ref_df    = all_sheets[ref_sheet]
            codes     = _get_valid_codes(ref_df, ref_config["key"])
            source    = f"onglet '{ref_sheet}'"
            ref_codes_cache[field_name] = (codes, source, True)
            continue

        # 2. Chercher dans le cache Supabase
        if profile_code and ref_config.get("cache_key"):
            cached_codes = get_reference_values(
                profile_code, ref_config["cache_key"]
            )
            if cached_codes:
                codes  = set(c for c in cached_codes if c)
                source = f"cache BC ({ref_config['label']})"
                ref_codes_cache[field_name] = (codes, source, True)
                continue

        # 3. Référence introuvable
        not_found_fields.add(field_name)
        ref_codes_cache[field_name] = (set(), ref_config["label"], False)

    # ── Validation ligne par ligne ────────────────────────────────────────────
    for row_idx, row in df.iterrows():
        line_num = int(row_idx) + 1

        for field_name, (valid_codes, source, found) in ref_codes_cache.items():
            raw_val = row.get(field_name)

            # Ignorer les valeurs vides (déjà traité par Axe A si obligatoire)
            if raw_val is None or str(raw_val).strip() in ("", "nan", "None"):
                continue

            str_val  = _normalize(str(raw_val))
            if not str_val:
                continue

            if not found:
                # Référence introuvable — on ne peut pas valider
                # On signale seulement une fois (pas par ligne) → géré après
                continue

            if not valid_codes:
                continue

            # Vérifier si le code existe (insensible à la casse)
            str_val_up = str_val.upper()
            if str_val_up not in {c.upper() for c in valid_codes}:
                # Code introuvable dans la référence
                # Construire la liste des valeurs valides (max 5 pour lisibilité)
                sample = sorted({c for c in valid_codes if c})[:5]
                sample_str = ", ".join(f"'{v}'" for v in sample)
                if len(valid_codes) > 5:
                    sample_str += f" ... ({len(valid_codes)} valeurs)"

                anomalies.append({
                    "Ligne":              line_num,
                    "Onglet":             sheet_name,
                    "Champ":              field_name,
                    "Valeur":             str_val,
                    "Type d'anomalie":    "Code de référence invalide",
                    "Sévérité":           "Majeure",
                    "Message":            (
                        f"'{field_name}' = '{str_val}' n'existe pas dans "
                        f"{source}. "
                        f"Exemples valides : {sample_str}."
                    ),
                    "Correction suggérée": "",
                    "Axe":                "B",
                })

    # ── Ajouter les avertissements pour les références introuvables ───────────
    for field_name in not_found_fields:
        ref_config = field_refs.get(field_name, {})
        # Vérifier si le champ a des valeurs non vides dans les données
        if field_name in df.columns:
            has_values = df[field_name].dropna().astype(str).str.strip().ne("").any()
            if has_values:
                anomalies.append({
                    "Ligne":              0,  # 0 = avertissement global
                    "Onglet":             sheet_name,
                    "Champ":             field_name,
                    "Valeur":            "",
                    "Type d'anomalie":   "Référence non vérifiable",
                    "Sévérité":          "Info",
                    "Message":           (
                        f"Impossible de vérifier '{field_name}' : "
                        f"la table de référence '{ref_config.get('label', '')}' "
                        "n'est pas dans le fichier et n'est pas dans le cache BC. "
                        "Chargez la metadata BC depuis le profil client."
                    ),
                    "Correction suggérée": "",
                    "Axe":               "B",
                })

    return anomalies


def validate_file_axe_b(
    parse_result:  dict,
    profile_code:  str = "",
) -> dict:
    """
    Lance la validation Axe B sur TOUTES les tables analysables du fichier
    (data_tables + ref_tables).

    Avant : seules les tables classées "data" étaient à la fois (a) contrôlées
    elles-mêmes ET (b) candidates comme cible de la boucle externe — bien que
    `all_sheets` (passé à validate_axe_b) ait toujours contenu TOUTES les
    feuilles du fichier pour la résolution des lookups. Le problème n'était
    donc pas la résolution des références, mais le fait qu'une feuille comme
    "Conditions de paiement" n'était jamais elle-même la cible d'un contrôle
    Axe B (utile dès qu'une table de référence référence elle-même un autre
    code, ex: futures tables avec FK imbriquées).

    Maintenant : toute table non-système (data + ref) est contrôlée comme
    cible, tout en restant disponible comme source de lookup pour les autres
    — exactement le comportement de BC standard observé via
    ValidateFieldRelationAgainstCompanyDataAndPackage (vérifie une donnée à
    la fois contre la société ET contre le reste du package).

    Retourne :
    {
        total_anomalies, major, minor, info,
        lines_analyzed,
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
    # Toutes les tables non-système sont désormais contrôlées par Axe B.
    tables_to_validate = data_tables + ref_tables

    all_sheets = parse_result.get("sheets", {})
    metadata   = parse_result.get("metadata", {})

    for sheet_name in tables_to_validate:
        df = all_sheets.get(sheet_name)
        if df is None or df.empty:
            continue

        meta     = metadata.get(sheet_name, {})
        table_id = meta.get("table_id", "")

        result["lines_analyzed"] += len(df)

        anomalies = validate_axe_b(
            df=df,
            table_id=table_id,
            all_sheets=all_sheets,
            sheet_name=sheet_name,
            profile_code=profile_code,
        )

        result["by_sheet"][sheet_name] = anomalies
        result["all_anomalies"].extend(anomalies)

    result["total_anomalies"] = len(result["all_anomalies"])
    result["major"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Majeure")
    result["minor"] = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Mineure")
    result["info"]  = sum(1 for a in result["all_anomalies"] if a["Sévérité"] == "Info")

    return result
