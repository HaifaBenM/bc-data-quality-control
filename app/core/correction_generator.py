"""
Génération du fichier Excel corrigé.

⚠️ Toujours pas testé contre un import BC réel — à valider avant démo.

Historique : une première version éditait les cellules via un parse +
ET.tostring() complet de la feuille modifiée. Bug confirmé le 17/07/2026 :
xml.etree.ElementTree ne préserve pas fidèlement les préfixes de namespace
non explicitement enregistrés (notamment x14ac: sur les attributs
<row ... x14ac:dyDescent="0.25">, quasi systématiques dans les fichiers
Excel réels). En renommant ces préfixes à la sérialisation, Excel considère
la feuille corrompue et la vide au moment de la réparation automatique à
l'ouverture — exactement le symptôme observé : l'onglet modifié se
retrouvait totalement vide après génération, alors que les autres onglets
(non touchés, recopiés tels quels) restaient intacts.

Fix : plus aucun aller-retour de sérialisation sur la feuille entière. Le
XML est édité en texte brut, en ne remplaçant que l'exacte sous-chaîne
`<c r="...">...</c>` de chaque cellule concernée. Tout le reste du XML
(déclarations de namespace, attributs x14ac/mc/xr, mise en forme, lignes
non modifiées) reste strictement identique, octet pour octet.

ElementTree n'est utilisé qu'en LECTURE SEULE (pour repérer la ligne
d'en-têtes et mapper nom de colonne -> lettre Excel) — jamais réinjecté.
"""
from __future__ import annotations
import io
import re
import zipfile
from xml.etree import ElementTree as ET

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

HEADER_ROW = 3  # confirmé : ligne des en-têtes de colonnes


def _q(tag: str) -> str:
    return f"{{{_NS_MAIN}}}{tag}"


def _sheet_xml_path(zf: zipfile.ZipFile, sheet_name: str) -> str | None:
    """Résout xl/worksheets/sheetN.xml à partir du nom d'onglet, via workbook.xml + ses rels."""
    wb_root   = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

    rel_map = {rel.get("Id"): rel.get("Target") for rel in rels_root}

    sheets_el = wb_root.find(_q("sheets"))
    if sheets_el is None:
        return None
    for sheet in sheets_el:
        if sheet.get("name") == sheet_name:
            r_id   = sheet.get(f"{{{_NS_REL}}}id")
            target = rel_map.get(r_id)
            if target:
                target = target.lstrip("/")
                return target if target.startswith("xl/") else f"xl/{target}"
    return None


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall(_q("si")):
        out.append("".join(t.text or "" for t in si.iter(_q("t"))))
    return out


def _cell_text(c, shared_strings: list[str]) -> str:
    t    = c.get("t", "")
    v_el = c.find(_q("v"))
    if t == "s" and v_el is not None and v_el.text is not None:
        idx = int(v_el.text)
        return shared_strings[idx] if idx < len(shared_strings) else ""
    if v_el is not None:
        return v_el.text or ""
    is_el = c.find(_q("is"))
    if is_el is not None:
        return "".join(t.text or "" for t in is_el.iter(_q("t")))
    return ""


def _build_header_map(root, shared_strings: list[str]) -> dict[str, str]:
    """Colonne (nom d'en-tête) -> lettre Excel, lue sur HEADER_ROW. Lecture seule."""
    header_map: dict[str, str] = {}
    sheet_data = root.find(_q("sheetData"))
    if sheet_data is None:
        return header_map
    for row in sheet_data.findall(_q("row")):
        if row.get("r") != str(HEADER_ROW):
            continue
        for c in row.findall(_q("c")):
            ref = c.get("r", "")
            m = re.match(r"([A-Z]+)", ref)
            if not m:
                continue
            val = _cell_text(c, shared_strings).strip()
            if val:
                header_map[val] = m.group(1)
        break
    return header_map


def _xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _extract_attr(tag_text: str, attr: str) -> str | None:
    m = re.search(rf'\b{attr}="([^"]*)"', tag_text)
    return m.group(1) if m else None


def _find_row_span(xml_text: str, row_number: int) -> tuple[int, int] | None:
    """(start, end) de la balise <row r="N" ...>...</row> (ou auto-fermante)
    dans xml_text.

    CORRIGÉ (28/07/2026) : le fichier export BC réel de la table 15 (GL
    Account) utilise un préfixe de namespace explicite sur ses éléments
    (<x:row>, <x:c>...), contrairement aux fichiers testés le 17/07 qui
    utilisaient le namespace par défaut sans préfixe (<row>, <c>). La regex
    cherchait littéralement "<row" et ne matchait jamais sur ce fichier —
    échec silencieux confirmé (apply_corrections rendait un fichier
    identique à l'original, aucune erreur levée). Fix : préfixe optionnel
    (\\w+:)? accepté devant row/c/rows dans toutes les regex de ce module.
    """
    m = re.search(rf'<(?:\w+:)?row\b[^>]*\br="{row_number}"[^>]*>', xml_text)
    if m and not m.group(0).endswith("/>"):
        m_close = re.search(r"</(?:\w+:)?row>", xml_text[m.end():])
        if not m_close:
            return None
        return (m.start(), m.end() + m_close.end())
    m_self = re.search(rf'<(?:\w+:)?row\b[^>]*\br="{row_number}"[^>]*/>', xml_text)
    if m_self:
        return (m_self.start(), m_self.end())
    return None


def _replace_cell_in_row(row_xml: str, cell_ref: str, new_value: str) -> str:
    """Remplace la cellule cell_ref dans le fragment row_xml par une inline
    string, en gardant son style (s=). Préfixe de namespace optionnel
    (voir _find_row_span) — CORRIGÉ (28/07/2026, 2e passe) : la cellule de
    remplacement doit reprendre EXACTEMENT le même préfixe que la cellule
    d'origine (ex. "x:c", "x:is", "x:t"), pas un tag sans préfixe. Ce
    fichier ne déclare xmlns "main" que via xmlns:x (pas de xmlns= par
    défaut) — un <c> sans préfixe tomberait dans le namespace nul, donc
    hors schéma, et provoquerait la même corruption/vidage de feuille que
    le bug ElementTree du 17/07. Le préfixe est extrait de la balise
    trouvée et réutilisé tel quel sur c/is/t.
    """
    esc_ref = re.escape(cell_ref)

    m = re.search(rf'<((?:\w+:)?)c\b[^>]*\br="{esc_ref}"[^>]*>.*?</(?:\w+:)?c>', row_xml, re.DOTALL)
    if not m:
        m = re.search(rf'<((?:\w+:)?)c\b[^>]*\br="{esc_ref}"[^>]*/>', row_xml)
    if not m:
        return row_xml  # cellule introuvable — on laisse la ligne intacte plutôt que deviner

    prefix = m.group(1)  # ex. "x:" ou "" — repris tel quel, jamais deviné
    style  = _extract_attr(m.group(0), "s")
    s_attr = f' s="{style}"' if style else ""
    new_cell = (
        f'<{prefix}c r="{cell_ref}"{s_attr} t="inlineStr">'
        f'<{prefix}is><{prefix}t xml:space="preserve">{_xml_escape(new_value)}</{prefix}t></{prefix}is>'
        f'</{prefix}c>'
    )
    return row_xml[:m.start()] + new_cell + row_xml[m.end():]


def apply_corrections(original_bytes: bytes, corrections: list[dict]) -> bytes:
    """
    corrections : [{"sheet": str, "excel_row": int, "column_name": str, "new_value": str}, ...]

    Édition en texte brut : seule la sous-chaîne exacte de chaque cellule
    concernée est remplacée. Tout le reste du XML de la feuille (namespaces,
    mise en forme, lignes non touchées) reste identique, octet pour octet.
    Les autres parties du zip (dont xmlMaps.xml, customXml/*) sont recopiées
    à l'identique.
    """
    src    = zipfile.ZipFile(io.BytesIO(original_bytes), "r")
    shared = _shared_strings(src)

    by_sheet: dict[str, list[dict]] = {}
    for corr in corrections:
        by_sheet.setdefault(corr["sheet"], []).append(corr)

    modified_bytes: dict[str, bytes] = {}

    for sheet_name, corr_list in by_sheet.items():
        sheet_path = _sheet_xml_path(src, sheet_name)
        if not sheet_path or sheet_path not in src.namelist():
            continue

        raw_bytes = src.read(sheet_path)
        # Lecture seule (jamais réinjecté) : sert uniquement à mapper nom de
        # colonne -> lettre Excel.
        header_map = _build_header_map(ET.fromstring(raw_bytes), shared)

        xml_text = raw_bytes.decode("utf-8")

        for corr in corr_list:
            col_letter = header_map.get(corr["column_name"])
            if not col_letter:
                continue

            cell_ref = f"{col_letter}{corr['excel_row']}"
            span = _find_row_span(xml_text, corr["excel_row"])
            if not span:
                continue

            start, end  = span
            row_xml     = xml_text[start:end]
            new_row_xml = _replace_cell_in_row(row_xml, cell_ref, str(corr["new_value"]))
            xml_text    = xml_text[:start] + new_row_xml + xml_text[end:]

        modified_bytes[sheet_path] = xml_text.encode("utf-8")

    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            # AJOUTÉ (27/08/2026, 2e passe) — nouvelle piste testée après
            # que le diagnostic ait confirmé qu'aucune entrée n'avait de
            # méthode de compression non standard (le fix précédent était
            # donc déjà correct, mais insuffisant) : ce fichier BC contient
            # des entrées "dossier" explicites (_rels/, xl/, taille 0,
            # nom se terminant par "/") — atypique pour un xlsx (Excel/
            # openpyxl n'en génèrent jamais), tolérées par Python/Excel
            # mais peut-être pas par le lecteur strict de BC. Ignorées à
            # la reconstruction — un lecteur OOXML retrouve la structure
            # de dossiers via les chemins des fichiers eux-mêmes, ces
            # entrées ne sont jamais indispensables.
            if item.filename.endswith("/") and item.file_size == 0:
                continue
            data = modified_bytes.get(item.filename, src.read(item.filename))
            # RÉVISÉ (27/08/2026) — bug réel rencontré : passer l'objet
            # ZipInfo original tel quel à writestr() lui fait ignorer le
            # mode ZIP_DEFLATED du zip de destination et réutiliser la
            # méthode de compression D'ORIGINE de chaque entrée — si le
            # fichier BC source en a une non standard sur ne serait-ce
            # qu'une entrée, ça produit une archive que BC rejette
            # ("compressed using an unsupported compression method") même
            # si Excel/openpyxl l'ouvrent sans se plaindre. Forcé en
            # DEFLATE standard sur CHAQUE entrée, sans exception.
            item.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(item, data)

    src.close()
    return out_buf.getvalue()


_ID_COLUMN_PREFIX = "ID "  # colonnes de résolution interne BC (SystemId) — non portables entre sociétés


def clear_id_reference_columns(
    excel_bytes: bytes,
    guid_column_names: dict[str, set[str]] | None = None,
) -> bytes:
    """
    Vide les colonnes de type Guid (SystemId interne BC : ID unité, ID groupe
    compta. stock, ID groupe compta. produit, ID catégorie article, etc.) sur
    toutes les feuilles de données.

    AJOUTÉ (18/08/2026) : ces colonnes contiennent le SystemId de l'enregistrement
    résolu au moment de l'export BC d'origine. Un SystemId est unique à sa
    société/base — il ne correspond à AUCUN enregistrement dans une société
    différente, même si le Code associé existe avec la même valeur. BC rejette
    donc systématiquement l'import (« Le champ ID X... contient une valeur qui
    ne peut pas être trouvée ») dès que le fichier a été exporté depuis une
    société différente de la cible, même quand les données Code sont
    correctes. Vider ces colonnes laisse BC résoudre uniquement via le champ
    Code (résolution RapidStart standard), qui lui est portable entre sociétés.

    RÉVISÉ (18/08/2026, 2e passe) : critère fiable = le TYPE AL du champ
    (Guid), pas son nom — un champ Guid avec TableRelation = Table.SystemId
    est un pattern standard Microsoft, aussi bien sur un champ BC natif que
    sur un champ d'extension (Talan ou client), puisque BC expose fieldType
    de la même façon pour les deux. `guid_column_names` (optionnel) :
    {sheet_name: {noms de colonnes Guid}}, calculé côté appelant depuis
    execution_plan.get_field_defs_for_table() (voir 2_Sessions_Integration.py).
    Si non fourni (plan indisponible), repli sur l'ancien préfixe "ID " —
    moins précis (risque de collision avec un futur champ métier nommé "ID
    ..." ou de rater un champ Guid d'extension nommé autrement) mais mieux
    que rien.

    Même technique d'édition texte brut que apply_corrections (voir docstring
    du module) : seule la sous-chaîne exacte de chaque cellule ciblée est
    remplacée, rien d'autre n'est reparsé/réinjecté. Pas encore testé contre
    un import BC réel — à valider comme apply_corrections avant démo.
    """
    src    = zipfile.ZipFile(io.BytesIO(excel_bytes), "r")
    shared = _shared_strings(src)

    modified_bytes: dict[str, bytes] = {}

    wb_root   = ET.fromstring(src.read("xl/workbook.xml"))
    sheets_el = wb_root.find(_q("sheets"))
    sheet_names = [s.get("name") for s in sheets_el] if sheets_el is not None else []

    for sheet_name in sheet_names:
        sheet_path = _sheet_xml_path(src, sheet_name)
        if not sheet_path or sheet_path not in src.namelist():
            continue

        raw_bytes  = src.read(sheet_path)
        header_map = _build_header_map(ET.fromstring(raw_bytes), shared)

        _guid_names = guid_column_names.get(sheet_name) if guid_column_names else None
        if _guid_names is not None:
            id_cols = {name: col for name, col in header_map.items() if name in _guid_names}
        else:
            id_cols = {name: col for name, col in header_map.items() if name.startswith(_ID_COLUMN_PREFIX)}
        if not id_cols:
            continue

        xml_text = raw_bytes.decode("utf-8")

        # Toutes les lignes de données (row > HEADER_ROW), pas seulement les
        # lignes corrigées — ici on vide sur TOUT le fichier.
        row_numbers = sorted({
            int(m.group(1))
            for m in re.finditer(r'<(?:\w+:)?row\b[^>]*\br="(\d+)"', xml_text)
            if int(m.group(1)) > HEADER_ROW
        })

        for row_num in row_numbers:
            span = _find_row_span(xml_text, row_num)
            if not span:
                continue
            start, end = span
            row_xml = xml_text[start:end]
            for col_letter in id_cols.values():
                cell_ref = f"{col_letter}{row_num}"
                row_xml = _replace_cell_in_row(row_xml, cell_ref, "")
            xml_text = xml_text[:start] + row_xml + xml_text[end:]

        modified_bytes[sheet_path] = xml_text.encode("utf-8")

    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            # AJOUTÉ (27/08/2026, 2e passe) — nouvelle piste testée après
            # que le diagnostic ait confirmé qu'aucune entrée n'avait de
            # méthode de compression non standard (le fix précédent était
            # donc déjà correct, mais insuffisant) : ce fichier BC contient
            # des entrées "dossier" explicites (_rels/, xl/, taille 0,
            # nom se terminant par "/") — atypique pour un xlsx (Excel/
            # openpyxl n'en génèrent jamais), tolérées par Python/Excel
            # mais peut-être pas par le lecteur strict de BC. Ignorées à
            # la reconstruction — un lecteur OOXML retrouve la structure
            # de dossiers via les chemins des fichiers eux-mêmes, ces
            # entrées ne sont jamais indispensables.
            if item.filename.endswith("/") and item.file_size == 0:
                continue
            data = modified_bytes.get(item.filename, src.read(item.filename))
            # RÉVISÉ (27/08/2026) — bug réel rencontré : passer l'objet
            # ZipInfo original tel quel à writestr() lui fait ignorer le
            # mode ZIP_DEFLATED du zip de destination et réutiliser la
            # méthode de compression D'ORIGINE de chaque entrée — si le
            # fichier BC source en a une non standard sur ne serait-ce
            # qu'une entrée, ça produit une archive que BC rejette
            # ("compressed using an unsupported compression method") même
            # si Excel/openpyxl l'ouvrent sans se plaindre. Forcé en
            # DEFLATE standard sur CHAQUE entrée, sans exception.
            item.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(item, data)

    src.close()
    return out_buf.getvalue()

def sanitize_zip_for_bc(excel_bytes: bytes) -> bytes:
    """
    AJOUTÉ (27/08/2026) — demande Rami : "🔴 BC a rejeté l'import — unsupported
    compression method" pouvait encore se produire sur le fichier ORIGINAL
    (jamais passé par apply_corrections/clear_id_reference_columns, qui
    contiennent déjà ce nettoyage — ex. "Comparer avec BC" à l'Étape 3,
    envoie original_bytes directement). Extrait le même nettoyage en
    fonction autonome, à appeler sur N'IMPORTE QUEL fichier juste avant un
    envoi à BC, peu importe s'il a déjà été retouché ou non :
    - retire les entrées "dossier" explicites (_rels/, xl/... taille 0,
      nom finissant par "/") — atypiques pour un xlsx, tolérées par
      Excel/Python mais pas par le lecteur strict de BC.
    - force ZIP_DEFLATED sur chaque entrée (passer l'objet ZipInfo original
      tel quel à writestr() lui fait réutiliser sa méthode de compression
      d'origine, potentiellement non standard, au lieu du mode du zip de
      destination).
    Ne modifie aucun contenu de fichier (contrairement à apply_corrections/
    clear_id_reference_columns) — recopie tout tel quel, juste nettoyé au
    niveau de l'archive zip elle-même.
    """
    src = zipfile.ZipFile(io.BytesIO(excel_bytes), "r")
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename.endswith("/") and item.file_size == 0:
                continue
            data = src.read(item.filename)
            item.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(item, data)
    src.close()
    return out_buf.getvalue()