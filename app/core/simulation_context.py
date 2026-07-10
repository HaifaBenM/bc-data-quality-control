"""
Simulation Context — état progressif en mémoire.

Reproduit ce que BC fait en écrivant directement en base réelle :
après que Customer a été importé (table 18), les Customer No. de ce fichier
sont disponibles comme références valides pour Ship-to Address (table 222).

Sans ce contexte, l'Axe B ne peut vérifier les références intra-fichier
qu'en chargeant toutes les tables d'un coup (ce qui ignore l'ordre BC).
Avec ce contexte, la validation se construit table par table exactement
comme BC le ferait.

Structure interne :
  {table_id: set(primary_key_values)}

Utilisation dans le pipeline :
  1. Axe B lit  : context.get_values(ref_table_id)  → valeurs déjà validées
  2. Axe B écrit : context.add(table_id, pk_values) → après validation d'une table
"""
from __future__ import annotations


class SimulationContext:
    """
    Contexte de simulation en mémoire — une instance par session de validation.

    Combiné avec le BC cache (données existantes dans la société),
    il permet à l'Axe B de vérifier :
        BC_cache(ref_table_id) ∪ simulation_context(ref_table_id)

    C'est exactement ce que fait ValidateFieldRelationAgainstCompanyDataAndPackage :
    vérifier que la valeur existe dans la société BC OU dans le reste du package.
    """

    def __init__(self) -> None:
        # {table_id (int): set of pk values (str)}
        self._data: dict[int, set[str]] = {}

    def add(self, table_id: int, pk_values: list[str]) -> None:
        """
        Ajoute les clés primaires d'une table après sa validation.
        Appelé après chaque table traitée sans erreur bloquante Axe A.

        Args:
            table_id  : ID de la table BC (ex: 18 pour Customer)
            pk_values : liste des valeurs PK de cette table dans le fichier
        """
        if table_id not in self._data:
            self._data[table_id] = set()
        self._data[table_id].update(str(v) for v in pk_values if v is not None)

    def get_values(self, table_id: int) -> set[str]:
        """
        Retourne les valeurs PK d'une table déjà validées dans ce fichier.
        Retourne un set vide si la table n'a pas encore été traitée.

        Args:
            table_id : ID de la table à interroger

        Returns:
            set des valeurs PK disponibles comme références intra-fichier
        """
        return self._data.get(table_id, set())

    def has_table(self, table_id: int) -> bool:
        """True si cette table a déjà été traitée et ajoutée au contexte."""
        return table_id in self._data and bool(self._data[table_id])

    def is_valid_reference(
        self,
        ref_table_id: int,
        value:        str,
        bc_cache:     set[str],
    ) -> bool:
        """
        Vérifie si une valeur est valide comme référence.
        Reproduit ValidateFieldRelationAgainstCompanyDataAndPackage :
            valeur ∈ BC_cache OU valeur ∈ simulation_context

        Args:
            ref_table_id : table référencée (ex: 18 pour Customer)
            value        : valeur à vérifier (ex: "CLI-001")
            bc_cache     : valeurs existantes dans la société BC

        Returns:
            True si la valeur est valide (dans BC ou dans le fichier courant)
        """
        v = str(value).strip()
        if v in bc_cache:
            return True
        return v in self._data.get(ref_table_id, set())

    def summary(self) -> dict[int, int]:
        """Résumé : {table_id: nb_valeurs} — utile pour debug."""
        return {tid: len(vals) for tid, vals in self._data.items()}

    def reset(self) -> None:
        """Remet le contexte à zéro (nouvelle session)."""
        self._data.clear()


def extract_pk_values(
    df,
    table_id: int,
    parse_result: dict,
) -> list[str]:
    """
    Extrait les valeurs de clé primaire d'un DataFrame de table BC.

    La clé primaire est la première colonne du fichier Excel BC
    (colonne A, après les métadonnées ligne 1 et headers ligne 3).
    C'est une approximation correcte pour les tables standards BC
    où la PK est toujours en première position dans le Config Package.

    Pour les tables à clé composite (ex: Ship-to Address : Customer No + Code),
    on prend la première colonne (Customer No.) car c'est la FK vers Customer.

    Args:
        df           : DataFrame de la table (rows = données, cols = champs)
        table_id     : ID de la table BC
        parse_result : résultat du file_parser (pour accès aux métadonnées)

    Returns:
        Liste des valeurs PK non-nulles
    """
    if df is None or df.empty:
        return []

    try:
        first_col = df.iloc[:, 0]
        return [
            str(v).strip()
            for v in first_col
            if v is not None and str(v).strip() not in ("", "nan", "None")
        ]
    except Exception:
        return []
