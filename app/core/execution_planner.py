from __future__ import annotations
from dataclasses import dataclass, field


_AL_TYPE_MAP: dict[str, str] = {
    "Text":      "Text",
    "Code":      "Text",
    "Integer":   "Integer",
    "Decimal":   "Decimal",
    "Boolean":   "Boolean",
    "Date":      "Date",
    # Time/DateTime/GUID : FldRef.Length() renvoie une taille de stockage
    # binaire AL (4/8/16), pas un nombre de caractères. Les mapper vers "Text"
    # déclenchait à tort le check de longueur Axe A (ex: GUID 38 car. > "max"
    # 16 alors que BC lui-même ne signale aucune erreur sur ces champs).
    # Type distinct volontaire pour ne matcher ni le check longueur
    # (py_type in ("Text", None)) ni aucun des elif de validation de type.
    "Time":      "Time",
    "DateTime":  "DateTime",
    "GUID":      "Guid",
    "Option":    "Option",
    "BigInteger":"Integer",
    "Blob":      None,
    "RecordID":  None,
}

_OPTION_VALUES: dict[str, dict[str, list[str]]] = {
    "18": {
        "Bloqué":      ["", " ", "Expédier", "Facture", "Tous", "Livraison", "Tout"],
        "Application": ["", " ", "Manuel", "Par date échéance", "Par date document"],
    },
    "23": {
        "Bloqué": ["", " ", "Paiement", "Facture", "Tous", "Tout"],
    },
    "27": {
        "Type": ["", " ", "Stock", "Service", "Hors stock"],
    },
    "15": {
        "Type compte":          ["", " ", "Reportage", "Total", "Début total", "Fin total"],
        "Catégorie compte":     ["", " ", "Actif", "Passif", "Fonds propres",
                                 "Produits", "Charges", "Coût des marchandises"],
        "Type comptabilisation":["", " ", "Vente", "Achat"],
    },
}

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "18": ["N°", "Nom", "Groupe compta. client", "Groupe compta. marché"],
    "23": ["N°", "Nom", "Groupe compta. fournisseur", "Groupe compta. marché"],
    # "Crédit carbone par unité" confirmé via comparaison erreurs BC réelles
    # (PKG003-Stock, session du 16/07/2026) : BC lève "Crédit GHG doit avoir
    # une valeur..." et légende l'erreur sur ce champ précis (pas "Crédit GHG"
    # le Boolean) sur 5/5 occurrences testées (items 1017, 1019, ACC001-3).
    "27": ["N°", "Unité de mesure de base", "Crédit carbone par unité"],
    "15": ["N°", "Nom", "Type compte"],
    "3":  ["Code"],
    "4":  ["Code"],
    "9":  ["Code"],
}

# Champs qui ne bloquent PAS l'import BC (pas de Mandatory=true déclenché par
# un Configuration Package) mais qui sont requis au moment de la
# comptabilisation (posting) — Gen. Posting Setup / Inventory Posting Setup
# vérifient la combinaison de groupes comptables uniquement lors d'une
# écriture de vente/achat/stock, pas à l'insertion de l'article. Confirmé
# empiriquement : items 1017/1019 importés par BC sans erreur malgré ces
# 3 champs vides (session du 16/07/2026, PKG003-Stock, 45 erreurs BC réelles
# ne mentionnent aucun de ces 3 champs). Anomalie Mineure/avisoire, pas
# bloquante — l'article existera mais sera inutilisable en comptabilisation
# tant que ces champs ne sont pas renseignés.
_POSTING_REQUIRED_FIELDS: dict[str, list[str]] = {
    "27": ["Description", "Groupe compta. stock", "Groupe compta. produit"],
}

_KEY_FIELD: dict[str, str] = {
    "18": "N°", "23": "N°", "27": "N°", "15": "N°", "5050": "N°",
    "3":  "Code", "4": "Code", "9": "Code", "10": "Code", "204": "Code",
    "default": "N°",
}


@dataclass
class FieldMeta:
    field_name:    str
    al_type:       str
    py_type:       str | None
    max_length:    int
    is_required:         bool = False
    is_posting_required: bool = False
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
    package_code:     str
    tables:           dict[int, TablePlan]            = field(default_factory=dict)
    fields:           dict[int, dict[str, bool]]      = field(default_factory=dict)
    fields_ref:       dict[int, dict[str, int]]       = field(default_factory=dict)
    fields_ref_field: dict[int, dict[str, int]]       = field(default_factory=dict)
    fields_meta:      dict[int, dict[str, FieldMeta]] = field(default_factory=dict)
    source:           str = "default"

    def skip_triggers_for(self, table_id: int) -> bool:
        t = self.tables.get(table_id)
        return t.skip_triggers if t else False

    def validate_field_for(self, table_id: int, field_name: str) -> bool:
        tbl = self.fields.get(table_id)
        if tbl is None:
            return True
        return tbl.get(field_name, True)

    def get_ref_table_id(self, table_id: int, field_name: str) -> int:
        return self.fields_ref.get(table_id, {}).get(field_name, 0)

    def get_ref_field_id(self, table_id: int, field_name: str) -> int:
        return self.fields_ref_field.get(table_id, {}).get(field_name, 0)

    def get_field_def(self, table_id: int, field_name: str) -> FieldMeta | None:
        return self.fields_meta.get(table_id, {}).get(field_name)

    def get_field_defs_for_table(self, table_id: int) -> dict[str, FieldMeta]:
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
    field_name = pf.get("fieldCaption", "") or pf.get("fieldInternalName", "")
    if not field_name:
        return None

    al_type    = str(pf.get("fieldType") or "").strip()
    py_type    = _AL_TYPE_MAP.get(al_type)
    max_length = int(pf.get("fieldLength") or 0)
    tid_str    = str(table_id)
    is_req     = field_name in _REQUIRED_FIELDS.get(tid_str, [])
    is_post_req= field_name in _POSTING_REQUIRED_FIELDS.get(tid_str, [])
    opts       = _OPTION_VALUES.get(tid_str, {}).get(field_name, [])

    return FieldMeta(
        field_name=field_name,
        al_type=al_type,
        py_type=py_type,
        max_length=max_length,
        is_required=is_req,
        is_posting_required=is_post_req,
        option_values=opts,
    )


# Log debug global — rempli pendant build_plan_from_bc
_debug_sample: list = []


def build_plan_from_bc(
    tenant_id:    str,
    environment:  str,
    company_id:   str,
    package_code: str,
    token:        str,
) -> ExecutionPlan:
    from app.core.bc_api import get_package_tables_qc, get_package_fields_qc

    global _debug_sample
    _debug_sample = []

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

            # ── DEBUG — stocker un échantillon pour affichage ─────────────────
            if not _debug_sample and pkg_fields:
                _debug_sample = [
                    {
                        "table":      tid,
                        "field":      pf.get("fieldCaption", ""),
                        "refTableId": pf.get("refTableId"),
                        "refFieldId": pf.get("refFieldId"),
                        "fieldType":  pf.get("fieldType"),
                    }
                   for pf in pkg_fields if pf.get("fieldCaption") in ("Code pays/région", "Code emplacement par défaut") or tid != 14
                ]
            # ── FIN DEBUG ─────────────────────────────────────────────────────

            plan.fields[tid] = {
                pf.get("fieldCaption", ""): bool(pf.get("validateField", True))
                for pf in pkg_fields if pf.get("fieldCaption")
            }

            plan.fields_ref[tid] = {
                pf.get("fieldCaption", ""): int(pf.get("refTableId") or 0)
                for pf in pkg_fields if pf.get("fieldCaption")
            }

            plan.fields_ref_field[tid] = {
                pf.get("fieldCaption", ""): int(pf.get("refFieldId") or 0)
                for pf in pkg_fields if pf.get("fieldCaption")
            }

            meta_map: dict[str, FieldMeta] = {}
            for pf in pkg_fields:
                fm = _build_field_meta(tid, pf)
                if fm:
                    meta_map[fm.field_name] = fm
            plan.fields_meta[tid] = meta_map

        except Exception:
            plan.fields[tid]           = {}
            plan.fields_ref[tid]       = {}
            plan.fields_ref_field[tid] = {}
            plan.fields_meta[tid]      = {}

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

        tenant_id     = profile.get("bc_tenant_id",    "").strip()
        client_id     = profile.get("bc_client_id",    "").strip()
        client_secret = profile.get("bc_client_secret","").strip()
        environment   = profile.get("bc_environment",  "").strip()

        if not all([tenant_id, client_id, client_secret, environment]):
            return build_default_plan(package_code)

        token = get_access_token(tenant_id, client_id, client_secret)
        return build_plan_from_bc(
            tenant_id, environment, company_id, package_code, token
        )

    except Exception:
        return build_default_plan(package_code)