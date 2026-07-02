"""Tests T-M06-2 : OCR image + confirmation manuelle (mode officiel).

Critere backlog : rien n'entre en « mesuré » sans confirmation humaine.
DoD : cycle OCR -> proposition -> confirmation teste.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from governance import permissions  # noqa: E402
from perception.parsers import image_ocr  # noqa: E402

HUMAN = "human:pierre"
TICKET_TEXT = "RESTO TICKET\nTotal : 42,50\nDate : 12/04/2028\nMerci !"


def fake_engine(path):
    """Moteur OCR local injecte pour le test (aucun binaire requis)."""
    return TICKET_TEXT


def no_engine(path):
    return None


class OcrTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_ocr.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        permissions.grant(self.conn, HUMAN, "OcrConfirm", 1)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class ProposalTests(OcrTestCase):
    def test_read_proposes_estimated_fields_with_low_confidence(self):
        outcome = image_ocr.read("ticket.png", engine=fake_engine)

        self.assertTrue(outcome["ocr_available"])
        self.assertEqual(outcome["proposals"]["montant"]["value"], "42,50")
        self.assertEqual(outcome["proposals"]["date"]["value"], "12/04/2028")
        for proposal in outcome["proposals"].values():
            self.assertEqual(proposal["nature"], "estimé")   # jamais un fait
            self.assertLess(proposal["score"], 0.5)          # confiance basse

    def test_read_without_local_engine_proposes_nothing(self):
        outcome = image_ocr.read("ticket.png", engine=no_engine)
        self.assertFalse(outcome["ocr_available"])
        self.assertEqual(outcome["proposals"], {})

    def test_reading_alone_writes_nothing_to_the_journal(self):
        """Rien n'entre en mesure sans confirmation : la lecture seule ne
        produit aucun evenement."""
        image_ocr.read("ticket.png", engine=fake_engine)
        count = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(count, 0)

    def test_manual_entry_request_when_no_engine(self):
        anomaly_id = image_ocr.request_manual_entry(self.conn, "ticket.png")
        row = self.conn.execute(
            "SELECT type, recommendation FROM anomalies WHERE anomaly_id = ?",
            (anomaly_id,)).fetchone()
        self.assertEqual(row[0], "perception/saisie-manuelle-requise")
        self.assertIn("manuel", row[1])


class ConfirmationCycleTests(OcrTestCase):
    """DoD : cycle OCR -> proposition -> confirmation teste."""

    def test_full_cycle_produces_a_measured_fact_only_after_confirmation(self):
        proposals = image_ocr.read("ticket.png", engine=fake_engine)

        outcome = image_ocr.confirm(
            self.conn, "ticket.png", proposals,
            confirmed_fields={"montant": "42,50", "date": "12/04/2028"},
            author=HUMAN)

        # 1. La validation humaine est un evenement HUMAN.Validation.
        validation = self.conn.execute(
            "SELECT type, author FROM events WHERE event_id = ?",
            (outcome["validation_event_id"],)).fetchone()
        self.assertEqual(validation, ("HUMAN.Validation", HUMAN))

        # 2. Le fait mesure existe, cause par la validation.
        row = self.conn.execute(
            "SELECT type, causation_id, payload_json FROM events WHERE event_id = ?",
            (outcome["measured_event_id"],)).fetchone()
        self.assertEqual(row[0], "PERCEPTION.InvoiceReceived")
        self.assertEqual(row[1], outcome["validation_event_id"])
        stored = json.loads(row[2])
        self.assertEqual(stored["envelope"]["confidence"]["nature"], "mesuré")
        self.assertEqual(stored["payload"]["fields"]["montant"], "42,50")

    def test_human_can_correct_a_proposal_before_confirming(self):
        proposals = image_ocr.read("ticket.png", engine=fake_engine)
        outcome = image_ocr.confirm(
            self.conn, "ticket.png", proposals,
            confirmed_fields={"montant": "43,00"},  # l'humain corrige
            author=HUMAN)

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?",
            (outcome["measured_event_id"],)).fetchone()
        self.assertEqual(json.loads(payload_json)["payload"]["fields"]["montant"], "43,00")

    def test_confirmation_by_unauthorized_actor_is_blocked(self):
        """Rien n'entre en mesure sans un humain autorise (M28)."""
        proposals = image_ocr.read("ticket.png", engine=fake_engine)
        with self.assertRaises(permissions.AuthorityError):
            image_ocr.confirm(self.conn, "ticket.png", proposals,
                              {"montant": "42,50"}, author="agent:anonyme")

        count = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(count, 0)  # aucun evenement n'a fuite

    def test_confirmation_leaves_an_access_trace(self):
        proposals = image_ocr.read("ticket.png", engine=fake_engine)
        outcome = image_ocr.confirm(self.conn, "ticket.png", proposals,
                                    {"montant": "42,50"}, author=HUMAN)
        row = self.conn.execute(
            "SELECT subject, action, target FROM access_log").fetchone()
        self.assertEqual(row, (HUMAN, "ocr-confirm", outcome["measured_event_id"]))


if __name__ == "__main__":
    unittest.main()
