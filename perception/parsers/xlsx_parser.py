"""Parseur XLSX (balance comptable, exports) - T-M05-3.

Meme contrat que le parseur CSV (T-M05-2) : un profil versionne
(``source-profile/*``) decrit la feuille a lire (``sheet``) et le mapping
colonnes -> champs ; sans profil, **anomalie « profil manquant », jamais
d'interpretation devinee**. Si la feuille declaree par le profil n'existe
pas dans le classeur : anomalie egalement (« feuille introuvable »).

Implementation 100 % bibliotheque standard : un .xlsx est une archive ZIP
de XML (ECMA-376) - ``zipfile`` + ``xml.etree`` suffisent pour lire les
cellules (chaines partagees, chaines inline, nombres). Aucun moteur de
formules : seules les valeurs stockees sont lues, jamais recalculees.
"""
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from perception.parsers import csv_parser

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []
    for si in root.findall("m:si", _NS):
        strings.append("".join(t.text or "" for t in si.iter(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    return strings


def _sheet_path(archive, sheet_name):
    """Chemin interne de la feuille nommee ``sheet_name`` (via workbook.xml
    + relations), ou ``None`` si elle n'existe pas."""
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.get("Id"): rel.get("Target")
        for rel in rels.iter("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
    }
    for sheet in workbook.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
        if sheet.get("name") == sheet_name:
            target = rel_targets.get(
                sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
            if target:
                return target if target.startswith("xl/") else f"xl/{target}"
    return None


def _column_of(cell_ref):
    match = re.match(r"([A-Z]+)", cell_ref or "")
    return match.group(1) if match else ""


def _cell_value(cell, shared):
    cell_type = cell.get("t")
    value_el = cell.find("m:v", _NS)
    if cell_type == "inlineStr":
        is_el = cell.find("m:is", _NS)
        if is_el is not None:
            return "".join(t.text or "" for t in is_el.iter(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        return None
    if value_el is None:
        return None
    if cell_type == "s":
        try:
            return shared[int(value_el.text)]
        except (ValueError, IndexError):
            return None
    return value_el.text


def read_rows(path, profile_body):
    """Lit la feuille declaree par le profil et renvoie les
    enregistrements bruts mappes (premiere ligne = en-tetes). Leve
    ``LookupError`` si la feuille declaree n'existe pas."""
    sheet_name = profile_body.get("sheet")
    mapping = profile_body["mapping"]

    with zipfile.ZipFile(path) as archive:
        sheet_path = _sheet_path(archive, sheet_name) if sheet_name else None
        if sheet_path is None:
            raise LookupError(f"feuille introuvable : {sheet_name!r}")

        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(sheet_path))

        rows = []
        for row_el in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            cells = {}
            for cell in row_el.findall("m:c", _NS):
                cells[_column_of(cell.get("r"))] = _cell_value(cell, shared)
            rows.append(cells)

    if not rows:
        return []

    header_row = rows[0]
    columns_by_letter = {letter: name for letter, name in header_row.items() if name}

    records = []
    for row_cells in rows[1:]:
        raw = {columns_by_letter[letter]: value
               for letter, value in row_cells.items() if letter in columns_by_letter}
        records.append({target: raw.get(source_col) for source_col, target in mapping.items()})
    return records


def parse(conn, path, profile=None):
    """Integre un classeur XLSX depose - meme contrat que
    ``csv_parser.parse`` (profil requis, feuille configurable par profil,
    sinon anomalie ; validation M07 ; emballage M04 ; dedup M08)."""
    if profile is None:
        profile = csv_parser.find_profile(conn, path)
    if profile is None:
        anomaly_id = csv_parser.missing_profile_anomaly(conn, path)
        return {"status": "no_profile", "anomaly_id": anomaly_id}

    try:
        records = read_rows(path, profile["body"])
    except LookupError as exc:
        anomaly_id = csv_parser.missing_profile_anomaly(conn, path, reason=str(exc))
        return {"status": "sheet_not_found", "anomaly_id": anomaly_id}

    return csv_parser.ingest_records(conn, path, profile, records)
