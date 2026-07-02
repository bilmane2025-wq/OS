"""Tests T-M05-3 : parseur XLSX (balance comptable, exports).

Criteres backlog : feuille/onglet configurable par profil ; sinon
anomalie. DoD : test sur un XLSX reel.
"""
import os
import shutil
import sqlite3
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import rules  # noqa: E402
from perception.parsers import csv_parser, xlsx_parser  # noqa: E402

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def build_xlsx(path, sheet_name, header, rows):
    """Construit un vrai classeur .xlsx (ECMA-376, chaines inline) avec
    une feuille nommee - lisible par Excel/LibreOffice."""
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )

    def row_xml(row_index, values):
        cells = []
        for col_index, value in enumerate(values):
            ref = f"{chr(ord('A') + col_index)}{row_index}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        return f'<row r="{row_index}">{"".join(cells)}</row>'

    all_rows = [row_xml(1, header)] + [row_xml(i + 2, row) for i, row in enumerate(rows)]
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(all_rows)}</sheetData></worksheet>'
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


class XlsxTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_xlsx")
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(base)
        self.base = base
        self.db_path = os.path.join(base, "eos.db")
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        csv_parser.load_profiles_as_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.base)

    def _build_balance(self, filename="balance-2028.xlsx", sheet_name="Feuille1"):
        return build_xlsx(
            os.path.join(self.base, filename), sheet_name,
            header=["Compte", "Libelle", "Debit", "Credit"],
            rows=[
                ["604000", "Achats marchandises", 1250.5, 0],
                ["700000", "Ventes", 0, 8420.0],
                ["", "Ligne sans compte", 1, 2],
            ],
        )


class RealXlsxTests(XlsxTestCase):
    """DoD : test sur un XLSX reel (archive ECMA-376 valide)."""

    def test_valid_rows_become_events(self):
        path = self._build_balance()
        outcome = xlsx_parser.parse(self.conn, path)

        self.assertEqual(outcome["status"], "parsed")
        self.assertEqual(outcome["records"], 3)
        self.assertEqual(len(outcome["appended"]), 2)  # ligne sans compte -> quarantaine
        self.assertEqual(len(outcome["quarantined"]), 1)

        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.FactObserved'"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_replaying_the_import_creates_zero_duplicates(self):
        path = self._build_balance()
        xlsx_parser.parse(self.conn, path)
        second = xlsx_parser.parse(self.conn, path)

        self.assertEqual(len(second["appended"]), 0)
        self.assertEqual(second["duplicates"], 2)

    def test_without_profile_creates_profil_manquant_anomaly(self):
        path = build_xlsx(os.path.join(self.base, "inconnu.xlsx"), "Feuille1",
                          ["A"], [["x"]])
        outcome = xlsx_parser.parse(self.conn, path)

        self.assertEqual(outcome["status"], "no_profile")
        row = self.conn.execute(
            "SELECT type FROM anomalies WHERE anomaly_id = ?", (outcome["anomaly_id"],)
        ).fetchone()
        self.assertEqual(row[0], "perception/profil-manquant")


class SheetConfigurableByProfileTests(XlsxTestCase):
    """Critere backlog : feuille/onglet configurable par profil ; sinon
    anomalie."""

    def test_profile_declared_sheet_is_read(self):
        path = self._build_balance(sheet_name="Feuille1")
        outcome = xlsx_parser.parse(self.conn, path)
        self.assertEqual(outcome["status"], "parsed")

    def test_missing_declared_sheet_creates_an_anomaly_never_a_guess(self):
        path = self._build_balance(sheet_name="AutreFeuille")
        outcome = xlsx_parser.parse(self.conn, path)

        self.assertEqual(outcome["status"], "sheet_not_found")
        self.assertIsNotNone(outcome["anomaly_id"])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type LIKE 'PERCEPTION.%'"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_new_profile_version_can_change_the_sheet(self):
        v1 = rules.get(self.conn, "source-profile/balance-comptable", "2028-01-01T00:00:00Z")
        new_body = dict(v1["body"], sheet="Onglet2")
        rules.add_version(self.conn, "source-profile/balance-comptable", new_body,
                          valid_from="2028-06-01T00:00:00Z", origin="manual")

        path = self._build_balance(sheet_name="Onglet2")
        profile = csv_parser.find_profile(self.conn, path, "2028-07-01T00:00:00Z")
        outcome = xlsx_parser.parse(self.conn, path, profile=profile)
        self.assertEqual(outcome["status"], "parsed")


if __name__ == "__main__":
    unittest.main()
