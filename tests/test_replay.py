"""Tests T-M01-2 : lecture ordonnee & rejeu (event_store.read).

Prouve le critere du backlog : "rejeu d'un intervalle reproduit la meme
sequence" - ordre deterministe, filtrage par valid-time (since/until) et
par decision-time, stabilite face aux ecritures posterieures.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from core.envelope import make_envelope  # noqa: E402


def _valid_envelope(**overrides):
    kwargs = dict(
        id="EVT:KAMEHA:000001",
        type_="PERCEPTION.InvoiceReceived",
        label="Facture Foodex #123",
        source="inbox/facture_foodex_123.pdf",
        author="agent:perception",
        valid_from="2028-04-01T00:00:00Z",
        ts_record="2028-04-01T00:00:00Z",
        nature="fait",
        score=1.0,
        owner="kameha",
        visibility="interne",
        authority=2,
    )
    kwargs.update(overrides)
    return make_envelope(**kwargs)


class ReplayTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_replay.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _append(self, event_id, valid_from, ts_record, **payload):
        envelope = _valid_envelope(id=event_id, valid_from=valid_from, ts_record=ts_record)
        event_store.append(self.conn, envelope, payload=payload)


class OrderingTests(ReplayTestCase):
    def test_read_orders_by_valid_time_regardless_of_insertion_order(self):
        # Insertion volontairement desordonnee.
        self._append("EVT:KAMEHA:C", "2028-04-03T00:00:00Z", "2028-04-03T00:00:00Z", label="C")
        self._append("EVT:KAMEHA:A", "2028-04-01T00:00:00Z", "2028-04-01T00:00:00Z", label="A")
        self._append("EVT:KAMEHA:B", "2028-04-02T00:00:00Z", "2028-04-02T00:00:00Z", label="B")

        events = event_store.read(self.conn)

        self.assertEqual([e["event_id"] for e in events], [
            "EVT:KAMEHA:A", "EVT:KAMEHA:B", "EVT:KAMEHA:C",
        ])

    def test_read_with_no_filters_returns_everything(self):
        for i in range(1, 4):
            self._append(f"EVT:KAMEHA:{i:06d}", f"2028-04-0{i}T00:00:00Z", f"2028-04-0{i}T00:00:00Z")

        events = event_store.read(self.conn)
        self.assertEqual(len(events), 3)

    def test_read_reconstructs_envelope_and_payload(self):
        envelope = _valid_envelope()
        event_store.append(self.conn, envelope, payload={"montant": 42.0, "devise": "EUR"})

        events = event_store.read(self.conn)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["envelope"], envelope)
        self.assertEqual(events[0]["payload"], {"montant": 42.0, "devise": "EUR"})


class ValidTimeFilterTests(ReplayTestCase):
    def setUp(self):
        super().setUp()
        self._append("EVT:KAMEHA:JAN", "2028-01-15T00:00:00Z", "2028-01-15T00:00:00Z")
        self._append("EVT:KAMEHA:FEB", "2028-02-15T00:00:00Z", "2028-02-15T00:00:00Z")
        self._append("EVT:KAMEHA:MAR", "2028-03-15T00:00:00Z", "2028-03-15T00:00:00Z")

    def test_since_excludes_earlier_events(self):
        events = event_store.read(self.conn, since="2028-02-01T00:00:00Z")
        self.assertEqual([e["event_id"] for e in events], ["EVT:KAMEHA:FEB", "EVT:KAMEHA:MAR"])

    def test_until_excludes_later_events(self):
        events = event_store.read(self.conn, until="2028-03-01T00:00:00Z")
        self.assertEqual([e["event_id"] for e in events], ["EVT:KAMEHA:JAN", "EVT:KAMEHA:FEB"])

    def test_until_is_exclusive(self):
        events = event_store.read(self.conn, until="2028-02-15T00:00:00Z")
        self.assertEqual([e["event_id"] for e in events], ["EVT:KAMEHA:JAN"])

    def test_since_and_until_together_select_a_window(self):
        events = event_store.read(
            self.conn, since="2028-02-01T00:00:00Z", until="2028-03-01T00:00:00Z"
        )
        self.assertEqual([e["event_id"] for e in events], ["EVT:KAMEHA:FEB"])


class DecisionTimeFilterTests(ReplayTestCase):
    def setUp(self):
        super().setUp()
        # Un fait de janvier appris en janvier (fait au fil de l'eau).
        self._append("EVT:KAMEHA:KNOWN-EARLY", "2028-01-10T00:00:00Z", "2028-01-10T00:00:00Z")
        # Un fait de janvier appris seulement en mars (import tardif).
        self._append("EVT:KAMEHA:KNOWN-LATE", "2028-01-20T00:00:00Z", "2028-03-05T00:00:00Z")

    def test_decision_time_excludes_events_not_yet_known(self):
        events = event_store.read(self.conn, decision_time="2028-02-01T00:00:00Z")
        self.assertEqual([e["event_id"] for e in events], ["EVT:KAMEHA:KNOWN-EARLY"])

    def test_decision_time_includes_events_known_by_then(self):
        events = event_store.read(self.conn, decision_time="2028-03-05T00:00:00Z")
        self.assertEqual(
            {e["event_id"] for e in events},
            {"EVT:KAMEHA:KNOWN-EARLY", "EVT:KAMEHA:KNOWN-LATE"},
        )

    def test_no_decision_time_means_everything_known_today(self):
        events = event_store.read(self.conn)
        self.assertEqual(len(events), 2)


class DeterministicReplayTests(ReplayTestCase):
    def test_replaying_the_same_interval_twice_yields_the_same_sequence(self):
        for i in range(1, 6):
            self._append(
                f"EVT:KAMEHA:{i:06d}", f"2028-04-{i:02d}T00:00:00Z", f"2028-04-{i:02d}T00:00:00Z"
            )

        first_pass = event_store.read(
            self.conn, since="2028-04-01T00:00:00Z", until="2028-04-06T00:00:00Z"
        )
        second_pass = event_store.read(
            self.conn, since="2028-04-01T00:00:00Z", until="2028-04-06T00:00:00Z"
        )

        self.assertEqual(first_pass, second_pass)
        self.assertEqual(
            [e["event_id"] for e in first_pass],
            [f"EVT:KAMEHA:{i:06d}" for i in range(1, 6)],
        )

    def test_replay_of_an_interval_is_stable_after_later_appends(self):
        """Rejouer un intervalle produit toujours la meme sequence, meme si
        de nouveaux evenements sont ajoutes hors de cet intervalle entre
        les deux lectures (Backlog, critere T-M01-2)."""
        self._append("EVT:KAMEHA:A", "2028-04-01T00:00:00Z", "2028-04-01T00:00:00Z")
        self._append("EVT:KAMEHA:B", "2028-04-02T00:00:00Z", "2028-04-02T00:00:00Z")

        window = dict(since="2028-04-01T00:00:00Z", until="2028-04-03T00:00:00Z")
        before = event_store.read(self.conn, **window)

        # Nouveaux evenements : un avant et un apres la fenetre rejouee.
        self._append("EVT:KAMEHA:EARLIER", "2028-03-01T00:00:00Z", "2028-03-01T00:00:00Z")
        self._append("EVT:KAMEHA:LATER", "2028-05-01T00:00:00Z", "2028-05-01T00:00:00Z")

        after = event_store.read(self.conn, **window)

        self.assertEqual(before, after)
        self.assertEqual([e["event_id"] for e in after], ["EVT:KAMEHA:A", "EVT:KAMEHA:B"])

    def test_replay_reproduces_the_same_sequence_as_the_original_ingestion_order(self):
        """Rejeu = meme sequence que celle produite lors de l'ingestion
        d'origine, meme si les evenements sont rejoues (re-appendes) dans
        un ordre d'insertion different."""
        original_order = []
        for i in range(1, 4):
            event_id = f"EVT:KAMEHA:{i:06d}"
            self._append(event_id, f"2028-04-0{i}T00:00:00Z", f"2028-04-0{i}T00:00:00Z")
            original_order.append(event_id)

        replayed = event_store.read(self.conn)
        self.assertEqual([e["event_id"] for e in replayed], original_order)


if __name__ == "__main__":
    unittest.main()
