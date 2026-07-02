"""Tests T-M33-1 : score de sante des donnees (governance.observability).

Criteres backlog : sources manquantes tirent le score ; watchdog alerte
les retards. DoD : score affiche + alerte de retard testee.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
import sqlite3  # noqa: E402
from governance import observability  # noqa: E402

NOW = "2028-04-15T00:00:00Z"


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_observability.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

        observability.register_source(
            self.conn, "banque", "Releve bancaire", "StatementLine", "depot-csv", 7)
        observability.register_source(
            self.conn, "uber", "Export Uber Eats", "OrderObserved", "depot-csv", 7)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_fresh_sources_give_a_full_score(self):
        observability.mark_seen(self.conn, "banque", "2028-04-14T00:00:00Z")
        observability.mark_seen(self.conn, "uber", "2028-04-13T00:00:00Z")

        report = observability.health(self.conn, NOW)
        self.assertEqual(report["score"], 1.0)
        self.assertEqual(report["late"], [])

    def test_missing_sources_pull_the_score_down_honestly(self):
        """Critere backlog : les sources manquantes tirent le score -
        jamais un faux 100 %."""
        observability.mark_seen(self.conn, "banque", "2028-04-14T00:00:00Z")
        # uber n'a jamais ete recue.

        report = observability.health(self.conn, NOW)
        self.assertEqual(report["score"], 0.5)
        self.assertEqual(len(report["late"]), 1)
        self.assertEqual(report["late"][0]["source_id"], "uber")
        self.assertEqual(report["late"][0]["status"], "jamais-recue")

    def test_a_late_source_is_flagged(self):
        observability.mark_seen(self.conn, "banque", "2028-04-01T00:00:00Z")  # 14 j > 7 j
        observability.mark_seen(self.conn, "uber", "2028-04-14T00:00:00Z")

        report = observability.health(self.conn, NOW)
        self.assertEqual(report["score"], 0.5)
        self.assertEqual(report["late"][0]["source_id"], "banque")
        self.assertEqual(report["late"][0]["status"], "en-retard")

    def test_no_declared_source_means_zero_score_not_a_fake_hundred(self):
        empty_db = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "_tmp_test_observability_empty.db")
        if os.path.exists(empty_db):
            os.remove(empty_db)
        eos_app.init_db(empty_db)
        conn = sqlite3.connect(empty_db)
        try:
            self.assertEqual(observability.health(conn, NOW)["score"], 0.0)
        finally:
            conn.close()
            os.remove(empty_db)

    def test_watchdog_creates_an_anomaly_per_late_source(self):
        """DoD : alerte de retard testee."""
        observability.mark_seen(self.conn, "banque", "2028-04-01T00:00:00Z")
        observability.mark_seen(self.conn, "uber", "2028-04-14T00:00:00Z")

        created = observability.watchdog(self.conn, NOW)

        self.assertEqual(len(created), 1)
        row = self.conn.execute(
            "SELECT type, state, refs_json FROM anomalies WHERE anomaly_id = ?",
            (created[0],)).fetchone()
        self.assertEqual(row[0], "observability/source-en-retard")
        self.assertEqual(row[1], "ouverte")
        self.assertIn("banque", row[2])

    def test_watchdog_never_duplicates_an_open_alert(self):
        observability.mark_seen(self.conn, "banque", "2028-04-01T00:00:00Z")
        observability.mark_seen(self.conn, "uber", "2028-04-14T00:00:00Z")

        first = observability.watchdog(self.conn, NOW)
        second = observability.watchdog(self.conn, NOW)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
