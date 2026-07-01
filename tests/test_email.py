"""Tests T-M05-1 : parseur email .eml (perception.email_parser).

DoD : test sur un vrai .eml multi-PJ. Critere backlog exact : un .eml
avec 2 PJ produit 1 EmailReceived + 2 fichiers routes.
"""
import email
import email.policy
import email.utils
import json
import os
import shutil
import sqlite3
import sys
import unittest
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core.envelope import validate_envelope  # noqa: E402
from perception import email_parser, intake_folder  # noqa: E402


def _build_eml_bytes(
    sender="fournisseur@foodex.example",
    subject="Facture Foodex #123",
    date="Mon, 1 Apr 2028 10:00:00 +0200",
    body="Bonjour,\nVeuillez trouver ci-joint la facture.\nCordialement.",
    attachments=(),
):
    message = EmailMessage(policy=email.policy.default)
    if sender is not None:
        message["From"] = sender
    if subject is not None:
        message["Subject"] = subject
    if date is not None:
        message["Date"] = email.utils.format_datetime(email.utils.parsedate_to_datetime(date))
    message.set_content(body)

    for filename, content, maintype, subtype in attachments:
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    return bytes(message)


class EmailTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_email")
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

    def _drop(self, filename, content):
        path = os.path.join(self.inbox_dir, filename)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def _events_of_type(self, type_):
        return self.conn.execute(
            "SELECT event_id, payload_json FROM events WHERE type = ?", (type_,)
        ).fetchall()


class TwoAttachmentsCriterionTests(EmailTestCase):
    """Critere backlog exact : un .eml avec 2 PJ produit 1 EmailReceived +
    2 fichiers routes."""

    def setUp(self):
        super().setUp()
        self.eml_bytes = _build_eml_bytes(
            attachments=[
                ("facture.pdf", b"%PDF-1.4 fake pdf bytes", "application", "pdf"),
                ("export.csv", b"montant,date\n42,2028-01-01\n", "text", "csv"),
            ]
        )
        self._drop("mail.eml", self.eml_bytes)

    def test_produces_exactly_one_email_received_event(self):
        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        events = self._events_of_type("PERCEPTION.EmailReceived")
        self.assertEqual(len(events), 1)

    def test_produces_exactly_two_routed_attachment_files(self):
        outcome = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        self.assertEqual(len(outcome["attachment_outcomes"]), 2)
        routes = {o["route"] for o in outcome["attachment_outcomes"]}
        self.assertEqual(routes, {"pdf", "csv"})
        for o in outcome["attachment_outcomes"]:
            self.assertEqual(o["status"], "processed")

    def test_attachments_are_archived(self):
        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        archived = os.listdir(self.archive_dir)
        self.assertTrue(any(name.endswith("_facture.pdf") for name in archived))
        self.assertTrue(any(name.endswith("_export.csv") for name in archived))

    def test_attachments_each_produce_their_own_document_received_event(self):
        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        events = self._events_of_type("PERCEPTION.DocumentReceived")
        self.assertEqual(len(events), 2)

    def test_original_email_is_archived_and_inbox_is_cleared(self):
        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        self.assertEqual(intake_folder.scan_inbox(self.inbox_dir), [])
        archived = os.listdir(self.archive_dir)
        self.assertTrue(any(name.endswith("_mail.eml") for name in archived))


class MetadataAndBodyTests(EmailTestCase):
    def test_sender_subject_date_and_body_are_captured(self):
        eml_bytes = _build_eml_bytes(
            sender="fournisseur@foodex.example",
            subject="Facture Foodex #123",
            date="Mon, 1 Apr 2028 10:00:00 +0200",
            body="Bonjour,\nVeuillez trouver ci-joint la facture.\n",
        )
        self._drop("mail.eml", eml_bytes)

        outcome = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        (_, payload_json), = self._events_of_type("PERCEPTION.EmailReceived")
        payload = json.loads(payload_json)["payload"]

        self.assertEqual(payload["sender"], "fournisseur@foodex.example")
        self.assertEqual(payload["subject"], "Facture Foodex #123")
        self.assertEqual(payload["date"], "2028-04-01T10:00:00+02:00")
        self.assertIn("Veuillez trouver ci-joint la facture.", payload["body"])
        self.assertEqual(payload["attachments"], [])
        self.assertEqual(outcome["status"], "processed")

    def test_email_without_attachments_produces_no_document_received_event(self):
        self._drop("mail.eml", _build_eml_bytes())
        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        self.assertEqual(len(self._events_of_type("PERCEPTION.DocumentReceived")), 0)

    def test_written_event_carries_a_complete_valid_envelope(self):
        self._drop("mail.eml", _build_eml_bytes())
        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        (_, payload_json), = self._events_of_type("PERCEPTION.EmailReceived")
        envelope = json.loads(payload_json)["envelope"]
        self.assertTrue(validate_envelope(envelope))
        self.assertEqual(envelope["confidence"]["nature"], "fait")
        self.assertEqual(envelope["label"], "Facture Foodex #123")


class RobustnessTests(EmailTestCase):
    def test_missing_or_malformed_date_falls_back_to_now(self):
        eml_bytes = _build_eml_bytes(date=None)
        self._drop("mail.eml", eml_bytes)

        outcome = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")
        self.assertEqual(outcome["status"], "processed")

        (_, payload_json), = self._events_of_type("PERCEPTION.EmailReceived")
        payload = json.loads(payload_json)["payload"]
        self.assertIsNone(payload["date"])
        # valid_from de l'enveloppe doit tout de meme etre une date valide (repli sur "maintenant").
        envelope = json.loads(payload_json)["envelope"]
        self.assertTrue(validate_envelope(envelope))

    def test_garbage_non_mime_content_does_not_crash(self):
        """Compatibilite : un fichier .eml qui n'est pas un vrai message
        (deja utilise par les tests Sprint 2 test_intake.py/test_normalize.py)
        doit tout de meme etre traite proprement, sans exception."""
        self._drop("mail.eml", b"contenu de test")

        outcome = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        self.assertEqual(outcome["status"], "processed")
        self.assertEqual(len(self._events_of_type("PERCEPTION.EmailReceived")), 1)

    def test_subject_with_only_whitespace_falls_back_to_filename_label(self):
        eml_bytes = _build_eml_bytes(subject="   ")
        self._drop("mail.eml", eml_bytes)

        email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        (_, payload_json), = self._events_of_type("PERCEPTION.EmailReceived")
        envelope = json.loads(payload_json)["envelope"]
        self.assertEqual(envelope["label"], "Email recu : mail.eml")

    def test_unknown_attachment_extension_is_quarantined_not_document_received(self):
        eml_bytes = _build_eml_bytes(
            attachments=[("mystere.docx", b"binaire quelconque", "application", "octet-stream")]
        )
        self._drop("mail.eml", eml_bytes)

        outcome = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")

        self.assertEqual(len(outcome["attachment_outcomes"]), 1)
        self.assertEqual(outcome["attachment_outcomes"][0]["status"], "quarantined")
        self.assertEqual(len(self._events_of_type("SYSTEM.Quarantine")), 1)
        self.assertEqual(len(self._events_of_type("PERCEPTION.DocumentReceived")), 0)


class DeduplicationTests(EmailTestCase):
    def test_replaying_the_same_email_creates_no_duplicate(self):
        eml_bytes = _build_eml_bytes(
            attachments=[("facture.pdf", b"%PDF-1.4 fake pdf bytes", "application", "pdf")]
        )
        self._drop("mail.eml", eml_bytes)
        first = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")
        self.assertEqual(first["status"], "processed")

        # Le meme email est redepose (par ex. un re-envoi).
        self._drop("mail.eml", eml_bytes)
        second = email_parser.parse(self.conn, self.inbox_dir, self.archive_dir, "mail.eml")
        self.assertEqual(second["status"], "duplicate")

        self.assertEqual(len(self._events_of_type("PERCEPTION.EmailReceived")), 1)
        self.assertEqual(len(self._events_of_type("PERCEPTION.DocumentReceived")), 1)


class IntakeFolderWiringTests(EmailTestCase):
    """Verifie que intake_folder.process_inbox route bien les .eml vers
    email_parser (integration bout-en-bout, sans regression Sprint 2)."""

    def test_process_inbox_routes_eml_through_email_parser(self):
        eml_bytes = _build_eml_bytes(
            attachments=[("facture.pdf", b"%PDF-1.4 fake pdf bytes", "application", "pdf")]
        )
        self._drop("mail.eml", eml_bytes)
        self._drop("independant.csv", b"montant,date\n1,2028-01-01\n")

        outcomes = intake_folder.process_inbox(self.conn, self.inbox_dir, self.archive_dir)

        self.assertEqual(len(outcomes), 2)
        email_outcome = next(o for o in outcomes if o["filename"] == "mail.eml")
        self.assertEqual(email_outcome["route"], "email")
        self.assertIn("attachment_outcomes", email_outcome)
        self.assertEqual(len(email_outcome["attachment_outcomes"]), 1)

        # 1 EmailReceived (mail.eml) + 2 DocumentReceived (facture.pdf de l'email, independant.csv).
        self.assertEqual(len(self._events_of_type("PERCEPTION.EmailReceived")), 1)
        self.assertEqual(len(self._events_of_type("PERCEPTION.DocumentReceived")), 2)


if __name__ == "__main__":
    unittest.main()
