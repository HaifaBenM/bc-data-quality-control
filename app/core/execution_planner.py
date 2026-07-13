"""
Lecture du plan d'exécution BC depuis l'extension Talan QC Tools.

Pour un package donné, construit un plan qui indique :
  - Processing Order par table (ordre de traitement BC)
  - Skip Table Triggers par table (FALSE = OnInsert/OnValidate actifs)
  - Delete Before Processing par table
  - Validate Field par champ (TRUE = Axe B vérifie ce champ)

Ce plan est utilisé par les validators pour reproduire exactement
le comportement BC :
  - Axe A ne simule les triggers que si skip_triggers = FALSE
  - Axe B ne vérifie une référence que si validate_field = TRUE

Fallback : si l'extension n'est pas disponible ou si aucun package
n'est sélectionné, le plan retourne des valeurs par défaut
(skip_triggers=False, validate_field=True pour tous les champs).
"""
from __future__ import annotations
from dataclasses import dataclass, field


# ── Mapping FldRef.Type (AL) → type interne Axe A ────────────────────────────
_AL_TYPE_MAP: dict[str, str] = {
    "Text":      "Text",
    "Code":      "Text",      # Code = Text contraint, même validation
    "Integer":   "Integer",
    "Decimal":   "Decimal",
    "Boolean":   "Boolean",
    "Date":      "Date",
    "Time":      "Text",      # pas de validation spécifique
    "DateTime":  "Text",
    "Option":    "Option",
    "BigInteger":"Integer",
    "Blob":      None,        # ignoré
    "RecordID":  None,        # ignoré
    "GUID":      "Text",
}

# Option fields BC — valeurs connues par table+champ (complément dynamique)
# Axe A ne peut pas inférer les valeurs Option depuis AL (FldRef.Type = Option
# mais FldRef ne retourne pas les captions). On garde le dict statique pour ça.
_OPTION_VALUES: dict[str, dict[str, list[str]]] = {
    "18": {
        "Bloqué":       ["", " ", "Expédier", "Facture", "Tous", "Livraison", "Tout"],
        "Application":  ["", " ", "Manuel", "Par date échéance", "Par date document"],
    },
    "23": {
        "Bloqué":       ["", " ", "Paiement", "Facture", "Tous", "Tout"],
    },
    "27": {
        "Type":         ["", " ", "Stock", "Service", "Hors stock"],
    },
    "15": {
        "Type compte":          ["", " ", "Reportage", "Total", "Début total", "Fin total"],
        "Catégorie compte":     ["", " ", "Actif", "Passif", "Fonds propres",
                                 "Produits", "Charges", "Coût des marchandises"],
        "Type comptabilisation":["", " ", "Vente", "Achat"],
    },
}

# Champs obligatoires connus — AL n'expose pas NotBlank via FldRef
# On garde cette connaissance statique, indépendante du type/longueur
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "18": ["N°", "Nom", "Groupe compta. client", "Groupe compta. marché"],
    "23": ["N°", "Nom", "Groupe compta. fournisseur", "Groupe compta. marché"],
    "27": ["N°", "Description", "Unité de mesure de base",
           "Groupe compta. stock", "Groupe compta. produit"],
    "15": ["N°", "Nom", "Type compte"],
    "3":  ["Code"],
    "4":  ["Code"],
    "9":  ["Code"],
}

# Champ clé par table
_KEY_FIELD: dict[str, str] = {
    "18": "N°", "23": "N°", "27": "N°", "15": "N°", "5050": "N°",
    "3": "Code", "4": "Code", "9": "Code", "10": "Code", "204": "Code",
    "default": "N°",
}


@dataclass
class FieldMeta:
    """Métadonnées d'un champ issues de l'extension AL (fieldType + fieldLength)."""
    field_name:    str
    al_type:       str        # valeur brute FldRef.Type : "Text", "Integer"…
    py_type:       str | None # type interne Axe A : "Text", "Integer"…
    max_length:    int        # FldRef.Length — 0 si non applicable
    is_required:   bool = False
    option_values: list[str] = field(default_factory=list)


@dataclass
class TablePlan:
    table_id:         int
    table_name:       str
    processing_order: int  = 1
    skip_triggers:    bool = False
    delete_before:    bool = False


@dataclass
class ExecutionPlan:
    package_code: str
    tables:       dict[int, TablePlan]          = field(default_factory=dict)
    fields:       dict[int, dict[str, bool]]    = field(default_factory=dict)
    fields_ref:   dict[int, dict[str, int]]     = field(default_factory=dict)
    # NOUVEAU : {table_id_int: {field_name: FieldMeta}}
    fields_meta:  dict[int, dict[str, FieldMeta]] = field(default_factory=dict)
    source:       str = "default"

    def skip_triggers_for(self, table_id: int) -> bool:
        t = self.tables.get(table_id)
        return t.skip_triggers if t else False

    def validate_field_for(self, table_id: int, field_name: str) -> bool:
        tbl_fields = self.fields.get(table_id)
        if tbl_fields is None:
            return True
        return tbl_fields.get(field_name, True)

    def get_ref_table_id(self, table_id: int, field_name: str) -> int:
        return self.fields_ref.get(table_id, {}).get(field_name, 0)

    def get_field_def(self, table_id: int, field_name: str) -> FieldMeta | None:
        """
        Retourne les métadonnées AL d'un champ pour Axe A.
        None si le plan vient du fallback ou si le champ est inconnu.
        """
        return self.fields_meta.get(table_id, {}).get(field_name)

    def get_field_defs_for_table(self, table_id: int) -> dict[str, FieldMeta]:
        """Retourne tous les FieldMeta d'une table. {} si inconnu."""
        return self.fields_meta.get(table_id, {})

    def get_key_field(self, table_id: int) -> str:
        return _KEY_FIELD.get(str(table_id), _KEY_FIELD["default"])

    def get_tables_ordered(self) -> list[TablePlan]:
        return sorted(
            self.tables.values(),
            key=lambda t: (t.processing_order, t.table_id),
        )


def build_default_plan(package_code: str = "") -> ExecutionPlan:
    return ExecutionPlan(package_code=package_code, source="default")


def _build_field_meta(table_id: int, pf: dict) -> FieldMeta | None:
    """
    Construit un FieldMeta depuis une entrée /packageFields AL.
    Enrichit avec options et req depuis les dicts statiques
    (AL n'expose pas NotBlank ni les captions Option).
    """
    field_name = pf.get("fieldName", "") or pf.get("fieldInternalName", "")
    if not field_name:
        return None

    al_type    = str(pf.get("fieldType") or "").strip()
    py_type    = _AL_TYPE_MAP.get(al_type)
    max_length = int(pf.get("fieldLength") or 0)

    # Enrichissement statique minimal
    tid_str    = str(table_id)
    is_req     = field_name in _REQUIRED_FIELDS.get(tid_str, [])
    opts       = _OPTION_VALUES.get(tid_str, {}).get(field_name, [])

    return FieldMeta(
        field_name=field_name,
        al_type=al_type,
        py_type=py_type,
        max_length=max_length,
        is_required=is_req,
        option_values=opts,
    )


def build_plan_from_bc(
    tenant_id:    str,
    environment:  str,
    company_id:   str,
    package_code: str,
    token:        str,
) -> ExecutionPlan:
    from app.core.bc_api import get_package_tables_qc, get_package_fields_qc

    plan = ExecutionPlan(package_code=package_code, source="bc_api")

    try:
        pkg_tables = get_package_tables_qc(
            tenant_id, environment, company_id, package_code, token
        )
    except Exception:
        return build_default_plan(package_code)

    for pt in pkg_tables:
        tid = pt.get("tableId", 0)
        if not tid:
            continue

        plan.tables[tid] = TablePlan(
            table_id         = tid,
            table_name       = pt.get("tableName", str(tid)),
            processing_order = int(pt.get("processingOrder", 1) or 1),
            skip_triggers    = bool(pt.get("skipTableTriggers", False)),
            delete_before    = bool(pt.get("deleteBeforeProcessing", False)),
        )

        try:
            pkg_fields = get_package_fields_qc(
                tenant_id, environment, company_id, package_code, tid, token
            )

            plan.fields[tid] = {
                pf.get("fieldName", ""): bool(pf.get("validateField", True))
                for pf in pkg_fields if pf.get("fieldName")
            }
            plan.fields_ref[tid] = {
                pf.get("fieldName", ""): int(pf.get("refTableId") or 0)
                for pf in pkg_fields if pf.get("fieldName")
            }

            # NOUVEAU : stockage fieldType + fieldLength
            meta_map: dict[str, FieldMeta] = {}
            for pf in pkg_fields:
                fm = _build_field_meta(tid, pf)
                if fm:
                    meta_map[fm.field_name] = fm
            plan.fields_meta[tid] = meta_map

        except Exception:
            plan.fields[tid]      = {}
            plan.fields_ref[tid]  = {}
            plan.fields_meta[tid] = {}

    return plan


def get_execution_plan(
    profile_code: str,
    company_id:   str,
    package_code: str,
) -> ExecutionPlan:
    if not package_code or not company_id:
        return build_default_plan(package_code)

    try:
        from app.db.profiles_db import get_profile_by_code
        from app.core.bc_api import get_access_token

        profile = get_profile_by_code(profile_code)
        if not profile:
            return build_default_plan(package_code)

        tenant_id     = profile.get("bc_tenant_id", "").strip()
        client_id     = profile.get("bc_client_id", "").strip()
        client_secret = profile.get("bc_client_secret", "").strip()
        environment   = profile.get("bc_environment", "").strip()

        if not all([tenant_id, client_id, client_secret, environment]):
            return build_default_plan(package_code)

        token = get_access_token(tenant_id, client_id, client_secret)

        return build_plan_from_bc(
            tenant_id, environment, company_id, package_code, token
        )

    except Exception:
        return build_default_plan(package_code)