"""Tests T-M23-1 : recherche universelle locale (intent.search).

Critere backlog : « Foodex » remonte fournisseur + factures + liens.
DoD : test recherche + navigation.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from graph import graph_engine  # noqa: E402
from intent import search  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_search.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

        for num, amount in ((1, "542,80"), (2, "120,00")):
            event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                               {"fields": {"montant": amount, "fournisseur": "Foodex"}}, num)
            graph_engine.apply(self.conn, event)
        other = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "80,00", "fournisseur": "Metro"}}, 3)
        graph_engine.apply(self.conn, other)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_foodex_returns_the_supplier_and_its_invoices(self):
        """Critere backlog exact : « Foodex » remonte fournisseur +
        factures."""
        results = search.query(self.conn, "Foodex")

        types = [r["type"] for r in results]
        self.assertIn("Acteur", types)
        self.assertEqual(types.count("Facture"), 2)
        self.assertNotIn("Metro", [r["label"] for r in results])

    def test_results_are_typed_and_ranked_label_first(self):
        results = search.query(self.conn, "Foodex")
        # L'Acteur « Foodex » matche par son libelle -> pertinence 2, en tete.
        self.assertEqual(results[0]["type"], "Acteur")
        self.assertEqual(results[0]["score"], 2)

    def test_navigation_from_result_to_links(self):
        """DoD : navigation - du fournisseur trouve, on atteint ses
        factures par les Liens."""
        supplier = search.query(self.conn, "Foodex", filters={"type": "Acteur"})[0]
        neighbors = search.related(self.conn, supplier["object_id"])

        invoice_neighbors = [n for n in neighbors if n["object"]["type"] == "Facture"]
        self.assertEqual(len(invoice_neighbors), 2)
        self.assertTrue(all(n["rel"] == "concerne" for n in invoice_neighbors))

    def test_from_result_to_proof(self):
        """Du resultat a la preuve : l'evenement createur et son fichier
        d'origine."""
        invoice = search.query(self.conn, "Foodex", filters={"type": "Facture"})[0]
        proof = search.to_proof(self.conn, invoice["object_id"])

        self.assertIsNotNone(proof["event"])
        self.assertEqual(proof["event"]["type"], "PERCEPTION.InvoiceReceived")
        self.assertEqual(proof["origin"], "inbox/test")

    def test_type_filter_restricts_results(self):
        results = search.query(self.conn, "Foodex", filters={"type": "Facture"})
        self.assertTrue(all(r["type"] == "Facture" for r in results))

    def test_empty_or_blank_query_returns_nothing(self):
        self.assertEqual(search.query(self.conn, ""), [])
        self.assertEqual(search.query(self.conn, "   "), [])

    def test_case_insensitive(self):
        self.assertEqual(len(search.query(self.conn, "fOoDeX")),
                         len(search.query(self.conn, "Foodex")))


if __name__ == "__main__":
    unittest.main()
