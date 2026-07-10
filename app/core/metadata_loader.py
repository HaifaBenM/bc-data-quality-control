"""
Metadata Loader — types de champs et relations de table BC.

Stratégie de chargement (par priorité) :
  1. Cache Supabase (bc_metadata_cache) — chargé lors de la config du profil
  2. FIELD_DEFS de validator_axe_a.py — fallback statique pour tables connues
  3. Valeur par défaut (type Text, pas de relation) — si rien d'autre

Le metadata_loader est appelé une fois par session, avant la boucle de validation.
Il fournit à Axe A et Axe B les informations nécessaires :
  - Type BC de chaque champ (pour la validation de format)
  - Longueur maximale (pour la validation de longueur)
  - Obligatoire (PK ou requis)
  - Table de référence (pour Axe B, active uniquement si validate_field=TRUE)
"""
from __future__ import annotations
from dataclasses import dataclass, field


# ── Structures ────────────────────────────────────────────────────────────────

@dataclass
class FieldMeta:
    """Métadonnées d'un champ BC."""
    field_name:   str
    bc_type:      str  = "Text"    # Code, Text, Integer, Decimal, Date, Boolean, Option
    max_length:   int  = 0         # 0 = illimité
    required:     bool = False     # champ obligatoire (PK ou requis)
    ref_table_id: int  = 0         # 0 = pas de TableRelation
    ref_table_name: str = ""
    is_custom:    bool = False     # champ d'extension (No ≥ 50000)


@dataclass
class TableMeta:
    """Métadonnées d'une table BC."""
    table_id:   int
    table_name: str
    fields:     dict[str, FieldMeta] = field(default_factory=dict)


# ── Mappings FIELD_DEFS ────────────────────────────────────────────────────────
# Correspondance champ BC → TableRelation (ref_table_id)
# Source : tests empiriques + schéma BC standard
_TABLE_RELATIONS: dict[str, dict[str, int]] = {
    "18": {   # Customer
        "Groupe compta. client":        91,
        "Groupe compta. marché":        15,
        "Code conditions paiement":      3,
        "Code conditions livraison":    10,
        "Code mode expédition":         10,
        "Code vendeur":                 13,
        "Code magasin":                 14,
        "Code pays/région":              9,
        "Devise":                        4,
        "Code langue":                   8,
        "Groupe compta. marché TVA":    74,
    },
    "23": {   # Vendor
        "Groupe compta. fourn.":        92,
        "Groupe compta. marché":        15,
        "Code conditions paiement":      3,
        "Code conditions livraison":    10,
        "Code mode expédition":         10,
        "Code acheteur":                13,
        "Code pays/région":              9,
        "Devise":                        4,
        "Groupe compta. marché TVA":    74,
    },
    "27": {   # Item
        "Groupe compta. stock":         94,
        "Groupe compta. produit":       15,
        "Code catégorie article":     5722,
        "Unité de base":               204,
        "Code traçabilité":           6502,
        "Groupe compta. produit TVA":   74,
    },
    "15": {   # G/L Account
        "Groupe compta. produit":       15,
        "Groupe compta. produit TVA":   74,
    },
    "3": {},  # Payment Terms — pas de relation externe
    "4": {},  # Currency
    "9": {},  # Country/Region
}


def _field_defs_to_meta(table_id_str: str) -> TableMeta | None:
    """
    Construit une TableMeta depuis FIELD_DEFS (validator_axe_a.py).
    Enrichit avec les TableRelations connues.
    """
    try:
        from app.core.validator_axe_a import FIELD_DEFS
    except ImportError:
        return None

    fd_table = FIELD_DEFS.get(table_id_str)
    if fd_table is None:
        return None

    table_id   = int(table_id_str)
    table_rels = _TABLE_RELATIONS.get(table_id_str, {})

    fields: dict[str, FieldMeta] = {}
    for fname, fd in fd_table.items():
        fields[fname] = FieldMeta(
            field_name    = fname,
            bc_type       = fd.get("type", "Text"),
            max_length    = int(fd.get("max", 0) or 0),
            required      = bool(fd.get("req", False)),
            ref_table_id  = table_rels.get(fname, 0),
            ref_table_name = "",
            is_custom     = False,
        )

    return TableMeta(
        table_id   = table_id,
        table_name = f"Table {table_id}",
        fields     = fields,
    )


def _default_field(field_name: str) -> FieldMeta:
    """Champ par défaut quand aucune métadonnée n'est disponible."""
    return FieldMeta(field_name=field_name, bc_type="Text")


# ── Point d'entrée principal ──────────────────────────────────────────────────

class MetadataLoader:
    """
    Charge et met en cache les métadonnées des tables pour une session.
    Instancié une fois par session de validation.
    """

    def __init__(self, profile_code: str, company_id: str = "") -> None:
        self.profile_code = profile_code
        self.company_id   = company_id
        self._cache: dict[int, TableMeta] = {}

    def get_table_meta(self, table_id: int, headers: list[str] | None = None) -> TableMeta:
        """
        Retourne les métadonnées d'une table.
        Ordre de priorité :
          1. Cache en mémoire (déjà chargé cette session)
          2. Cache Supabase (bc_metadata_cache)
          3. FIELD_DEFS statiques
          4. Défaut (Text pour tout)

        Args:
            table_id : ID de la table BC
            headers  : noms des colonnes dans le fichier (pour créer les champs manquants)
        """
        if table_id in self._cache:
            return self._cache[table_id]

        # Tentative FIELD_DEFS
        meta = _field_defs_to_meta(str(table_id))

        # Tentative cache Supabase
        if meta is None:
            meta = self._load_from_supabase(table_id)

        # Fallback : créer une TableMeta minimale avec les headers
        if meta is None:
            meta = TableMeta(
                table_id   = table_id,
                table_name = f"Table {table_id}",
                fields     = {
                    h: _default_field(h)
                    for h in (headers or [])
                },
            )

        # Ajouter les headers manquants avec valeur par défaut
        if headers:
            for h in headers:
                if h not in meta.fields:
                    meta.fields[h] = _default_field(h)

        self._cache[table_id] = meta
        return meta

    def get_field_meta(
        self,
        table_id:   int,
        field_name: str,
        headers:    list[str] | None = None,
    ) -> FieldMeta:
        """Retourne les métadonnées d'un champ spécifique."""
        table_meta = self.get_table_meta(table_id, headers)
        return table_meta.fields.get(field_name, _default_field(field_name))

    def _load_from_supabase(self, table_id: int) -> TableMeta | None:
        """
        Tente de charger les métadonnées depuis bc_metadata_cache Supabase.
        Retourne None si absent ou en cas d'erreur.
        """
        try:
            from app.db.metadata_db import get_cached_metadata
            row = get_cached_metadata(self.profile_code, f"table_{table_id}")
            if not row:
                return None

            raw_fields = row.get("fields", [])
            if not isinstance(raw_fields, list):
                return None

            fields: dict[str, FieldMeta] = {}
            table_rels = _TABLE_RELATIONS.get(str(table_id), {})

            for f in raw_fields:
                fname = f.get("name", "")
                if not fname:
                    continue
                fields[fname] = FieldMeta(
                    field_name    = fname,
                    bc_type       = f.get("type", "Text"),
                    max_length    = int(f.get("max_length", 0) or 0),
                    required      = bool(f.get("required", False)),
                    ref_table_id  = table_rels.get(fname, 0),
                    ref_table_name = f.get("ref_table", ""),
                    is_custom     = int(f.get("field_no", 0) or 0) >= 50000,
                )

            return TableMeta(
                table_id   = table_id,
                table_name = row.get("entity_name", f"Table {table_id}"),
                fields     = fields,
            ) if fields else None

        except Exception:
            return None

    def get_ref_table_id(self, table_id: int, field_name: str) -> int:
        """
        Retourne l'ID de la table référencée par un champ FK.
        0 si pas de relation connue.
        """
        fm = self.get_field_meta(table_id, field_name)
        return fm.ref_table_id
