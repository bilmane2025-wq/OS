"""Tests T-M09-1 : projeteur evenement->graphe (graph_engine.apply).

Criteres backlog : un InvoiceReceived cree l'Objet Facture + Liens ;
rejeu -> meme graphe. DoD : reconstruction depuis zero = etat identique.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from core.envelope import make_envelope  # noqa: E402
from graph import graph_engine  # noqa: E402


def make_event(conn, type_, payload, event_num, nature="fait", score=1.0):
    ts = f"2028-04-{event_num:02d}T10:00:00Z"
    envelope = make_envelope(
        id=f"EVT:TEST:{event_num:06d}", type_=type_, label=f"{type_} {event_num}",
        source="inbox/test", author="agent:perception",
        valid_from=ts, ts_record=ts, nature=nature, score=score,
        owner="system", visibility="interne", authority=1,
    )
    event_store.append(conn, envelope, payload=payload)
    return event_store.read(conn)[-1]


class GraphTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_graph.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class InvoiceProjectionTests(GraphTestCase):
    def test_invoice_received_creates_facture_object_and_links(self):
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "542,80", "fournisseur": "Foodex",
                                       "compte": "604000"}}, 1)
        touched = graph_engine.apply(self.conn, event)

        types = {graph_engine.get_object(self.conn, oid)["type"] for oid in touched}
        self.assertEqual(types, {"Facture", "Acteur", "Compte"})

        invoice_id = touched[0]
        rels = {(n["rel"], n["object"]["type"])
                for n in graph_engine.neighbors(self.conn, invoice_id, "out")}
        self.assertEqual(rels, {("concerne", "Acteur"), ("impacte", "Compte")})

    def test_same_supplier_across_invoices_is_one_actor(self):
        for num in (1, 2):
            event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                               {"fields": {"montant": str(num), "fournisseur": "Foodex"}}, num)
            graph_engine.apply(self.conn, event)

        actors = self.conn.execute(
            "SELECT COUNT(*) FROM objects WHERE type = 'Acteur'").fetchone()[0]
        invoices = self.conn.execute(
            "SELECT COUNT(*) FROM objects WHERE type = 'Facture'").fetchone()[0]
        self.assertEqual(actors, 1)
        self.assertEqual(invoices, 2)

    def test_unknown_event_types_are_ignored_without_error(self):
        event = make_event(self.conn, "RULE.RuleCreated", {"name": "x"}, 1)
        self.assertEqual(graph_engine.apply(self.conn, event), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0], 0)


class ReplayAndRebuildTests(GraphTestCase):
    def _seed_events(self):
        events = []
        events.append(make_event(self.conn, "PERCEPTION.InvoiceReceived",
                                 {"fields": {"montant": "542,80", "fournisseur": "Foodex"}}, 1))
        events.append(make_event(self.conn, "PERCEPTION.StatementLine",
                                 {"record": {"date": "2028-04-02", "montant": "-542,80",
                                             "contrepartie": "Foodex", "libelle": "Paiement"}}, 2))
        events.append(make_event(self.conn, "PERCEPTION.OrderObserved",
                                 {"record": {"commande_id": "UB-1", "montant": "24,50",
                                             "plateforme": "Uber Eats"}}, 3))
        return events

    def test_reapplying_the_same_events_yields_the_same_graph(self):
        """Rejeu -> meme graphe (idempotence par row_hash)."""
        events = self._seed_events()
        graph_engine.apply_events(self.conn, events)
        first = graph_engine.snapshot_state(self.conn)

        graph_engine.apply_events(self.conn, events)  # rejeu
        second = graph_engine.snapshot_state(self.conn)

        self.assertEqual(first, second)

    def test_rebuild_from_zero_yields_an_identical_state(self):
        """DoD : reconstruction depuis zero = etat identique."""
        events = self._seed_events()
        graph_engine.apply_events(self.conn, events)
        incremental = graph_engine.snapshot_state(self.conn)
        self.assertGreater(len(incremental["objects"]), 0)

        graph_engine.rebuild(self.conn, event_store.read(self.conn))
        rebuilt = graph_engine.snapshot_state(self.conn)

        self.assertEqual(incremental, rebuilt)

    def test_object_ids_are_deterministic_across_databases(self):
        """Meme journal ailleurs = memes identifiants (rejeu fidele)."""
        self.assertEqual(
            graph_engine.object_id_for("Acteur", "acteur:foodex"),
            graph_engine.object_id_for("Acteur", "acteur:foodex"),
        )
        self.assertNotEqual(
            graph_engine.object_id_for("Acteur", "acteur:foodex"),
            graph_engine.object_id_for("Acteur", "acteur:metro"),
        )


if __name__ == "__main__":
    unittest.main()
