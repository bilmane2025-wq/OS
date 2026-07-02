"""Tests T-M09-2 : traversee bidirectionnelle (graph_engine.neighbors).

Critere backlog : d'une facture on atteint le fournisseur et
inversement. DoD : test aller-retour.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from graph import graph_engine  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class TraverseTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_traverse.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "542,80", "fournisseur": "Foodex"}}, 1)
        touched = graph_engine.apply(self.conn, event)
        self.invoice_id = touched[0]
        self.supplier_id = graph_engine.object_id_for("Acteur", "acteur:foodex")

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_from_invoice_to_supplier(self):
        out = graph_engine.neighbors(self.conn, self.invoice_id, "out")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rel"], "concerne")
        self.assertEqual(out[0]["object"]["object_id"], self.supplier_id)
        self.assertEqual(out[0]["object"]["label"], "Foodex")

    def test_from_supplier_back_to_invoice(self):
        incoming = graph_engine.neighbors(self.conn, self.supplier_id, "in")
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]["rel"], "concerne")
        self.assertEqual(incoming[0]["object"]["object_id"], self.invoice_id)
        self.assertEqual(incoming[0]["object"]["type"], "Facture")

    def test_round_trip_lands_back_on_the_same_object(self):
        """DoD : aller-retour."""
        to_supplier = graph_engine.neighbors(self.conn, self.invoice_id, "out")[0]
        back = graph_engine.neighbors(
            self.conn, to_supplier["object"]["object_id"], "in")[0]
        self.assertEqual(back["object"]["object_id"], self.invoice_id)

    def test_both_direction_returns_out_and_in(self):
        both = graph_engine.neighbors(self.conn, self.supplier_id, "both")
        directions = {n["direction"] for n in both}
        self.assertEqual(directions, {"in"})  # le fournisseur n'a pas de lien sortant
        both_invoice = graph_engine.neighbors(self.conn, self.invoice_id, "both")
        self.assertEqual({n["direction"] for n in both_invoice}, {"out"})


if __name__ == "__main__":
    unittest.main()
