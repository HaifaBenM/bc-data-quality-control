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
import io

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


def build_prerequisites_report(
    anomalies: list[dict], profile_code: str = "", company_id: str = "",
) -> list[dict]:
    """
    Extrait les anomalies PREALABLE_BC_REQUIS et les regroupe par
    (table référencée, valeur manquante) pour produire une checklist de
    données maîtresses à créer côté BC avant import — distincte du fichier
    corrigé (ce ne sont PAS des corrections de valeur).

    Nom de table : interroge BC dynamiquement en priorité (cache Supabase +
    endpoint AL Table Caption API) si profile_code/company_id sont fournis ;
    ne retombe sur le dictionnaire statique master_data_config que si
    l'appel BC échoue ou si les identifiants ne sont pas fournis (usage sans
    contexte BC, ex: tests).
    """
    from app.core.master_data_config import get_table_label

    grouped: dict[tuple, dict] = {}
    for a in anomalies:
        if a.get("Classification") != "PREALABLE_BC_REQUIS":
            continue
        table_id = str(a.get("Table référencée", ""))
        key = (table_id, a.get("Valeur", ""))
        if key not in grouped:
            table_name = None
            if profile_code and company_id and table_id:
                try:
                    from app.db.metadata_db import get_table_caption_cached
                    table_name = get_table_caption_cached(profile_code, company_id, table_id)
                except Exception:
                    table_name = None  # BC injoignable — on retombe sur le statique juste en dessous
            if not table_name:
                table_name = get_table_label(table_id)

            grouped[key] = {
                "Table référencée BC": table_id,
                "Nom table BC":        table_name,
                "Code manquant":       a.get("Valeur", ""),
                "Champs concernés":    set(),
                "Occurrences":         0,
            }
        grouped[key]["Champs concernés"].add(a.get("Champ", ""))
        grouped[key]["Occurrences"] += 1

    report = []
    for row in grouped.values():
        row["Champs concernés"] = ", ".join(sorted(c for c in row["Champs concernés"] if c))
        report.append(row)
    return sorted(report, key=lambda r: -r["Occurrences"])


_PREREQ_COLUMNS = [
    "Table référencée BC", "Nom table BC", "Code manquant",
    "Champs concernés", "Occurrences",
]


def build_prerequisites_excel(prereqs: list[dict]) -> bytes:
    """
    Génère un .xlsx mis en forme (en-tête coloré, colonnes dimensionnées,
    figé sur la 1re ligne) pour la checklist de prérequis BC.

    Remplace le CSV : un CSV en UTF-8 sans BOM s'ouvre en mojibake dans
    Excel FR (accents illisibles, "é" -> "Ã©") tant que l'utilisateur ne
    force pas manuellement l'encodage à l'import. Un .xlsx natif évite le
    problème complètement, et permet la mise en forme demandée.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Prérequis BC"

    ws.append(_PREREQ_COLUMNS)

    header_fill = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    thin        = Side(style="thin", color="D1D5DB")
    border      = Border(left=thin, right=thin, top=thin, bottom=thin)

    for cell in ws[1]:
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = border

    for row in prereqs:
        ws.append([row.get(col, "") for col in _PREREQ_COLUMNS])

    for r in range(2, ws.max_row + 1):
        for c in range(1, len(_PREREQ_COLUMNS) + 1):
            cell = ws.cell(row=r, column=c)
            cell.border    = border
            cell.alignment = Alignment(vertical="center", wrap_text=(c in (3, 4)))
        # Bandes alternées pour la lisibilité
        if r % 2 == 0:
            for c in range(1, len(_PREREQ_COLUMNS) + 1):
                ws.cell(row=r, column=c).fill = PatternFill(
                    start_color="F5F3FF", end_color="F5F3FF", fill_type="solid"
                )

    widths = [18, 26, 34, 34, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 28

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()