"""Tests T-M22-1 : resolveur d'intentions deterministe.

Criteres backlog : une intention connue -> reponse avec confiance +
preuve ; intention inconnue -> « je ne sais pas repondre a ca pour
l'instant », jamais d'invention ; zero appel externe. DoD : >= 8
intentions cadrees testees.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store, rules  # noqa: E402
from graph import graph_engine  # noqa: E402
from governance import audit  # noqa: E402
from intent import conversation  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class ConversationTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_conversation.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)

        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-1", "date": "2028-04-01",
                               "montant": "25,00", "commission": "5,00"}}, 1)
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-2", "date": "2028-04-01",
                               "montant": "35,00", "commission": "7,00"}}, 2)
        invoice = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                             {"fields": {"montant": "24,00", "fournisseur": "Foodex"}}, 3)
        graph_engine.apply(self.conn, invoice)
        make_event(self.conn, "PERCEPTION.StatementLine",
                   {"record": {"date": "2028-04-02", "montant": "60,00",
                               "contrepartie": "Uber Eats", "libelle": "versement"}}, 4)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class EightFramedIntentsTests(ConversationTestCase):
    """DoD : >= 8 intentions cadrees, chacune avec confiance + preuve +
    action."""

    CASES = [
        ("Combien gagné hier ?", "ca_periode", "60.00 EUR"),
        ("Quelle est ma trésorerie ?", "tresorerie", "60.00 EUR"),
        ("Quelle est ma marge ?", "marge", "36.00 EUR"),
        ("Quel est mon food cost ?", "food_cost", "40.0 %"),
        ("Quel est le ticket moyen ?", "ticket_moyen", "30.00 EUR"),
        ("Combien de commission ce mois ?", "commission", "12.00 EUR"),
        ("Quel fournisseur coûte le plus ?", "fournisseur_principal", "100.0 %"),
        ("Que dois-je faire ?", "que_faire", None),
        ("Où est Foodex ?", "recherche", None),
    ]

    def test_at_least_eight_intents_are_declared(self):
        self.assertGreaterEqual(len(conversation.load_intents()), 8)

    def test_each_framed_intent_answers_with_confidence_proof_and_action(self):
        for question, expected_intent, expected_fragment in self.CASES:
            with self.subTest(question=question):
                response = conversation.ask(self.conn, question)

                self.assertTrue(response["known"])
                self.assertEqual(response["intent"], expected_intent)
                self.assertIsNotNone(response["confidence"])   # confiance toujours presente
                self.assertIsNotNone(response["proof"])        # preuve toujours presente
                self.assertTrue(response["action"])            # finit par une action
                if expected_fragment:
                    self.assertIn(expected_fragment, response["answer"])

    def test_kpi_answer_proof_reaches_the_source_events(self):
        response = conversation.ask(self.conn, "Combien gagné hier ?")
        self.assertEqual(len(response["proof"]["events"]), 2)
        self.assertEqual(response["proof"]["sources"], ["inbox/test"])
        self.assertIn("kpi/ca@1", response["proof"]["rule"])

    def test_answer_distinguishes_fact_from_estimate(self):
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-3", "montant": "10,00"}}, 5,
                   nature="estimé", score=0.4)
        response = conversation.ask(self.conn, "Combien gagné hier ?")
        self.assertIn("estimé", response["answer"])
        self.assertEqual(response["confidence"]["nature"], "estimé")

    def test_que_faire_surfaces_the_top_anomaly_as_action(self):
        # Une vente supplementaire jamais encaissee -> ecart 100 vs 160,
        # bien au-dela du seuil de 5 % -> anomalie de reconciliation.
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "UB-9", "montant": "100,00"}}, 6)
        audit.reconcile_collections_vs_sales(self.conn)  # ecart -> anomalie

        response = conversation.ask(self.conn, "Que dois-je faire ?")
        self.assertIn("anomalie", response["answer"])
        self.assertTrue(response["proof"]["anomalies"])

    def test_recherche_intent_finds_the_supplier(self):
        response = conversation.ask(self.conn, "Où est Foodex ?")
        self.assertTrue(response["proof"]["results"])
        self.assertIn("Foodex", response["answer"])


class UnknownIntentTests(ConversationTestCase):
    def test_unknown_question_gets_the_exact_refusal_never_an_invention(self):
        """Critere backlog : « je ne sais pas repondre a ca pour
        l'instant », jamais d'invention."""
        response = conversation.ask(self.conn, "Quelle est la météo demain à Bruxelles ?")

        self.assertFalse(response["known"])
        self.assertEqual(response["answer"], conversation.UNKNOWN_ANSWER)
        self.assertIsNone(response["confidence"])
        self.assertIsNone(response["proof"])

    def test_empty_question_is_unknown(self):
        response = conversation.ask(self.conn, "")
        self.assertFalse(response["known"])

    def test_resolver_is_purely_local_no_network_modules_imported(self):
        """Zero appel externe : le module conversation n'importe aucun
        module reseau."""
        import intent.conversation as convo
        source = open(convo.__file__, encoding="utf-8").read()
        for forbidden in ("urllib", "http.client", "requests", "socket"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
