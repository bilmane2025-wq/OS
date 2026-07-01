"""Tests T-M03-1 : identifiants immortels (core.identity.new_id).

Prouve les criteres du backlog : deux appels ne collisionnent jamais ;
format respecte. DoD : test d'unicite sur 10 000 id.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import identity  # noqa: E402


class IdentityTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_identity.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class FormatTests(IdentityTestCase):
    def test_format_is_type_entity_sequence(self):
        result = identity.new_id(self.conn, "OBJ", "KAMEHA")
        self.assertEqual(result, "OBJ:KAMEHA:000001")

    def test_generated_id_is_recognized_as_valid(self):
        result = identity.new_id(self.conn, "EVT", "KAMEHA")
        self.assertTrue(identity.is_valid_id(result))

    def test_is_valid_id_rejects_malformed_strings(self):
        for bogus in ("", "OBJ", "OBJ:KAMEHA", "OBJ:KAMEHA:abc", "OBJ:KAMEHA:", None, 123, "OBJ:KAMEHA:1:extra"):
            with self.subTest(value=bogus):
                self.assertFalse(identity.is_valid_id(bogus))

    def test_type_cannot_contain_colon(self):
        with self.assertRaises(identity.IdentityError):
            identity.new_id(self.conn, "OBJ:X", "KAMEHA")

    def test_entity_cannot_contain_colon(self):
        with self.assertRaises(identity.IdentityError):
            identity.new_id(self.conn, "OBJ", "KAMEHA:X")

    def test_type_and_entity_must_be_non_empty(self):
        for bogus in ("", "   ", None, 123):
            with self.subTest(value=bogus):
                with self.assertRaises(identity.IdentityError):
                    identity.new_id(self.conn, bogus, "KAMEHA")
                with self.assertRaises(identity.IdentityError):
                    identity.new_id(self.conn, "OBJ", bogus)


class SequenceTests(IdentityTestCase):
    def test_first_id_starts_at_one(self):
        result = identity.new_id(self.conn, "OBJ", "KAMEHA")
        self.assertEqual(result, "OBJ:KAMEHA:000001")

    def test_sequence_increments_monotonically(self):
        ids = [identity.new_id(self.conn, "OBJ", "KAMEHA") for _ in range(5)]
        self.assertEqual(ids, [
            "OBJ:KAMEHA:000001", "OBJ:KAMEHA:000002", "OBJ:KAMEHA:000003",
            "OBJ:KAMEHA:000004", "OBJ:KAMEHA:000005",
        ])

    def test_sequences_are_independent_per_type(self):
        obj_id = identity.new_id(self.conn, "OBJ", "KAMEHA")
        evt_id = identity.new_id(self.conn, "EVT", "KAMEHA")
        self.assertEqual(obj_id, "OBJ:KAMEHA:000001")
        self.assertEqual(evt_id, "EVT:KAMEHA:000001")

    def test_sequences_are_independent_per_entity(self):
        kameha_id = identity.new_id(self.conn, "OBJ", "KAMEHA")
        crousty_id = identity.new_id(self.conn, "OBJ", "CROUSTY")
        self.assertEqual(kameha_id, "OBJ:KAMEHA:000001")
        self.assertEqual(crousty_id, "OBJ:CROUSTY:000001")

    def test_interleaved_calls_do_not_disturb_independent_sequences(self):
        first_obj = identity.new_id(self.conn, "OBJ", "KAMEHA")
        first_evt = identity.new_id(self.conn, "EVT", "KAMEHA")
        second_obj = identity.new_id(self.conn, "OBJ", "KAMEHA")
        second_evt = identity.new_id(self.conn, "EVT", "KAMEHA")

        self.assertEqual(first_obj, "OBJ:KAMEHA:000001")
        self.assertEqual(second_obj, "OBJ:KAMEHA:000002")
        self.assertEqual(first_evt, "EVT:KAMEHA:000001")
        self.assertEqual(second_evt, "EVT:KAMEHA:000002")


class PersistenceTests(IdentityTestCase):
    def test_sequence_is_never_reused_across_reconnection(self):
        """L'id est immortel : le compteur survit a un redemarrage complet
        du systeme (connexion fermee puis rouverte sur le meme fichier)."""
        identity.new_id(self.conn, "OBJ", "KAMEHA")
        identity.new_id(self.conn, "OBJ", "KAMEHA")
        self.conn.close()

        reconnected = sqlite3.connect(self.db_path)
        try:
            third = identity.new_id(reconnected, "OBJ", "KAMEHA")
        finally:
            reconnected.close()

        self.assertEqual(third, "OBJ:KAMEHA:000003")


class UniquenessAtScaleTests(IdentityTestCase):
    def test_ten_thousand_ids_never_collide(self):
        """DoD T-M03-1 : test d'unicite sur 10 000 id."""
        ids = [identity.new_id(self.conn, "OBJ", "KAMEHA") for _ in range(10_000)]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "OBJ:KAMEHA:000001")
        self.assertEqual(ids[-1], "OBJ:KAMEHA:010000")

        sequences = [int(generated_id.split(":")[-1]) for generated_id in ids]
        self.assertEqual(sequences, list(range(1, 10_001)))

    def test_ten_thousand_ids_across_mixed_types_and_entities_never_collide(self):
        combos = [("OBJ", "KAMEHA"), ("EVT", "KAMEHA"), ("OBJ", "CROUSTY"), ("LNK", "KAMEHA")]
        ids = []
        for i in range(10_000):
            type_, entity = combos[i % len(combos)]
            ids.append(identity.new_id(self.conn, type_, entity))

        self.assertEqual(len(ids), len(set(ids)))
        for generated_id in ids:
            self.assertTrue(identity.is_valid_id(generated_id))


if __name__ == "__main__":
    unittest.main()
