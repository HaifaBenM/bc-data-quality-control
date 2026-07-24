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
import pandas as pd

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


# ── Contrôle croisé GL Account <-> groupes comptables (socle MDD Compta) ────
#
# Confirmé par test réel le 23/07/2026 : importer 92/93/94 après GL Account
# échoue quand même si le compte général référencé par un champ-compte de
# 92/93/94 n'a pas LUI-MÊME ses propres Groupe compta. marché / Groupe
# compta. produit renseignés — erreur BC "Groupe compta. produit doit avoir
# une valeur dans Compte général: N°=<compte>. Il ne peut pas être vide ou
# nul." Ce n'est pas une histoire de table manquante (le compte existe déjà,
# GL Account est intégré) : c'est un champ précis, sur une ligne précise,
# manquant.
#
# Vérification 100% inter-onglets DU MÊME fichier déposé, aucun appel BC :
# le compte et le groupe qui le référence sont dans le même package MDD
# Comptabilité (socle figé confirmé par Rami/Bilel), donc les deux onglets
# sont déjà là au moment du contrôle.

GL_ACCOUNT_REQUIRED_FIELDS = ["Groupe compta. marché", "Groupe compta. produit"]

_ACCOUNT_FIELD_PREFIXES = ("compte", "cpte")
_ACCOUNT_FIELD_EXCLUSIONS = {
    "afficher tous les comptes lors de la consultation",
}


def _is_account_reference_column(col_name: str) -> bool:
    """
    Un champ "champ-compte" pointe vers un compte général (Chart of
    Accounts) — reconnu par son libellé BC standard : commence par
    "Compte" ou "Cpte" (Compte client, Compte frais forfaitaires, Cpte
    arrondi débit...), à l'exclusion des champs qui contiennent le mot
    sans être une référence de compte (ex. la case à cocher "Afficher tous
    les comptes lors de la consultation").

    NON VÉRIFIÉ AU-DELÀ DES ONGLETS 92/93 DU FICHIER RÉEL DE RAMI (22/07) :
    la règle générique tient sur ces deux tables, mais n'a pas été testée
    sur d'autres tables de groupes comptables (FA Posting Group, Bank
    Account Posting Group...) si elles apparaissent un jour dans le socle —
    à revérifier si de nouveaux libellés de champ ne matchent pas ce motif.
    """
    name = str(col_name or "").strip().lower()
    if name in _ACCOUNT_FIELD_EXCLUSIONS:
        return False
    return any(name.startswith(p) for p in _ACCOUNT_FIELD_PREFIXES)


def check_gl_account_prerequisites(parsed_file: dict) -> list[dict]:
    """
    Pour chaque compte général référencé par un champ-compte d'une table de
    groupe comptable (92, 93, 94, ou toute autre table du même type présente
    dans le fichier), vérifie que ce compte a bien ses propres champs
    "Groupe compta. marché" et "Groupe compta. produit" remplis dans
    l'onglet Compte général (table 15) — AVANT de considérer 92/93/94
    intégrables sans erreur BC.

    Ne fait AUCUN appel BC : contrôle purement inter-onglets sur le fichier
    déjà déposé (parse_uploaded_file). S'utilise en amont de l'intégration
    BC de 92/93/94, pas après-coup sur une erreur déjà survenue.

    Retourne une liste de dicts au même format que build_prerequisites_report
    (réutilisable tel quel avec build_prerequisites_excel) :
        {
          "Table référencée BC": "15",
          "Nom table BC": "Compte général",
          "Code manquant": "<N° compte> — <champ vide>",
          "Champs concernés": "<onglet>.<colonne> ; ...",
          "Occurrences": <int>,
        }

    Si l'onglet Compte général (table 15) est absent du fichier déposé (cas
    normal pour un package qui ne contient pas la comptabilité), retourne []
    silencieusement — ce contrôle ne s'applique qu'aux fichiers qui
    contiennent réellement la table 15.
    """
    sheets   = parsed_file.get("sheets", {})
    metadata = parsed_file.get("metadata", {})

    gl_sheet_name = next(
        (name for name, meta in metadata.items() if str(meta.get("table_id", "")) == "15"),
        None,
    )
    if gl_sheet_name is None:
        return []

    gl_df = sheets.get(gl_sheet_name)
    if gl_df is None or gl_df.empty:
        return []

    account_col = next((c for c in gl_df.columns if str(c).strip() == "N°"), None)
    if account_col is None:
        return []

    gl_by_account = gl_df.set_index(gl_df[account_col].astype(str).str.strip())

    missing: dict[tuple, dict] = {}

    for sheet_name, df in sheets.items():
        if sheet_name == gl_sheet_name or df is None or df.empty:
            continue

        account_columns = [c for c in df.columns if _is_account_reference_column(c)]
        if not account_columns:
            continue

        for col in account_columns:
            for raw_value in df[col].dropna():
                acc_no = str(raw_value).strip()
                if not acc_no or acc_no not in gl_by_account.index:
                    continue  # compte inexistant : déjà signalé par ailleurs (Axe B), pas ce contrôle

                gl_row = gl_by_account.loc[acc_no]
                if hasattr(gl_row, "ndim") and gl_row.ndim > 1:
                    gl_row = gl_row.iloc[0]  # N° dupliqué dans le fichier — on ne plante pas, 1re occurrence

                for required_field in GL_ACCOUNT_REQUIRED_FIELDS:
                    # ATTENTION : parse_uploaded_file() fait df.dropna(axis=1,
                    # how="all") — une colonne 100% vide sur TOUS les comptes
                    # du fichier disparaît purement et simplement de gl_df.
                    # Donc "colonne absente" ne veut PAS dire "rien à
                    # vérifier" : ça veut dire "vide pour tous les comptes",
                    # exactement le cas confirmé sur le fichier réel de Rami
                    # le 23/07 (aucun compte n'a Groupe compta. marché/
                    # produit rempli). Traiter comme vide, pas comme absent.
                    if required_field in gl_df.columns:
                        _val = gl_row.get(required_field, "")
                        # BUG CORRIGÉ (24/07) : un NaN pandas (case vide dans
                        # le fichier Excel) est "truthy" en Python — `nan or
                        # ""` vaut nan, pas "". Sans pd.isna() ici, un champ
                        # réellement vide comme celui du compte 40110001
                        # passait à tort pour "rempli". Confirmé en testant
                        # sur le fichier réel de Rami du 24/07 (0 anomalie
                        # remontée alors que Compte fournisseur ETRANGER
                        # avait Groupe compta. marché/produit vides).
                        if not pd.isna(_val) and str(_val).strip():
                            continue  # rempli, rien à signaler

                    key = (acc_no, required_field)
                    if key not in missing:
                        missing[key] = {
                            "Table référencée BC": "15",
                            "Nom table BC": "Compte général",
                            "Code manquant": f"{acc_no} — {required_field} vide",
                            "Champs concernés": set(),
                            "Occurrences": 0,
                        }
                    missing[key]["Champs concernés"].add(f"{sheet_name}.{col}")
                    missing[key]["Occurrences"] += 1

    report = []
    for row in missing.values():
        row["Champs concernés"] = ", ".join(sorted(row["Champs concernés"]))
        report.append(row)
    return sorted(report, key=lambda r: -r["Occurrences"])


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