"""
Génération du fichier Excel corrigé.

⚠️ PAS TESTÉ CONTRE UN IMPORT BC RÉEL — à valider avant démo.

Approche volontairement différente de pandas/openpyxl.to_excel() : ces
librairies reconstruisent le classeur et perdent les parties XML propres à
BC (xmlMaps.xml, customXml) — c'est la cause déjà identifiée du blocage sur
le test Emplacement (mapping XML invalide sur les fichiers reconstruits).

Ici, on édite uniquement la valeur des cellules concernées directement dans
le XML du classeur (xl/worksheets/sheetN.xml), et on recopie TOUTES les
autres parties du zip xlsx à l'identique, octet pour octet — y compris
xmlMaps.xml et customXml.

Convention de structure confirmée sur les fichiers BC de ce projet :
  ligne 1 = métadonnées package, ligne 2 = vide, ligne 3 = en-têtes,
  ligne 4+ = données. D'où le "+4" déjà utilisé dans validator_axe_a.py /
  validator_axe_b.py pour numéroter les lignes — même convention réutilisée
  ici (le "Ligne" d'une anomalie EST le numéro de ligne Excel réel).
"""
from __future__ import annotations
import io
import re
import zipfile
from xml.etree import ElementTree as ET

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", _NS_MAIN)

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
    """Colonne (nom d'en-tête) -> lettre Excel, lue sur HEADER_ROW."""
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


def apply_corrections(original_bytes: bytes, corrections: list[dict]) -> bytes:
    """
    corrections : [{"sheet": str, "excel_row": int, "column_name": str, "new_value": str}, ...]

    Modifie uniquement les cellules concernées, en les convertissant en
    inline string (t="inlineStr") — ce qui évite de toucher à la table
    sharedStrings.xml partagée par toutes les autres cellules non modifiées.
    Toutes les parties du zip non touchées (dont xmlMaps.xml, customXml/*)
    sont recopiées à l'identique.
    """
    src    = zipfile.ZipFile(io.BytesIO(original_bytes), "r")
    shared = _shared_strings(src)

    by_sheet: dict[str, list[dict]] = {}
    for corr in corrections:
        by_sheet.setdefault(corr["sheet"], []).append(corr)

    modified_xml: dict[str, bytes] = {}

    for sheet_name, corr_list in by_sheet.items():
        sheet_path = _sheet_xml_path(src, sheet_name)
        if not sheet_path or sheet_path not in src.namelist():
            continue

        root       = ET.fromstring(src.read(sheet_path))
        header_map = _build_header_map(root, shared)
        sheet_data = root.find(_q("sheetData"))
        if sheet_data is None:
            continue

        row_map = {row.get("r"): row for row in sheet_data.findall(_q("row"))}

        for corr in corr_list:
            col_letter = header_map.get(corr["column_name"])
            if not col_letter:
                continue  # en-tête introuvable — on ne touche pas au fichier plutôt que de deviner

            excel_row = str(corr["excel_row"])
            cell_ref  = f"{col_letter}{excel_row}"
            row_el    = row_map.get(excel_row)
            if row_el is None:
                continue

            cell_el = next((c for c in row_el.findall(_q("c")) if c.get("r") == cell_ref), None)
            if cell_el is None:
                continue

            for child in list(cell_el):
                cell_el.remove(child)
            cell_el.set("t", "inlineStr")
            is_el = ET.SubElement(cell_el, _q("is"))
            t_el  = ET.SubElement(is_el, _q("t"))
            t_el.text = str(corr["new_value"])

        modified_xml[sheet_path] = ET.tostring(root, xml_declaration=True, encoding="UTF-8")

    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = modified_xml.get(item.filename, src.read(item.filename))
            dst.writestr(item, data)

    src.close()
    return out_buf.getvalue()
