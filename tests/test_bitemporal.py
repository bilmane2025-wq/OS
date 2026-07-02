"""Tests T-M10-1 : requete bi-temporelle (bitemporal.state_as_of).

Critere backlog : « etat connu au 12/06 » != « etat vrai au 03/06 » ; les
deux exacts. DoD : test des deux horloges.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from core.envelope import make_envelope  # noqa: E402
from graph import bitemporal, graph_engine  # noqa: E402


def append_event(conn, num, valid_from, ts_record, supplier):
    envelope = make_envelope(
        id=f"EVT:TEST:{num:06d}", type_="PERCEPTION.InvoiceReceived",
        label=f"Facture {supplier}", source="inbox/test", author="agent:perception",
        valid_from=valid_from, ts_record=ts_record, nature="fait", score=1.0,
        owner="system", visibility="interne", authority=1,
    )
    event_store.append(conn, envelope, payload={"fields": {"fournisseur": supplier,
                                                           "montant": str(num)}})


class BitemporalTests(unittest.TestCase):
    """Scenario des deux horloges :
    - Facture Foodex : vraie au 01/06, connue le 01/06 (au fil de l'eau).
    - Facture Metro : vraie au 03/06, mais connue seulement le 10/06
      (import tardif)."""

    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_bitemporal.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

        append_event(self.conn, 1, "2028-06-01T00:00:00Z", "2028-06-01T00:00:00Z", "Foodex")
        append_event(self.conn, 2, "2028-06-03T00:00:00Z", "2028-06-10T00:00:00Z", "Metro")

        self.foodex_id = graph_engine.object_id_for("Acteur", "acteur:foodex")
        self.metro_id = graph_engine.object_id_for("Acteur", "acteur:metro")

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_state_known_on_june_5_ignores_the_late_import(self):
        """Au 05/06, le systeme ne connaissait pas encore la facture Metro
        (enregistree le 10/06) - meme si elle etait deja vraie au 03/06."""
        state = bitemporal.state_as_of(
            self.conn, valid_date="2028-06-05T00:00:00Z",
            decision_date="2028-06-05T00:00:00Z")

        self.assertIn(self.foodex_id, state["objects"])
        self.assertNotIn(self.metro_id, state["objects"])

    def test_state_true_on_june_5_seen_from_june_12_includes_it(self):
        """Au 12/06, on sait que la facture Metro etait vraie des le
        03/06 : l'etat *vrai* au 05/06, vu d'aujourd'hui, l'inclut."""
        state = bitemporal.state_as_of(
            self.conn, valid_date="2028-06-05T00:00:00Z",
            decision_date="2028-06-12T00:00:00Z")

        self.assertIn(self.foodex_id, state["objects"])
        self.assertIn(self.metro_id, state["objects"])

    def test_the_two_clocks_give_different_yet_both_exact_states(self):
        """Critere backlog : les deux etats different, et chacun est exact
        pour sa question."""
        known_then = bitemporal.state_as_of(
            self.conn, "2028-06-05T00:00:00Z", "2028-06-05T00:00:00Z")
        known_now = bitemporal.state_as_of(
            self.conn, "2028-06-05T00:00:00Z", "2028-06-12T00:00:00Z")

        self.assertNotEqual(set(known_then["objects"]), set(known_now["objects"]))
        self.assertEqual(known_then["event_count"], 1)
        self.assertEqual(known_now["event_count"], 2)

    def test_valid_date_excludes_facts_from_the_future(self):
        """La borne valid-time exclut ce qui n'etait pas encore vrai."""
        state = bitemporal.state_as_of(
            self.conn, valid_date="2028-06-02T00:00:00Z", decision_date=None)
        self.assertIn(self.foodex_id, state["objects"])
        self.assertNotIn(self.metro_id, state["objects"])

    def test_query_at_past_date_never_mutates_the_current_projection(self):
        """La requete au passe se fait dans une base jetable : la
        projection courante n'est jamais touchee."""
        graph_engine.apply_events(self.conn, event_store.read(self.conn))
        before = graph_engine.snapshot_state(self.conn)

        bitemporal.state_as_of(self.conn, "2028-06-02T00:00:00Z", "2028-06-02T00:00:00Z")

        self.assertEqual(graph_engine.snapshot_state(self.conn), before)


if __name__ == "__main__":
    unittest.main()
