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


# ── Structures de données ─────────────────────────────────────────────────────

@dataclass
class TablePlan:
    table_id:         int
    table_name:       str
    processing_order: int  = 1
    skip_triggers:    bool = False   # FALSE = Apply package déclenche OnInsert/OnModify
    delete_before:    bool = False   # TRUE  = BC supprime les enregistrements avant import


@dataclass
class ExecutionPlan:
    """
    Plan d'exécution complet pour un package BC.
    Utilisé par validate_file_axe_a, validate_file_axe_b, trigger_simulator.
    """
    package_code: str
    tables:       dict[int, TablePlan]        = field(default_factory=dict)
    # {table_id: {field_name: validate_field}}
    fields:       dict[int, dict[str, bool]]  = field(default_factory=dict)
    source:       str = "default"   # "bc_api" | "default"

    def skip_triggers_for(self, table_id: int) -> bool:
        """True si BC ne déclenche pas les triggers pour cette table."""
        t = self.tables.get(table_id)
        return t.skip_triggers if t else False

    def validate_field_for(self, table_id: int, field_name: str) -> bool:
        """
        True si BC vérifie ce champ via ValidateFieldRelationAgainstCompanyDataAndPackage.
        Si le plan vient du fallback (source='default'), tous les champs sont validés.
        """
        tbl_fields = self.fields.get(table_id)
        if tbl_fields is None:
            return True   # fallback : valider tout
        return tbl_fields.get(field_name, True)

    def get_tables_ordered(self) -> list[TablePlan]:
        """Retourne les tables triées par (processing_order, table_id) — ordre BC réel."""
        return sorted(
            self.tables.values(),
            key=lambda t: (t.processing_order, t.table_id),
        )


# ── Constructeurs ─────────────────────────────────────────────────────────────

def build_default_plan(package_code: str = "") -> ExecutionPlan:
    """
    Plan par défaut quand l'extension AL n'est pas disponible.
    Valide tout (comportement le plus strict = plus de valeur ajoutée).
    """
    return ExecutionPlan(
        package_code=package_code,
        source="default",
    )


def build_plan_from_bc(
    tenant_id:    str,
    environment:  str,
    company_id:   str,
    package_code: str,
    token:        str,
) -> ExecutionPlan:
    """
    Construit le plan d'exécution en lisant l'extension Talan QC.

    Appels API :
      GET /packageTables?$filter=packageCode eq '{code}'
        → processingOrder, skipTableTriggers, deleteBeforeProcessing

      GET /packageFields?$filter=packageCode eq '{code}' and tableId eq {id}
        → fieldName, validateField
        (appelé pour chaque table, résultats mis en cache 10 min)

    Returns:
        ExecutionPlan peuplé depuis BC, ou plan par défaut si erreur.
    """
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

        tp = TablePlan(
            table_id         = tid,
            table_name       = pt.get("tableName", str(tid)),
            processing_order = int(pt.get("processingOrder", 1) or 1),
            skip_triggers    = bool(pt.get("skipTableTriggers", False)),
            delete_before    = bool(pt.get("deleteBeforeProcessing", False)),
        )
        plan.tables[tid] = tp

        # Validate Field par champ
        try:
            pkg_fields = get_package_fields_qc(
                tenant_id, environment, company_id, package_code, tid, token
            )
            plan.fields[tid] = {
                pf.get("fieldName", ""): bool(pf.get("validateField", True))
                for pf in pkg_fields
                if pf.get("fieldName")
            }
        except Exception:
            # Fallback pour cette table : valider tous les champs
            plan.fields[tid] = {}

    return plan


def get_execution_plan(
    profile_code: str,
    company_id:   str,
    package_code: str,
) -> ExecutionPlan:
    """
    Point d'entrée principal depuis Sessions.

    Si package_code est vide → plan par défaut (pas de package sélectionné).
    Si extension AL indisponible → plan par défaut avec warning loggué.

    Args:
        profile_code : code profil client (pour charger les credentials)
        company_id   : ID société BC sélectionnée dans Sessions
        package_code : code package (ex: "003K-ARTICLE"), "" si non sélectionné

    Returns:
        ExecutionPlan prêt à l'emploi
    """
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
