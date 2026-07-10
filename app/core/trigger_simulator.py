"""
Trigger Simulator — mapping empirique OnInsert / OnValidate.

Ce module reproduit le comportement des triggers AL BC sur les tables connues,
tel que confirmé par les tests empiriques (breakOnError sur BC Online).

IMPORTANT : ce mapping est INCOMPLET par nature.
  - OnValidate est du code AL propriétaire Microsoft, non exposé par API
  - Le comportement varie selon la version BC et les extensions installées
  - Seules les tables testées empiriquement sont couvertes

Quand skip_triggers = FALSE pour une table :
  - BC appelle InsertWithValidation/ModifyWithValidation
  - Ces fonctions déclenchent OnInsert/OnModify
  - OnInsert peut appeler VALIDATE() sur certains champs
  - VALIDATE() déclenche OnValidate du champ

Quand skip_triggers = TRUE :
  - BC appelle Insert/Modify direct → AUCUN trigger → ce module ne s'exécute pas

Source des mappings : tests empiriques du 2025/2026
  (voir Resume_Conclusion_Integration_BC.docx)
"""
from __future__ import annotations
from dataclasses import dataclass, field


# ── Règles de validation OnInsert par table ───────────────────────────────────
# {table_id: [{champ, ref_table_id, description, severity}]}
# Ces champs sont validés par BC lors du INSERT (si skip_triggers=False)

ONINSERT_RULES: dict[int, list[dict]] = {

    # Table 18 — Customer
    # Confirmé : InsertWithValidation → OnInsert → valide Customer Posting Group
    18: [
        {
            "field":         "Groupe compta. client",
            "ref_table_id":  91,
            "description":   "Groupe compta. client obligatoire et doit exister",
            "severity":      "Majeure",
        },
        {
            "field":         "Groupe compta. marché",
            "ref_table_id":  15,
            "description":   "Groupe compta. marché (Gen. Bus. Posting Group) doit exister",
            "severity":      "Majeure",
        },
    ],

    # Table 23 — Vendor
    # Confirmé par analogie avec Customer (même pattern BC)
    23: [
        {
            "field":         "Groupe compta. fourn.",
            "ref_table_id":  92,
            "description":   "Groupe compta. fournisseur obligatoire et doit exister",
            "severity":      "Majeure",
        },
        {
            "field":         "Groupe compta. marché",
            "ref_table_id":  15,
            "description":   "Groupe compta. marché (Gen. Bus. Posting Group) doit exister",
            "severity":      "Majeure",
        },
    ],

    # Table 27 — Item
    # OnInsert valide les groupes comptables si non vides
    27: [
        {
            "field":         "Groupe compta. stock",
            "ref_table_id":  94,
            "description":   "Groupe compta. stock doit exister si renseigné",
            "severity":      "Majeure",
        },
        {
            "field":         "Groupe compta. produit",
            "ref_table_id":  15,
            "description":   "Groupe compta. produit (Gen. Prod. Posting Group) doit exister",
            "severity":      "Mineure",
        },
    ],

    # Table 15 — G/L Account
    # OnInsert minimal — le compte doit avoir un type valide
    15: [],

    # Tables sans OnInsert significatif (Setup / Reference data)
    3:   [],   # Payment Terms
    4:   [],   # Currency
    9:   [],   # Country/Region
    10:  [],   # Shipment Method
    13:  [],   # Salesperson
    14:  [],   # Location
    204: [],   # Unit of Measure
    289: [],   # Payment Method
}


# ── Résultat d'une simulation trigger ─────────────────────────────────────────

@dataclass
class TriggerAnomaly:
    table_id:     int
    sheet_name:   str
    row_number:   int
    field_name:   str
    value:        str
    ref_table_id: int
    message:      str
    severity:     str = "Majeure"
    trigger_type: str = "OnInsert"   # OnInsert | OnValidate


# ── Simulateur ────────────────────────────────────────────────────────────────

class TriggerSimulator:
    """
    Simule les triggers BC pour les tables connues.

    Utilisation dans le pipeline :
      - Appelé uniquement si execution_plan.skip_triggers_for(table_id) == False
      - Complète l'Axe B pour les champs validés par OnInsert (pas par Validate Field)
    """

    def __init__(self, simulation_context, metadata_loader) -> None:
        self.context  = simulation_context
        self.metadata = metadata_loader

    def simulate_table(
        self,
        table_id:    int,
        sheet_name:  str,
        df,
        bc_cache_fn,
    ) -> list[TriggerAnomaly]:
        """
        Simule les triggers pour toutes les lignes d'une table.

        Args:
            table_id    : ID de la table BC
            sheet_name  : nom de l'onglet Excel
            df          : DataFrame de la table
            bc_cache_fn : callable(ref_table_id) → set[str] des valeurs BC en cache

        Returns:
            Liste des anomalies détectées par les triggers
        """
        rules = ONINSERT_RULES.get(table_id)
        if rules is None:
            # Table inconnue → avertir mais ne pas bloquer
            return []
        if not rules:
            # Table connue mais sans règle OnInsert
            return []
        if df is None or df.empty:
            return []

        anomalies: list[TriggerAnomaly] = []
        headers = list(df.columns)

        for row_idx, row in df.iterrows():
            row_num = int(row_idx) + 4  # +4 car données commencent ligne 4

            for rule in rules:
                fname        = rule["field"]
                ref_table_id = rule["ref_table_id"]

                if fname not in headers:
                    continue

                value = str(row.get(fname, "") or "").strip()
                if not value or value.lower() in ("nan", "none", ""):
                    # Champ vide → autre anomalie (Axe A) ou optionnel
                    continue

                # Vérifier contre BC cache + simulation context
                bc_vals = bc_cache_fn(ref_table_id)
                if not self.context.is_valid_reference(ref_table_id, value, bc_vals):
                    if bc_vals or self.context.has_table(ref_table_id):
                        # On a des données de référence → erreur certaine
                        anomalies.append(TriggerAnomaly(
                            table_id     = table_id,
                            sheet_name   = sheet_name,
                            row_number   = row_num,
                            field_name   = fname,
                            value        = value,
                            ref_table_id = ref_table_id,
                            message      = (
                                f"[OnInsert] '{fname}' = '{value}' "
                                f"introuvable. {rule['description']}"
                            ),
                            severity     = rule["severity"],
                            trigger_type = "OnInsert",
                        ))
                    # Si pas de données de référence : signaler comme INFO
                    # (sera géré par l'Axe B existant)

        return anomalies

    def is_table_known(self, table_id: int) -> bool:
        """True si ce module a des règles pour cette table."""
        return table_id in ONINSERT_RULES

    def get_coverage_note(self, table_id: int) -> str | None:
        """
        Retourne une note si la table a des triggers mais n'est pas couverte.
        Utilisé pour l'affichage dans l'UI (section INFO).
        """
        if table_id not in ONINSERT_RULES:
            return (
                f"Table {table_id} : comportement OnInsert non documenté "
                "— triggers non simulés par l'outil."
            )
        return None
