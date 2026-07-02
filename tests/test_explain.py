"""Tests T-M24-1 : depliage jusqu'a la preuve (explain.unfold).

Critere backlog : « d'ou sort ce chiffre ? » -> chaine complete jusqu'au
fichier/evenement d'origine. DoD : test depliage sur un KPI reel.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from calc import kpi_catalog  # noqa: E402
from core import event_store, rules  # noqa: E402
from intent import explain  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class ExplainTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_explain.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)

        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-1", "montant": "25,00"}}, 1)
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-2", "montant": "35,00"}}, 2)
        kpi_catalog.compute(self.conn, "ca")

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_unfold_returns_the_published_value(self):
        unfolded = explain.unfold(self.conn, "ca")
        self.assertEqual(unfolded["kpi"]["name"], "ca")
        self.assertAlmostEqual(unfolded["kpi"]["value"], 60.0)

    def test_unfold_reaches_the_versioned_rule(self):
        unfolded = explain.unfold(self.conn, "ca")
        self.assertEqual(unfolded["rule"]["name"], "kpi/ca")
        self.assertEqual(unfolded["rule"]["version"], 1)
        self.assertIn("formule", unfolded["rule"]["body"])

    def test_unfold_reaches_every_source_event_and_its_origin_file(self):
        """Chaine complete jusqu'au fichier/evenement d'origine."""
        unfolded = explain.unfold(self.conn, "ca")

        self.assertEqual(len(unfolded["events"]), 2)
        for event in unfolded["events"]:
            self.assertEqual(event["type"], "PERCEPTION.OrderObserved")
            self.assertEqual(event["source"], "inbox/test")  # le fichier d'origine
            self.assertIn("confidence", event)
            self.assertIn("montant", event["payload"]["record"])

    def test_unfold_carries_the_propagated_confidence(self):
        unfolded = explain.unfold(self.conn, "ca")
        self.assertEqual(unfolded["confidence"]["nature"], "fait")
        self.assertEqual(unfolded["confidence"]["score"], 1.0)
        self.assertEqual(unfolded["hypotheses"], [])

    def test_unfold_exposes_hypotheses_when_confidence_degrades(self):
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-3", "montant": "10,00"}}, 3,
                   nature="estimé", score=0.4)
        kpi_catalog.compute(self.conn, "ca")

        unfolded = explain.unfold(self.conn, "ca")
        self.assertEqual(unfolded["confidence"]["nature"], "estimé")
        self.assertTrue(any("estimé" in h for h in unfolded["hypotheses"]))

    def test_unfold_of_an_empty_kpi_says_so_never_invents(self):
        unfolded = explain.unfold(self.conn, "tresorerie")
        self.assertIsNone(unfolded["kpi"]["value"])
        self.assertTrue(any("incalculable" in h for h in unfolded["hypotheses"]))
        self.assertEqual(unfolded["events"], [])


if __name__ == "__main__":
    unittest.main()
