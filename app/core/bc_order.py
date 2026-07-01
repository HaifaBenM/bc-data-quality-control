"""
Module bc_order — Reproduction de l'algorithme d'ordre d'intégration BC.

BC trie les tables d'un Configuration Package selon :
  1. Processing Order ASC  (calculé par récursion sur les FK des clés primaires)
  2. Table ID ASC          (à égalité de Processing Order)

Source : tests empiriques sur BC Online (breakOnError, codeunit 8611).
Référence : Resume_Conclusion_Integration_BC.docx — section 3.1 et 3.2.

Usage :
    from app.core.bc_order import sort_sheets_by_bc_order
    tables_ordered = sort_sheets_by_bc_order(sheet_names, parse_result["metadata"])
"""

# ══════════════════════════════════════════════════════════════════════════════
# DÉPENDANCES DE CLÉ PRIMAIRE PAR TABLE
#
# Clé   = Table ID (int)
# Valeur = liste des Table ID référencés dans la CLÉ PRIMAIRE de cette table
#
# Règle BC : Processing Order = max(ProcessingOrder(dépendance) + 1)
#            Si aucune dépendance → Processing Order = 1
#
# IMPORTANT : seules les FK dans la clé primaire comptent pour le calcul.
# Les FK dans les champs normaux (ex: Code conditions paiement → Table 3)
# n'affectent PAS le Processing Order — elles sont vérifiées par
# ValidateFieldRelationAgainstCompanyDataAndPackage (Valider Package).
# ══════════════════════════════════════════════════════════════════════════════

PK_RELATIONS: dict[int, list[int]] = {

    # ── N0 — Plan Comptable ───────────────────────────────────────────────────
    15:   [],       # G/L Account          — PK: No. (pas de FK)

    # ── N1 — Operational Setup ────────────────────────────────────────────────
    3:    [],       # Payment Terms         — PK: Code (pas de FK)
    10:   [],       # Shipment Method       — PK: Code (pas de FK)
    13:   [],       # Salesperson/Purchaser — PK: Code (pas de FK)
    14:   [],       # Location              — PK: Code (pas de FK)
    204:  [],       # Unit of Measure       — PK: Code (pas de FK)
    289:  [],       # Payment Method        — PK: Code (pas de FK)

    # ── N2 — Reference Data ───────────────────────────────────────────────────
    4:    [],       # Currency              — PK: Code (pas de FK)
    9:    [],       # Country/Region        — PK: Code (pas de FK)
    5722: [],       # Item Category         — PK: Code (pas de FK)

    # ── N3 — Master Data : Ventes ─────────────────────────────────────────────
    6:    [],       # Customer Price Group  — PK: Code (pas de FK)
    7:    [],       # Customer Disc. Group  — PK: Code (pas de FK)
    18:   [],       # Customer              — PK: No. (pas de FK)
    340:  [],       # Customer Disc. Group  — PK: Code (pas de FK)
    222:  [18],     # Ship-to Address       — PK: Customer No.(→18) + Code
    287:  [18],     # Customer Bank Account — PK: Customer No.(→18) + Code
    5050: [],       # Contact               — PK: No. (pas de FK dans PK)

    # ── N3 — Master Data : Achats ─────────────────────────────────────────────
    23:   [],       # Vendor                — PK: No. (pas de FK)
    288:  [23],     # Vendor Bank Account   — PK: Vendor No.(→23) + Code
    26:   [],       # Vendor Ledger Entry   — PK: Entry No. (pas de FK)

    # ── N3 — Master Data : Stock ──────────────────────────────────────────────
    27:   [],       # Item                  — PK: No. (pas de FK)
    5741: [27],     # Item Variant          — PK: Item No.(→27) + Code
    5717: [27],     # Item Reference        — PK: Item No.(→27) + Variant + UoM + Type + Ref No.
    5401: [27],     # Item Unit of Measure  — PK: Item No.(→27) + Code
    5404: [27],     # Item Unit of Measure  — PK: Item No.(→27) + Code (variante)

    # ── N3 — Master Data : Ressources ─────────────────────────────────────────
    76:   [],       # Resource Group        — PK: Code (pas de FK)
    156:  [],       # Resource              — PK: No. (pas de FK dans PK)

    # ── N3 — Master Data : Immobilisations ────────────────────────────────────
    5600: [],       # Fixed Asset           — PK: No. (pas de FK)
    5601: [5600],   # FA Depreciation Book  — PK: FA No.(→5600) + Depreciation Book Code
    5602: [5600],   # FA Allocation         — PK: FA No.(→5600) + Code

    # ── N4 — Transactional Data ───────────────────────────────────────────────
    81:   [],       # Gen. Journal Line     — PK: Template + Batch + Line No.
    83:   [],       # Item Journal Line     — PK: Template + Batch + Line No.
    36:   [],       # Sales Header          — PK: Document Type + No.
    37:   [36],     # Sales Line            — PK: Document Type + Document No.(→36) + Line No.
    38:   [],       # Purchase Header       — PK: Document Type + No.
    39:   [38],     # Purchase Line         — PK: Document Type + Document No.(→38) + Line No.
}


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITHME DE CALCUL DU PROCESSING ORDER
# Reproduction exacte de la logique BC (codeunit 8611 ApplyPackageTables)
# ══════════════════════════════════════════════════════════════════════════════

def calculate_processing_order(
    table_id: int,
    tables_in_package: set[int],
    visited: set[int] | None = None,
) -> int:
    """
    Calcule le Processing Order BC pour une table donnée.

    Règle BC :
      - Si aucune dépendance PK dans le package → 1
      - Sinon → max(ProcessingOrder(dépendance) + 1) pour toutes les dépendances
        présentes dans le package

    Args:
        table_id          : Table ID à calculer
        tables_in_package : Ensemble des Table ID présents dans le fichier
        visited           : Set interne pour la détection de cycle

    Returns:
        Processing Order (int, commence à 1)

    Raises:
        ValueError si un cycle est détecté (ne devrait pas arriver en données BC standard)
    """
    if visited is None:
        visited = set()

    if table_id in visited:
        raise ValueError(f"Cycle FK détecté sur Table ID {table_id}")

    visited.add(table_id)

    order = 1
    for dep_id in PK_RELATIONS.get(table_id, []):
        if dep_id in tables_in_package and dep_id != table_id:
            dep_order = calculate_processing_order(dep_id, tables_in_package, visited.copy())
            order = max(dep_order + 1, order)

    return order


def get_integration_order(table_ids: list[int]) -> list[int]:
    """
    Trie une liste de Table IDs dans l'ordre d'intégration BC.

    Ordre : Processing Order ASC, puis Table ID ASC (à égalité).

    Args:
        table_ids : Liste des Table IDs présents dans le fichier

    Returns:
        Liste triée des Table IDs dans l'ordre BC
    """
    tables_set = set(table_ids)
    orders: dict[int, int] = {}

    for tid in table_ids:
        try:
            orders[tid] = calculate_processing_order(tid, tables_set)
        except ValueError:
            # Cycle détecté → mettre en dernier (ne devrait pas arriver)
            orders[tid] = 999

    return sorted(table_ids, key=lambda t: (orders[t], t))


def get_processing_orders(table_ids: list[int]) -> dict[int, int]:
    """
    Retourne le Processing Order calculé pour chaque Table ID.
    Utile pour l'affichage dans l'UI.

    Returns:
        {table_id: processing_order}
    """
    tables_set = set(table_ids)
    result = {}
    for tid in table_ids:
        try:
            result[tid] = calculate_processing_order(tid, tables_set)
        except ValueError:
            result[tid] = 999
    return result


# ══════════════════════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE — UTILISÉE PAR LES VALIDATORS
# ══════════════════════════════════════════════════════════════════════════════

def sort_sheets_by_bc_order(
    sheet_names: list[str],
    metadata: dict,
) -> list[str]:
    """
    Trie une liste de noms d'onglets dans l'ordre d'intégration BC.

    Chaque onglet est associé à un Table ID via `metadata[sheet_name]["table_id"]`.
    Les onglets sans Table ID valide sont conservés à la fin, dans leur ordre d'origine.

    Args:
        sheet_names : Liste des noms d'onglets à trier
        metadata    : Dictionnaire {sheet_name: {"table_id": "18", ...}}

    Returns:
        Liste triée des noms d'onglets

    Exemple :
        Input  : ["18 Client", "222 Adresse", "3 Cond. Paiement"]
        Output : ["3 Cond. Paiement", "18 Client", "222 Adresse"]
        (Processing Orders : 3→1, 18→1, 222→2 ; à PO=1 on trie par Table ID : 3 < 18)
    """
    valid: list[tuple[str, int]] = []
    invalid: list[str] = []

    for sheet in sheet_names:
        tid_str = metadata.get(sheet, {}).get("table_id", "")
        try:
            tid = int(str(tid_str).strip())
            valid.append((sheet, tid))
        except (ValueError, TypeError):
            invalid.append(sheet)

    if not valid:
        return sheet_names

    # Calculer l'ordre sur les Table IDs uniques présents dans le fichier
    table_ids = [t for _, t in valid]
    ordered_ids = get_integration_order(table_ids)

    # Reconstruire la liste d'onglets dans l'ordre calculé
    # (gérer le cas où plusieurs onglets ont le même Table ID)
    id_to_sheets: dict[int, list[str]] = {}
    for sheet, tid in valid:
        id_to_sheets.setdefault(tid, []).append(sheet)

    result: list[str] = []
    for tid in ordered_ids:
        result.extend(id_to_sheets.get(tid, []))

    result.extend(invalid)
    return result


def get_bc_order_summary(sheet_names: list[str], metadata: dict) -> list[dict]:
    """
    Retourne un résumé de l'ordre BC pour affichage dans l'UI.

    Returns:
        Liste de dicts : [
            {"position": 1, "sheet": "3 Cond. Paiement", "table_id": 3,
             "processing_order": 1, "has_fk_risk": False},
            ...
        ]
    """
    valid: list[tuple[str, int]] = []
    for sheet in sheet_names:
        tid_str = metadata.get(sheet, {}).get("table_id", "")
        try:
            tid = int(str(tid_str).strip())
            valid.append((sheet, tid))
        except (ValueError, TypeError):
            pass

    if not valid:
        return []

    table_ids = [t for _, t in valid]
    tables_set = set(table_ids)
    po_map = get_processing_orders(table_ids)
    ordered_ids = get_integration_order(table_ids)

    # Détecter les FK à risque (table dépend d'une autre présente dans le package)
    fk_risks: dict[int, list[int]] = {}
    for tid in table_ids:
        deps_in_pkg = [d for d in PK_RELATIONS.get(tid, []) if d in tables_set]
        if deps_in_pkg:
            fk_risks[tid] = deps_in_pkg

    id_to_sheet = {tid: sheet for sheet, tid in valid}
    summary = []
    pos = 1
    for tid in ordered_ids:
        sheet = id_to_sheet.get(tid, str(tid))
        summary.append({
            "position":         pos,
            "sheet":            sheet,
            "table_id":         tid,
            "label":            metadata.get(sheet, {}).get("label", ""),
            "processing_order": po_map.get(tid, 1),
            "fk_depends_on":    fk_risks.get(tid, []),
            "has_fk_risk":      tid in fk_risks,
        })
        pos += 1

    return summary
