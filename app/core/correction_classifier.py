"""
Classification des anomalies "Code de référence invalide" (et "Souches de
n° non résolvable") en deux catégories :

- VALEUR_CORRIGIBLE   : le code saisi est proche d'un code qui existe déjà
                        dans la table référencée BC (faute de frappe probable,
                        ou mauvais code choisi) -> corrigible dans le fichier.
- PREALABLE_BC_REQUIS : aucun code valide ne ressemble à la valeur saisie ->
                        le code n'existe tout simplement pas côté BC. Aucune
                        valeur saisie dans le fichier ne sera valide tant que
                        cette donnée maîtresse n'est pas créée dans BC.

Distinction basée sur une comparaison floue (difflib, stdlib — aucune
dépendance supplémentaire) contre l'ensemble des codes valides déjà récupéré
par Axe B (get_reference_values_by_table_id) : aucun appel BC additionnel.
"""
from __future__ import annotations
import difflib

# Score de similarité minimal pour considérer un code existant comme "faute
# de frappe probable" plutôt que "code inexistant". Pas encore calibré sur
# un jeu de cas réel BC — à ajuster si trop de faux positifs/négatifs
# apparaissent en pratique (valeur de départ raisonnable, pas une vérité
# mesurée).
FUZZY_MATCH_THRESHOLD = 0.72
MAX_SUGGESTIONS = 3


def suggest_close_codes(
    value: str, valid_codes: set[str], limit: int = MAX_SUGGESTIONS
) -> list[tuple[str, float]]:
    """Codes valides les plus proches de `value`, triés par score décroissant."""
    if not value or not valid_codes:
        return []
    scored = []
    for code in valid_codes:
        if not code:
            continue
        ratio = difflib.SequenceMatcher(None, value.lower(), str(code).lower()).ratio()
        if ratio >= FUZZY_MATCH_THRESHOLD:
            scored.append((code, ratio))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def classify_reference_anomaly(value: str, valid_codes: set[str]) -> dict:
    """
    Classifie une anomalie "Code de référence invalide".

    Retourne :
      {
        "classification": "VALEUR_CORRIGIBLE" | "PREALABLE_BC_REQUIS",
        "suggestions": [(code, score), ...],  # non vide seulement si VALEUR_CORRIGIBLE
      }
    """
    suggestions = suggest_close_codes(value, valid_codes)
    if suggestions:
        return {"classification": "VALEUR_CORRIGIBLE", "suggestions": suggestions}
    return {"classification": "PREALABLE_BC_REQUIS", "suggestions": []}


def build_prerequisites_report(anomalies: list[dict]) -> list[dict]:
    """
    Extrait les anomalies PREALABLE_BC_REQUIS et les regroupe par
    (table référencée, valeur manquante) pour produire une checklist de
    données maîtresses à créer côté BC avant import — distincte du fichier
    corrigé (ce ne sont PAS des corrections de valeur).
    """
    grouped: dict[tuple, dict] = {}
    for a in anomalies:
        if a.get("Classification") != "PREALABLE_BC_REQUIS":
            continue
        key = (a.get("Table référencée", ""), a.get("Valeur", ""))
        if key not in grouped:
            grouped[key] = {
                "Table référencée BC":  a.get("Table référencée", ""),
                "Code manquant":        a.get("Valeur", ""),
                "Champs concernés":     set(),
                "Occurrences":          0,
            }
        grouped[key]["Champs concernés"].add(a.get("Champ", ""))
        grouped[key]["Occurrences"] += 1

    report = []
    for row in grouped.values():
        row["Champs concernés"] = ", ".join(sorted(c for c in row["Champs concernés"] if c))
        report.append(row)
    return sorted(report, key=lambda r: -r["Occurrences"])
