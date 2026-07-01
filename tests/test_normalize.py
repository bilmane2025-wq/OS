"""Tests T-M04-2 : normalisation en evenement (avec enveloppe).

Prouve les criteres du backlog : M04 ne calcule rien, ne decide rien - il
produit 0..n evenements ou une quarantaine. DoD : un evenement valide est
ecrit au journal.
"""
import json
import os
import shutil
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core.envelope import validate_envelope  # noqa: E402
from perception import intake_folder  # noqa: E402


class NormalizeTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_normalize")
        self.inbox_dir = os.path.join(base, "inbox")
        self.archive_dir = os.path.join(base, "archive")
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(self.inbox_dir)
        os.makedirs(self.archive_dir)

        self.db_path = os.path.join(base, "eos.db")
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        base = os.path.dirname(self.inbox_dir)
        if os.path.isdir(base):
            shutil.rmtree(base)

    def _drop(self, filename, content=b"contenu de test"):
        path = os.path.join(self.inbox_dir, filename)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def _event_row(self, event_id):
        return self.conn.execute(
            "SELECT event_id, type, source, author, payload_json, hash "
            "FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()


class RecognizedFileProducesAnEventTests(NormalizeTestCase):
    def test_a_recognized_file_produces_exactly_one_valid_event(self):
        self._drop("facture.pdf")
        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "facture.pdf")

        self.assertEqual(outcome["status"], "processed")
        row = self._event_row(outcome["event_id"])
        self.assertIsNotNone(row)  # DoD : un evenement valide est ecrit au journal.

        event_id, type_, source, author, payload_json, hash_ = row
        self.assertEqual(type_, "PERCEPTION.DocumentReceived")
        self.assertEqual(source, "inbox/facture.pdf")
        self.assertTrue(author)
        self.assertTrue(hash_)

    def test_the_written_event_carries_a_complete_valid_envelope(self):
        self._drop("mail.eml")
        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        stored = json.loads(payload_json)

        # validate_envelope leve une exception si l'enveloppe est incomplete :
        # ce simple appel est la preuve que l'evenement est correctement enveloppe.
        self.assertTrue(validate_envelope(stored["envelope"]))
        self.assertEqual(stored["envelope"]["confidence"]["nature"], "fait")

    def test_normalize_does_not_interpret_the_file_content(self):
        """M04 ne calcule rien, ne decide rien : le payload ne contient que
        des metadonnees structurelles, jamais un champ metier invente."""
        self._drop("export.csv", content=b"montant,date\n42,2028-01-01\n")
        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "export.csv")

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        payload = json.loads(payload_json)["payload"]

        self.assertEqual(set(payload.keys()), {"filename", "route", "file_hash", "size_bytes"})
        self.assertNotIn("montant", payload)
        self.assertNotIn("date", payload)

    def test_each_processed_file_produces_zero_or_one_event_never_more(self):
        for filename in ("a.pdf", "b.csv", "c.xlsx"):
            self._drop(filename, content=f"contenu de {filename}".encode())
            outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, filename)
            count = self.conn.execute(
                "SELECT COUNT(*) FROM events WHERE payload_json LIKE ?",
                (f'%"filename": "{filename}"%',),
            ).fetchone()[0]
            self.assertEqual(count, 1)
            self.assertIn("event_id", outcome)


class UnrecognizedFileProducesQuarantineTests(NormalizeTestCase):
    def test_unrecognized_extension_produces_a_quarantine_not_a_fact_event(self):
        self._drop("mystere.docx")
        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "mystere.docx")

        self.assertEqual(outcome["status"], "quarantined")

        (type_,) = self.conn.execute(
            "SELECT type FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        self.assertEqual(type_, "SYSTEM.Quarantine")

        no_perception_event = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type LIKE 'PERCEPTION.%'"
        ).fetchone()[0]
        self.assertEqual(no_perception_event, 0)

    def test_quarantine_creates_a_traceable_anomaly(self):
        self._drop("mystere.docx")
        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "mystere.docx")

        anomaly = self.conn.execute(
            "SELECT type, state, refs_json FROM anomalies WHERE anomaly_id = ?",
            (outcome["anomaly_id"],),
        ).fetchone()
        self.assertIsNotNone(anomaly)
        anomaly_type, state, refs_json = anomaly
        self.assertEqual(anomaly_type, "perception/unrouted-file")
        self.assertEqual(state, "ouverte")
        self.assertEqual(json.loads(refs_json)["event_id"], outcome["event_id"])

    def test_quarantined_file_is_still_archived(self):
        self._drop("mystere.docx")
        intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "mystere.docx")

        self.assertNotIn("mystere.docx", os.listdir(self.inbox_dir))
        self.assertTrue(any(name.endswith("_mystere.docx") for name in os.listdir(self.archive_dir)))

    def test_quarantine_event_also_carries_a_complete_envelope(self):
        self._drop("mystere.docx")
        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "mystere.docx")

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        stored = json.loads(payload_json)
        self.assertTrue(validate_envelope(stored["envelope"]))


if __name__ == "__main__":
    unittest.main()
