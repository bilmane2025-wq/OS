"""Tests T-M12-1 : DAG de derivations incremental.

Critere backlog : un evenement ne recalcule que l'impacte ; jamais tout.
DoD : test prouve le recalcul cible.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calc import derivation  # noqa: E402


class DerivationDagTests(unittest.TestCase):
    def setUp(self):
        # Registre isole pour le test : on sauvegarde puis restaure.
        self._saved = dict(derivation._REGISTRY)
        derivation._REGISTRY.clear()
        self.computed = []

        derivation.register(
            "kpi/tresorerie", ("PERCEPTION.StatementLine",),
            lambda conn: self.computed.append("kpi/tresorerie"))
        derivation.register(
            "kpi/ca", ("PERCEPTION.OrderObserved",),
            lambda conn: self.computed.append("kpi/ca"))
        derivation.register(
            "kpi/marge", ("PERCEPTION.OrderObserved", "PERCEPTION.InvoiceReceived"),
            lambda conn: self.computed.append("kpi/marge"))

    def tearDown(self):
        derivation._REGISTRY.clear()
        derivation._REGISTRY.update(self._saved)

    def test_an_event_recomputes_only_its_dependents(self):
        """Critere backlog exact : seul l'impacte est recalcule."""
        derivation.on_event(None, {"type": "PERCEPTION.StatementLine"})

        self.assertEqual(self.computed, ["kpi/tresorerie"])
        self.assertNotIn("kpi/ca", self.computed)
        self.assertNotIn("kpi/marge", self.computed)

    def test_an_event_can_impact_several_derivations_but_never_all(self):
        derivation.on_event(None, {"type": "PERCEPTION.OrderObserved"})

        self.assertEqual(sorted(self.computed), ["kpi/ca", "kpi/marge"])
        self.assertNotIn("kpi/tresorerie", self.computed)

    def test_an_event_without_dependents_triggers_nothing(self):
        result = derivation.on_event(None, {"type": "RULE.RuleCreated"})
        self.assertEqual(result, {})
        self.assertEqual(self.computed, [])

    def test_dependents_of_declares_the_dag_edges(self):
        self.assertEqual(derivation.dependents_of("PERCEPTION.OrderObserved"),
                         ["kpi/ca", "kpi/marge"])
        self.assertEqual(derivation.dependents_of("PERCEPTION.StatementLine"),
                         ["kpi/tresorerie"])

    def test_recompute_all_is_explicit_and_separate_from_the_reactive_flow(self):
        derivation.recompute_all(None)
        self.assertEqual(sorted(self.computed), ["kpi/ca", "kpi/marge", "kpi/tresorerie"])


if __name__ == "__main__":
    unittest.main()
