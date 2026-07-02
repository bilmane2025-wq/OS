"""Tests T-M14-1 : catalogue KPI (regles versionnees).

Criteres backlog : chaque KPI porte sa version de regle et sa confiance.
DoD : les 8 KPI calcules et traces.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from calc import derivation, kpi_catalog  # noqa: E402
from core import event_store, rules  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class KpiTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_kpi.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _seed_business_events(self):
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-1", "date": "2028-04-01",
                               "montant": "25,00", "commission": "5,00",
                               "plateforme": "Uber Eats"}}, 1)
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-2", "date": "2028-04-01",
                               "montant": "35,00", "commission": "7,00",
                               "plateforme": "Uber Eats"}}, 2)
        make_event(self.conn, "PERCEPTION.InvoiceReceived",
                   {"fields": {"montant": "18,00", "fournisseur": "Foodex"}}, 3)
        make_event(self.conn, "PERCEPTION.InvoiceReceived",
                   {"fields": {"montant": "6,00", "fournisseur": "Metro"}}, 4)
        make_event(self.conn, "PERCEPTION.StatementLine",
                   {"record": {"date": "2028-04-02", "montant": "60,00",
                               "contrepartie": "Uber Eats", "libelle": "versement"}}, 5)


class EightKpisTests(KpiTestCase):
    """DoD : les 8 KPI calcules et traces."""

    def test_all_eight_kpis_compute_and_are_persisted(self):
        self._seed_business_events()
        results = kpi_catalog.compute_all(self.conn)

        self.assertEqual(sorted(results), sorted([
            "ca", "marge", "food_cost", "ticket_moyen", "commandes_jour",
            "tresorerie", "commission", "dependance_fournisseur"]))

        for name in results:
            with self.subTest(kpi=name):
                stored = kpi_catalog.get(self.conn, name)
                self.assertIsNotNone(stored)
                self.assertIsNotNone(stored["rule_version"])  # version de regle tracee
                self.assertIn(stored["nature"],
                              ("fait", "mesuré", "estimé", "hypothèse", "projection"))
                self.assertIsNotNone(stored["score"])  # jamais de valeur nue

    def test_kpi_values_are_correct_on_a_known_dataset(self):
        self._seed_business_events()
        results = kpi_catalog.compute_all(self.conn)

        self.assertAlmostEqual(results["ca"]["value"], 60.0)
        self.assertAlmostEqual(results["marge"]["value"], 36.0)         # 60 - 24
        self.assertAlmostEqual(results["food_cost"]["value"], 0.4)      # 24 / 60
        self.assertAlmostEqual(results["ticket_moyen"]["value"], 30.0)  # 60 / 2
        self.assertAlmostEqual(results["commandes_jour"]["value"], 2.0) # 2 cmd / 1 jour
        self.assertAlmostEqual(results["tresorerie"]["value"], 60.0)
        self.assertAlmostEqual(results["commission"]["value"], 12.0)
        self.assertAlmostEqual(results["dependance_fournisseur"]["value"], 0.75)  # 18/24

    def test_each_kpi_carries_its_rule_version(self):
        """Critere backlog : chaque KPI porte sa version de regle."""
        self._seed_business_events()
        detail = kpi_catalog.compute(self.conn, "ca")
        self.assertEqual(detail["rule_name"], "kpi/ca")
        self.assertEqual(detail["rule_version"], 1)

        # Une v2 de la definition : le KPI porte desormais la v2.
        v1 = rules.get(self.conn, "kpi/ca", "2028-01-01T00:00:00Z")
        rules.add_version(self.conn, "kpi/ca", dict(v1["body"], note="v2"),
                          valid_from="2020-06-01T00:00:00Z", origin="manual")
        detail_v2 = kpi_catalog.compute(self.conn, "ca")
        self.assertEqual(detail_v2["rule_version"], 2)


class ConfidencePropagationTests(KpiTestCase):
    def test_kpi_from_estimated_source_is_labelled_estimation(self):
        """Critere M13 : un KPI issu d'estimation est etiquete estimation."""
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "X-1", "montant": "10,00"}}, 1)
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "X-2", "montant": "20,00"}}, 2,
                   nature="estimé", score=0.4)

        detail = kpi_catalog.compute(self.conn, "ca")
        self.assertEqual(detail["nature"], "estimé")
        self.assertEqual(detail["score"], 0.4)

    def test_kpi_without_any_source_is_none_hypothese_never_a_fake_zero(self):
        detail = kpi_catalog.compute(self.conn, "ca")
        self.assertIsNone(detail["value"])
        self.assertEqual(detail["nature"], "hypothèse")
        self.assertEqual(detail["score"], 0.0)


class IncrementalRecomputeTests(KpiTestCase):
    def test_a_statement_event_recomputes_only_tresorerie(self):
        """Integration M12+M14 : recalcul cible, jamais global."""
        self._seed_business_events()
        kpi_catalog.register_derivations()
        try:
            event = make_event(self.conn, "PERCEPTION.StatementLine",
                               {"record": {"date": "2028-04-03", "montant": "40,00",
                                           "contrepartie": "Deliveroo",
                                           "libelle": "versement"}}, 6)
            recomputed = derivation.on_event(self.conn, event)

            self.assertEqual(sorted(recomputed), ["kpi/tresorerie"])
            self.assertAlmostEqual(recomputed["kpi/tresorerie"]["value"], 100.0)
        finally:
            derivation._REGISTRY.clear()


if __name__ == "__main__":
    unittest.main()
