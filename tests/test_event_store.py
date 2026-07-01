"""Tests T-M01-1 : journal d'evenements append-only (event_store.append).

Prouve les deux garanties non-negociables du journal (Backlog, T-M01-1) :
immutabilite (UPDATE/DELETE refuses) et idempotence (un doublon est ignore,
jamais reinsere).
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from core.envelope import EnvelopeError, make_envelope  # noqa: E402


def _valid_envelope(**overrides):
    kwargs = dict(
        id="EVT:KAMEHA:000001",
        type_="PERCEPTION.InvoiceReceived",
        label="Facture Foodex #123",
        source="inbox/facture_foodex_123.pdf",
        author="agent:perception",
        valid_from="2028-04-01T00:00:00Z",
        ts_record="2028-04-02T09:30:00Z",
        nature="fait",
        score=1.0,
        owner="kameha",
        visibility="interne",
        authority=2,
    )
    kwargs.update(overrides)
    return make_envelope(**kwargs)


class EventStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_event_store.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _row_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


class AppendTests(EventStoreTestCase):
    def test_append_writes_the_event(self):
        envelope = _valid_envelope()
        status, event_id = event_store.append(
            self.conn, envelope, payload={"montant": 42.0, "devise": "EUR"}
        )

        self.assertEqual(status, event_store.APPENDED)
        self.assertEqual(event_id, "EVT:KAMEHA:000001")
        self.assertEqual(self._row_count(), 1)

        row = self.conn.execute(
            "SELECT event_id, ts_record, valid_from, valid_to, type, source, author, hash "
            "FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        (db_event_id, ts_record, valid_from, valid_to, type_, source, author, db_hash) = row
        self.assertEqual(db_event_id, "EVT:KAMEHA:000001")
        self.assertEqual(ts_record, "2028-04-02T09:30:00Z")
        self.assertEqual(valid_from, "2028-04-01T00:00:00Z")
        self.assertIsNone(valid_to)
        self.assertEqual(type_, "PERCEPTION.InvoiceReceived")
        self.assertEqual(source, "inbox/facture_foodex_123.pdf")
        self.assertEqual(author, "agent:perception")
        self.assertTrue(db_hash)

    def test_payload_and_envelope_round_trip_through_payload_json(self):
        envelope = _valid_envelope()
        payload = {"montant": 42.0, "devise": "EUR"}
        event_store.append(self.conn, envelope, payload=payload)

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",)
        ).fetchone()
        stored = json.loads(payload_json)
        self.assertEqual(stored["payload"], payload)
        self.assertEqual(stored["envelope"], envelope)

    def test_causation_id_defaults_to_envelope_event_id(self):
        envelope = _valid_envelope(event_id="EVT:KAMEHA:000000")
        event_store.append(self.conn, envelope, payload={})

        (causation_id,) = self.conn.execute(
            "SELECT causation_id FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",)
        ).fetchone()
        self.assertEqual(causation_id, "EVT:KAMEHA:000000")

    def test_explicit_causation_id_is_respected(self):
        envelope = _valid_envelope(event_id="EVT:KAMEHA:000000")
        event_store.append(self.conn, envelope, payload={}, causation_id="EVT:KAMEHA:OVERRIDE")

        (causation_id,) = self.conn.execute(
            "SELECT causation_id FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",)
        ).fetchone()
        self.assertEqual(causation_id, "EVT:KAMEHA:OVERRIDE")

    def test_correlation_id_and_rule_version_ref_are_persisted(self):
        envelope = _valid_envelope()
        event_store.append(
            self.conn,
            envelope,
            payload={},
            correlation_id="THREAD:facture-foodex-123",
            rule_version_ref="categorization/foodex@3",
        )

        row = self.conn.execute(
            "SELECT correlation_id, rule_version_ref FROM events WHERE event_id = ?",
            ("EVT:KAMEHA:000001",),
        ).fetchone()
        self.assertEqual(row[0], "THREAD:facture-foodex-123")
        self.assertEqual(row[1], "categorization/foodex@3")

    def test_append_rejects_incomplete_envelope(self):
        envelope = _valid_envelope()
        del envelope["provenance"]

        with self.assertRaises(EnvelopeError):
            event_store.append(self.conn, envelope, payload={})

        self.assertEqual(self._row_count(), 0)


class IdempotenceTests(EventStoreTestCase):
    def test_appending_the_exact_same_call_twice_is_a_duplicate(self):
        envelope = _valid_envelope()
        payload = {"montant": 42.0}

        first_status, first_id = event_store.append(self.conn, envelope, payload=payload)
        second_status, second_id = event_store.append(self.conn, envelope, payload=payload)

        self.assertEqual(first_status, event_store.APPENDED)
        self.assertEqual(second_status, event_store.DUPLICATE)
        self.assertEqual(first_id, second_id)
        self.assertEqual(self._row_count(), 1)

    def test_duplicate_content_with_a_new_id_is_still_detected(self):
        """Une re-tentative avec un id different reste un doublon de contenu."""
        payload = {"montant": 42.0}
        first_envelope = _valid_envelope(id="EVT:KAMEHA:000001")
        retry_envelope = _valid_envelope(id="EVT:KAMEHA:000002")

        _, first_id = event_store.append(self.conn, first_envelope, payload=payload)
        status, returned_id = event_store.append(self.conn, retry_envelope, payload=payload)

        self.assertEqual(status, event_store.DUPLICATE)
        self.assertEqual(returned_id, first_id)
        self.assertEqual(self._row_count(), 1)

    def test_different_payload_is_not_a_duplicate(self):
        envelope_a = _valid_envelope(id="EVT:KAMEHA:000001")
        envelope_b = _valid_envelope(id="EVT:KAMEHA:000002")

        event_store.append(self.conn, envelope_a, payload={"montant": 42.0})
        status, _ = event_store.append(self.conn, envelope_b, payload={"montant": 43.0})

        self.assertEqual(status, event_store.APPENDED)
        self.assertEqual(self._row_count(), 2)

    def test_replaying_an_import_creates_no_new_duplicate(self):
        """Rejouer plusieurs fois le meme lot d'evenements = 0 nouveau doublon."""
        envelopes_and_payloads = [
            (_valid_envelope(id=f"EVT:KAMEHA:{i:06d}"), {"ligne": i}) for i in range(1, 6)
        ]

        for envelope, payload in envelopes_and_payloads:
            event_store.append(self.conn, envelope, payload=payload)
        self.assertEqual(self._row_count(), 5)

        # Rejeu : memes evenements, nouveaux id (simulateur d'une reprise apres coupure).
        for index, (_, payload) in enumerate(envelopes_and_payloads, start=1):
            replay_envelope = _valid_envelope(id=f"EVT:KAMEHA:REPLAY-{index:06d}")
            status, _ = event_store.append(self.conn, replay_envelope, payload=payload)
            self.assertEqual(status, event_store.DUPLICATE)

        self.assertEqual(self._row_count(), 5)


class ImmutabilityTests(EventStoreTestCase):
    _COLUMNS = (
        "event_id", "ts_record", "valid_from", "valid_to", "type", "payload_json",
        "causation_id", "correlation_id", "rule_version_ref", "source", "author", "hash",
    )

    def setUp(self):
        super().setUp()
        envelope = _valid_envelope()
        event_store.append(self.conn, envelope, payload={"montant": 42.0})

    def _full_row(self, event_id="EVT:KAMEHA:000001"):
        columns = ", ".join(self._COLUMNS)
        row = self.conn.execute(
            f"SELECT {columns} FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return dict(zip(self._COLUMNS, row))

    def test_update_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE events SET type = ? WHERE event_id = ?",
                ("PERCEPTION.Tampered", "EVT:KAMEHA:000001"),
            )

        (type_,) = self.conn.execute(
            "SELECT type FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",)
        ).fetchone()
        self.assertEqual(type_, "PERCEPTION.InvoiceReceived")

    def test_delete_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",))

        self.assertEqual(self._row_count(), 1)

    def test_update_of_hash_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE events SET hash = ? WHERE event_id = ?",
                ("0" * 64, "EVT:KAMEHA:000001"),
            )

    def test_row_is_fully_unchanged_after_update_and_delete_attempts(self):
        """Verifie l'integralite de la ligne (pas seulement un champ)."""
        before = self._full_row()

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE events SET type = ?, source = ?, author = ?, payload_json = ? "
                "WHERE event_id = ?",
                ("PERCEPTION.Tampered", "attacker", "attacker", "{}", "EVT:KAMEHA:000001"),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",))

        after = self._full_row()
        self.assertEqual(before, after)
        self.assertEqual(self._row_count(), 1)

    def test_append_still_works_after_failed_update_and_delete_attempts(self):
        """La garde d'immutabilite ne doit pas casser les ecritures legitimes suivantes."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE events SET type = ? WHERE event_id = ?",
                ("PERCEPTION.Tampered", "EVT:KAMEHA:000001"),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM events WHERE event_id = ?", ("EVT:KAMEHA:000001",))

        new_envelope = _valid_envelope(id="EVT:KAMEHA:000002")
        status, event_id = event_store.append(self.conn, new_envelope, payload={"montant": 7.0})

        self.assertEqual(status, event_store.APPENDED)
        self.assertEqual(event_id, "EVT:KAMEHA:000002")
        self.assertEqual(self._row_count(), 2)

        original = self._full_row("EVT:KAMEHA:000001")
        self.assertEqual(original["type"], "PERCEPTION.InvoiceReceived")


if __name__ == "__main__":
    unittest.main()
