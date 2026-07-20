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
    """(start, end) de la balise <row r="N" ...>...</row> (ou auto-fermante) dans xml_text."""
    m = re.search(rf'<row\b[^>]*\br="{row_number}"[^>]*>', xml_text)
    if m and not m.group(0).endswith("/>"):
        m_close = re.search(r"</row>", xml_text[m.end():])
        if not m_close:
            return None
        return (m.start(), m.end() + m_close.end())
    m_self = re.search(rf'<row\b[^>]*\br="{row_number}"[^>]*/>', xml_text)
    if m_self:
        return (m_self.start(), m_self.end())
    return None


def _replace_cell_in_row(row_xml: str, cell_ref: str, new_value: str) -> str:
    """Remplace la cellule cell_ref dans le fragment row_xml par une inline string, en gardant son style (s=)."""
    esc_ref = re.escape(cell_ref)

    m = re.search(rf'<c\b[^>]*\br="{esc_ref}"[^>]*>.*?</c>', row_xml, re.DOTALL)
    if not m:
        m = re.search(rf'<c\b[^>]*\br="{esc_ref}"[^>]*/>', row_xml)
    if not m:
        return row_xml  # cellule introuvable — on laisse la ligne intacte plutôt que deviner

    style  = _extract_attr(m.group(0), "s")
    s_attr = f' s="{style}"' if style else ""
    new_cell = f'<c r="{cell_ref}"{s_attr} t="inlineStr"><is><t xml:space="preserve">{_xml_escape(new_value)}</t></is></c>'
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
            data = modified_bytes.get(item.filename, src.read(item.filename))
            dst.writestr(item, data)

    src.close()
    return out_buf.getvalue()