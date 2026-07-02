"""Tests T-M31-1 : reconciliation & anomalies (governance.audit).

Critere backlog : un ecart > seuil -> anomalie tracee. DoD : test sur un
ecart connu.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store, rules  # noqa: E402
from governance import audit  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_audit.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _sale(self, num, amount):
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": f"C-{num}", "montant": amount}}, num)

    def _collection(self, num, amount):
        make_event(self.conn, "PERCEPTION.StatementLine",
                   {"record": {"date": "2028-04-02", "montant": amount,
                               "contrepartie": "Plateforme", "libelle": "versement"}}, num)

    def test_known_gap_above_threshold_creates_a_full_anomaly(self):
        """DoD : ecart connu (ventes 100, encaissements 80 -> 20 %) au-dela
        du seuil de 5 % -> anomalie avec gravite/proba/impact/reco."""
        self._sale(1, "100,00")
        self._collection(2, "80,00")

        outcome = audit.reconcile_collections_vs_sales(self.conn)

        self.assertAlmostEqual(outcome["ecart"], 20.0)
        self.assertAlmostEqual(outcome["ecart_relatif"], 0.2)
        self.assertIsNotNone(outcome["anomaly_id"])

        row = self.conn.execute(
            "SELECT type, severity, probability, impact, recommendation, state "
            "FROM anomalies WHERE anomaly_id = ?", (outcome["anomaly_id"],)
        ).fetchone()
        self.assertEqual(row[0], "reconciliation/ecart-encaissement-vente")
        self.assertEqual(row[1], "haute")          # gravite
        self.assertEqual(row[2], 1.0)              # probabilite
        self.assertAlmostEqual(row[3], 20.0)       # impact financier
        self.assertTrue(row[4])                    # recommandation presente
        self.assertEqual(row[5], "ouverte")

    def test_gap_below_threshold_creates_no_anomaly(self):
        self._sale(1, "100,00")
        self._collection(2, "98,00")  # ecart 2 % < seuil 5 %

        outcome = audit.reconcile_collections_vs_sales(self.conn)
        self.assertIsNone(outcome["anomaly_id"])

    def test_threshold_is_a_versioned_rule(self):
        """Le seuil vient de la regle versionnee applicable a la date -
        une v2 plus tolerante change le verdict sans toucher au code."""
        self._sale(1, "100,00")
        self._collection(2, "80,00")

        v1 = rules.get(self.conn, audit.RECONCILIATION_RULE, "2028-01-01T00:00:00Z")
        rules.add_version(self.conn, audit.RECONCILIATION_RULE,
                          dict(v1["body"], seuil_pourcentage=0.30),
                          valid_from="2028-06-01T00:00:00Z", origin="manual")

        strict = audit.reconcile_collections_vs_sales(self.conn, at_date="2028-05-01T00:00:00Z")
        tolerant = audit.reconcile_collections_vs_sales(self.conn, at_date="2028-07-01T00:00:00Z")

        self.assertIsNotNone(strict["anomaly_id"])
        self.assertIsNone(tolerant["anomaly_id"])
        self.assertEqual(strict["rule"], f"{audit.RECONCILIATION_RULE}@1")
        self.assertEqual(tolerant["rule"], f"{audit.RECONCILIATION_RULE}@2")

    def test_anomaly_refs_trace_the_figures_and_the_rule(self):
        self._sale(1, "100,00")
        self._collection(2, "50,00")
        outcome = audit.reconcile_collections_vs_sales(self.conn)

        anomalies = audit.open_anomalies(self.conn)
        target = next(a for a in anomalies if a["anomaly_id"] == outcome["anomaly_id"])
        self.assertAlmostEqual(target["refs"]["ventes"], 100.0)
        self.assertAlmostEqual(target["refs"]["encaissements"], 50.0)
        self.assertIn("@", target["refs"]["rule"])

    def test_no_data_no_gap_no_anomaly(self):
        outcome = audit.reconcile_collections_vs_sales(self.conn)
        self.assertIsNone(outcome["anomaly_id"])
        self.assertEqual(outcome["ecart"], 0.0)


if __name__ == "__main__":
    unittest.main()
