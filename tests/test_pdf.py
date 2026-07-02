"""Tests T-M06-1 : parseur PDF texte (factures natives).

Critere backlog : montant illisible -> anomalie + demande de saisie
manuelle. DoD : test sur une facture PDF reelle.
"""
import json
import os
import shutil
import sqlite3
import sys
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import rules  # noqa: E402
from perception.parsers import pdf_parser  # noqa: E402


def build_pdf(path, lines, compress=False):
    """Construit un vrai PDF 1.4 monopage avec du texte (operateurs Tj),
    flux optionnellement compresse FlateDecode - lisible par tout lecteur
    PDF."""
    text_ops = ["BT", "/F1 12 Tf", "50 780 Td"]
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        text_ops.append(f"({escaped}) Tj")
        text_ops.append("0 -16 Td")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")

    filter_entry = ""
    if compress:
        stream = zlib.compress(stream)
        filter_entry = " /Filter /FlateDecode"

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)}{filter_entry} >>".encode() + b"\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()

    with open(path, "wb") as handle:
        handle.write(bytes(out))
    return path


INVOICE_LINES = [
    "FACTURE N. 2028-0412",
    "Fournisseur : Foodex SPRL",
    "Date : 12/04/2028",
    "Poke bowls x 40",
    "Total TTC : 542,80 EUR",
]


class PdfTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_pdf")
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(base)
        self.base = base
        self.db_path = os.path.join(base, "eos.db")
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        rules.load_seed_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.base)


class RealInvoiceTests(PdfTestCase):
    """DoD : test sur une facture PDF reelle (structure PDF 1.4 valide)."""

    def test_amount_date_supplier_are_extracted(self):
        path = build_pdf(os.path.join(self.base, "facture_foodex.pdf"), INVOICE_LINES)

        outcome = pdf_parser.parse(self.conn, path)

        self.assertEqual(outcome["status"], "parsed")
        self.assertEqual(outcome["fields"]["montant"], "542,80")
        self.assertEqual(outcome["fields"]["date"], "12/04/2028")
        self.assertEqual(outcome["fields"]["fournisseur"], "Foodex SPRL")
        self.assertEqual(outcome["missing"], [])
        self.assertIsNone(outcome["anomaly_id"])

    def test_compressed_flatedecode_stream_is_also_read(self):
        path = build_pdf(os.path.join(self.base, "facture_zip.pdf"), INVOICE_LINES, compress=True)
        outcome = pdf_parser.parse(self.conn, path)
        self.assertEqual(outcome["fields"]["montant"], "542,80")

    def test_event_is_written_with_extraction_rule_reference(self):
        path = build_pdf(os.path.join(self.base, "facture_foodex.pdf"), INVOICE_LINES)
        outcome = pdf_parser.parse(self.conn, path)

        row = self.conn.execute(
            "SELECT type, rule_version_ref, payload_json FROM events WHERE event_id = ?",
            (outcome["event_id"],),
        ).fetchone()
        self.assertEqual(row[0], "PERCEPTION.InvoiceReceived")
        self.assertEqual(row[1], "extraction/facture-pdf@1")
        payload = json.loads(row[2])["payload"]
        self.assertEqual(payload["fields"]["fournisseur"], "Foodex SPRL")

    def test_extracted_event_is_nature_mesure_never_fait(self):
        path = build_pdf(os.path.join(self.base, "facture_foodex.pdf"), INVOICE_LINES)
        outcome = pdf_parser.parse(self.conn, path)

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        envelope = json.loads(payload_json)["envelope"]
        self.assertEqual(envelope["confidence"]["nature"], "mesuré")


class UnreadableFieldTests(PdfTestCase):
    """Critere backlog : montant illisible -> anomalie + demande de saisie
    manuelle - jamais une valeur inventee."""

    def test_missing_amount_creates_anomaly_with_manual_entry_request(self):
        lines = ["FACTURE", "Fournisseur : Foodex SPRL", "Date : 12/04/2028",
                 "Total TTC : illisible"]
        path = build_pdf(os.path.join(self.base, "facture_sans_montant.pdf"), lines)

        outcome = pdf_parser.parse(self.conn, path)

        self.assertIn("montant", outcome["missing"])
        self.assertNotIn("montant", outcome["fields"])  # jamais invente
        row = self.conn.execute(
            "SELECT type, recommendation, refs_json FROM anomalies WHERE anomaly_id = ?",
            (outcome["anomaly_id"],),
        ).fetchone()
        self.assertEqual(row[0], "perception/champ-illisible")
        self.assertIn("manuellement", row[1])
        self.assertIn("montant", json.loads(row[2])["missing"])

    def test_scanned_pdf_without_text_reports_all_fields_missing(self):
        path = os.path.join(self.base, "scan.pdf")
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n% aucun flux textuel\n%%EOF\n")

        outcome = pdf_parser.parse(self.conn, path)

        self.assertEqual(set(outcome["missing"]), {"montant", "date", "fournisseur"})
        self.assertEqual(outcome["fields"], {})
        self.assertIsNotNone(outcome["anomaly_id"])

    def test_extraction_rule_is_bitemporal(self):
        """Une v2 de la regle d'extraction s'applique a partir de sa date
        d'effet ; le passe reste interprete par la v1 (rejeu fidele)."""
        v1 = rules.get(self.conn, "extraction/facture-pdf", "2028-01-01T00:00:00Z")
        new_body = json.loads(json.dumps(v1["body"]))
        new_body["fields"]["montant"] = [r"Grand total\s*[:=]?\s*([0-9]+[.,][0-9]{2})"]
        rules.add_version(self.conn, "extraction/facture-pdf", new_body,
                          valid_from="2028-06-01T00:00:00Z", origin="manual")

        lines = ["Fournisseur : Foodex SPRL", "Date : 12/04/2028", "Grand total : 99,99"]
        path = build_pdf(os.path.join(self.base, "facture_v2.pdf"), lines)

        before = pdf_parser.parse(self.conn, path, at_date="2028-05-01T00:00:00Z")
        after = pdf_parser.parse(self.conn, path, at_date="2028-07-01T00:00:00Z")

        self.assertIn("montant", before["missing"])   # v1 ne connait pas "Grand total"
        self.assertEqual(after["fields"]["montant"], "99,99")  # v2 le connait


if __name__ == "__main__":
    unittest.main()
