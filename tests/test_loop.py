"""Tests T-M00-3 : la boucle de synchronisation vivante.

Critere backlog : un fichier depose se retrouve, sans action humaine, en
KPI + anomalies + vues. DoD : test bout-en-bout (depot -> ecran).
"""
import os
import shutil
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from calc import derivation, kpi_catalog  # noqa: E402
from core import event_store, rules  # noqa: E402
from experience import views  # noqa: E402
from governance import observability  # noqa: E402
from perception.parsers import csv_parser  # noqa: E402
from tests.test_email import _build_eml_bytes  # noqa: E402

RELEVE_CSV = (
    "Date valeur;Montant;Devise;Contrepartie;Communication\n"
    "2028-04-01T00:00:00Z;-142,50;EUR;Foodex;Facture 123\n"
    "2028-04-02T00:00:00Z;890,00;EUR;Uber Eats;Versement semaine 13\n"
)


class LoopTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_loop")
        if os.path.isdir(base):
            shutil.rmtree(base)
        self.inbox_dir = os.path.join(base, "inbox")
        self.archive_dir = os.path.join(base, "archive")
        os.makedirs(self.inbox_dir)
        os.makedirs(self.archive_dir)

        self.db_path = os.path.join(base, "eos.db")
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)
        csv_parser.load_profiles_as_rules(self.conn)
        self._saved_registry = dict(derivation._REGISTRY)

    def tearDown(self):
        derivation._REGISTRY.clear()
        derivation._REGISTRY.update(self._saved_registry)
        self.conn.close()
        shutil.rmtree(os.path.dirname(self.inbox_dir))

    def _drop(self, filename, content):
        path = os.path.join(self.inbox_dir, filename)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(path, mode) as handle:
            handle.write(content)
        return path

    def _cycle(self):
        return eos_app.sync_cycle(self.conn, self.inbox_dir, self.archive_dir)


class EndToEndTests(LoopTestCase):
    """DoD : depot -> ecran, sans aucune action humaine."""

    def test_a_dropped_csv_becomes_kpi_anomalies_and_screen(self):
        self._drop("releve-avril.csv", RELEVE_CSV)

        outcome = self._cycle()

        # 1. Ingere : evenements StatementLine au journal.
        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.StatementLine'"
        ).fetchone()[0]
        self.assertEqual(count, 2)
        self.assertEqual(outcome["new_events"], 2)

        # 2. Graphe : les transactions existent, reliees a leur compte.
        transactions = self.conn.execute(
            "SELECT COUNT(*) FROM objects WHERE type = 'Transaction'").fetchone()[0]
        self.assertEqual(transactions, 2)

        # 3. KPI : tresorerie calculee avec confiance, sans action humaine.
        tresorerie = kpi_catalog.get(self.conn, "tresorerie")
        self.assertAlmostEqual(tresorerie["value"], 747.5)
        self.assertEqual(tresorerie["nature"], "fait")

        # 4. Anomalies : la reconciliation a constate l'ecart
        #    encaissements (890) vs ventes (0).
        reconciliation_anomalies = self.conn.execute(
            "SELECT COUNT(*) FROM anomalies "
            "WHERE type = 'reconciliation/ecart-encaissement-vente'").fetchone()[0]
        self.assertEqual(reconciliation_anomalies, 1)

        # 5. Ecran : la Vue Instantanee montre la tresorerie et l'alerte.
        rendered = views.render_instant(self.conn)
        self.assertIn("747.50 EUR", rendered)
        self.assertIn("attention", rendered)

        # 6. Trace : depot journalise, inbox videe, source archivee.
        (status,) = self.conn.execute(
            "SELECT status FROM ingestion_log WHERE file = 'releve-avril.csv'"
        ).fetchone()
        self.assertEqual(status, "parsed")
        self.assertEqual(os.listdir(self.inbox_dir), [])
        self.assertTrue(any(n.endswith("_releve-avril.csv")
                            for n in os.listdir(self.archive_dir)))

    def test_a_dropped_eml_goes_through_the_same_living_pipeline(self):
        eml = _build_eml_bytes(attachments=[
            ("facture.pdf", b"%PDF-1.4 fake", "application", "pdf")])
        self._drop("mail.eml", eml)

        outcome = self._cycle()

        email_events = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.EmailReceived'"
        ).fetchone()[0]
        self.assertEqual(email_events, 1)
        self.assertGreaterEqual(outcome["new_events"], 1)
        self.assertEqual(os.listdir(self.inbox_dir), [])


class IncrementalityTests(LoopTestCase):
    def test_the_loop_recomputes_only_impacted_derivations(self):
        """La boucle vivante ne recalcule jamais globalement : un releve
        bancaire ne recompute que le KPI dependant des StatementLine."""
        self._drop("releve-avril.csv", RELEVE_CSV)
        outcome = self._cycle()

        self.assertEqual(outcome["recomputed"], ["kpi/tresorerie"])

    def test_an_empty_cycle_ingests_and_recomputes_nothing(self):
        outcome = self._cycle()
        self.assertEqual(outcome["ingested"], [])
        self.assertEqual(outcome["new_events"], 0)
        self.assertEqual(outcome["recomputed"], [])

    def test_redepositing_the_same_file_creates_zero_duplicates(self):
        self._drop("releve-avril.csv", RELEVE_CSV)
        self._cycle()
        self._drop("releve-avril.csv", RELEVE_CSV)
        second = self._cycle()

        self.assertEqual(second["new_events"], 0)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.StatementLine'"
        ).fetchone()[0]
        self.assertEqual(count, 2)


class AlertsUnderBudgetTests(LoopTestCase):
    def test_cycle_returns_grouped_alerts_under_the_attention_cap(self):
        """Criteres MVP : alertes groupees, plafond d'attention respecte."""
        self._drop("releve-avril.csv", RELEVE_CSV)
        outcome = self._cycle()

        budgeted = outcome["attention"]
        self.assertLessEqual(len(budgeted["shown"]), 3)
        # La tresorerie (747.50) est sous le seuil versionne (2000) : le
        # niveau proactif l'a transformee en alerte de seuil groupee.
        shown_types = {a["type"] for a in budgeted["shown"]}
        self.assertIn("seuil/tresorerie", shown_types)
        # Rien n'est perdu : total = montre + supprime.
        self.assertEqual(budgeted["total"],
                         len(budgeted["shown"]) + budgeted["suppressed"])

    def test_reconciliation_anomaly_is_never_duplicated_across_cycles(self):
        self._drop("releve-avril.csv", RELEVE_CSV)
        self._cycle()
        self._drop("autre-releve.csv", RELEVE_CSV.replace("890,00", "891,00"))
        self._cycle()

        count = self.conn.execute(
            "SELECT COUNT(*) FROM anomalies "
            "WHERE type = 'reconciliation/ecart-encaissement-vente' "
            "AND state = 'ouverte'").fetchone()[0]
        self.assertEqual(count, 1)


class SourceFreshnessTests(LoopTestCase):
    def test_a_received_profiled_file_refreshes_its_declared_source(self):
        observability.register_source(
            self.conn, "banque-releve", "Releve bancaire", "StatementLine",
            "depot-csv", 7)
        self._drop("releve-avril.csv", RELEVE_CSV)

        self._cycle()

        (last_seen, status) = self.conn.execute(
            "SELECT last_seen, status FROM sources WHERE source_id = 'banque-releve'"
        ).fetchone()
        self.assertIsNotNone(last_seen)
        self.assertEqual(status, "ok")


class RunLoopTests(LoopTestCase):
    def test_run_loop_honours_the_cycle_count_and_cadence(self):
        """Cadence configurable : la boucle s'arrete apres N cycles."""
        self._drop("releve-avril.csv", RELEVE_CSV)
        completed = eos_app.run_loop(
            db_path=self.db_path, inbox_dir=self.inbox_dir,
            archive_dir=self.archive_dir, interval_seconds=0.01, cycles=2)

        self.assertEqual(completed, 2)
        conn_check = event_store.connect(self.db_path)
        try:
            count = conn_check.execute(
                "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.StatementLine'"
            ).fetchone()[0]
        finally:
            conn_check.close()
        self.assertEqual(count, 2)

    def test_run_loop_stops_on_stop_event(self):
        stop = threading.Event()
        stop.set()  # deja demande : la boucle ne fait aucun tour
        completed = eos_app.run_loop(
            db_path=self.db_path, inbox_dir=self.inbox_dir,
            archive_dir=self.archive_dir, interval_seconds=0.01,
            cycles=5, stop_event=stop)
        self.assertEqual(completed, 0)


if __name__ == "__main__":
    unittest.main()
