"""Tests T-M04-1 : poller du dossier inbox (detection, routage, archivage).

DoD : un fichier de chaque type (.eml, .pdf, .csv, .xlsx, .png/.jpg) est
detecte, route et archive apres traitement.
"""
import os
import shutil
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from perception import intake_folder  # noqa: E402


class IntakeTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_intake")
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

    def _archived_names(self):
        return os.listdir(self.archive_dir)


class ScanAndRouteTests(IntakeTestCase):
    def test_scan_inbox_lists_deposited_files_and_ignores_dotfiles(self):
        self._drop("facture.pdf")
        self._drop("export.csv")
        open(os.path.join(self.inbox_dir, ".gitkeep"), "w").close()

        names = intake_folder.scan_inbox(self.inbox_dir)
        self.assertEqual(names, ["export.csv", "facture.pdf"])

    def test_scan_inbox_on_missing_directory_returns_empty_list(self):
        self.assertEqual(intake_folder.scan_inbox("/no/such/dir"), [])

    def test_route_for_each_known_extension(self):
        self.assertEqual(intake_folder.route_for("mail.eml"), "email")
        self.assertEqual(intake_folder.route_for("facture.pdf"), "pdf")
        self.assertEqual(intake_folder.route_for("export.csv"), "csv")
        self.assertEqual(intake_folder.route_for("balance.xlsx"), "xlsx")
        self.assertEqual(intake_folder.route_for("ticket.png"), "image")
        self.assertEqual(intake_folder.route_for("ticket.jpg"), "image")
        self.assertEqual(intake_folder.route_for("ticket.jpeg"), "image")

    def test_route_for_is_case_insensitive(self):
        self.assertEqual(intake_folder.route_for("FACTURE.PDF"), "pdf")

    def test_route_for_unknown_extension_is_none(self):
        self.assertIsNone(intake_folder.route_for("mystere.docx"))


class OneFileOfEachTypeTests(IntakeTestCase):
    """DoD : test avec un fichier de chaque type."""

    def _assert_detected_routed_and_archived(self, filename, expected_route):
        self._drop(filename)

        outcome = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, filename)

        self.assertEqual(outcome["status"], "processed")
        self.assertEqual(outcome["route"], expected_route)
        self.assertNotIn(filename, os.listdir(self.inbox_dir))
        self.assertTrue(any(name.endswith(f"_{filename}") for name in self._archived_names()))

    def test_eml_file(self):
        self._assert_detected_routed_and_archived("mail.eml", "email")

    def test_pdf_file(self):
        self._assert_detected_routed_and_archived("facture.pdf", "pdf")

    def test_csv_file(self):
        self._assert_detected_routed_and_archived("export.csv", "csv")

    def test_xlsx_file(self):
        self._assert_detected_routed_and_archived("balance.xlsx", "xlsx")

    def test_png_file(self):
        self._assert_detected_routed_and_archived("ticket.png", "image")

    def test_jpg_file(self):
        self._assert_detected_routed_and_archived("ticket.jpg", "image")


class ProcessInboxTests(IntakeTestCase):
    def test_process_inbox_handles_every_deposited_file(self):
        self._drop("mail.eml", content=b"contenu eml")
        self._drop("facture.pdf", content=b"contenu pdf")
        self._drop("export.csv", content=b"contenu csv")

        outcomes = intake_folder.process_inbox(self.conn, self.inbox_dir, self.archive_dir)

        self.assertEqual(len(outcomes), 3)
        self.assertEqual({o["status"] for o in outcomes}, {"processed"})
        self.assertEqual(intake_folder.scan_inbox(self.inbox_dir), [])
        self.assertEqual(len(self._archived_names()), 3)

    def test_process_inbox_on_empty_inbox_returns_empty_list(self):
        self.assertEqual(intake_folder.process_inbox(self.conn, self.inbox_dir, self.archive_dir), [])


class ReplayProducesZeroDuplicatesTests(IntakeTestCase):
    """T-M08-1 (integration) : rejouer un import ne cree aucun doublon."""

    def test_dropping_the_same_content_twice_creates_only_one_event(self):
        self._drop("facture.pdf", content=b"meme contenu")
        first = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "facture.pdf")
        self.assertEqual(first["status"], "processed")

        # Le meme contenu est redepose (par ex. un re-envoi par email).
        self._drop("facture.pdf", content=b"meme contenu")
        second = intake_folder.process_file(self.conn, self.inbox_dir, self.archive_dir, "facture.pdf")
        self.assertEqual(second["status"], "duplicate")

        event_count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.DocumentReceived'"
        ).fetchone()[0]
        self.assertEqual(event_count, 1)

    def test_replaying_a_batch_of_files_creates_zero_new_duplicates(self):
        for i in range(5):
            self._drop(f"releve_{i}.csv", content=f"ligne-{i}".encode())
        first_pass = intake_folder.process_inbox(self.conn, self.inbox_dir, self.archive_dir)
        self.assertTrue(all(o["status"] == "processed" for o in first_pass))

        # "Rejeu" de l'import : on redepose les 5 memes contenus.
        for i in range(5):
            self._drop(f"releve_{i}.csv", content=f"ligne-{i}".encode())
        second_pass = intake_folder.process_inbox(self.conn, self.inbox_dir, self.archive_dir)

        self.assertTrue(all(o["status"] == "duplicate" for o in second_pass))
        event_count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.DocumentReceived'"
        ).fetchone()[0]
        self.assertEqual(event_count, 5)


if __name__ == "__main__":
    unittest.main()
