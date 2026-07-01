"""Tests T-M00-2 : enveloppe universelle (make_envelope / validate_envelope).

Couvre : construction complete par defaut, integration des 6 facettes
(identite, provenance, temporalite bi-temporelle, confiance, permissions,
cycle de vie), rejet de toute enveloppe incomplete, et rejet de toute
nature de confiance hors des 5 valeurs autorisees.
"""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.envelope import (  # noqa: E402
    NATURES,
    EnvelopeError,
    make_envelope,
    validate_envelope,
)


def _valid_kwargs(**overrides):
    kwargs = dict(
        id="OBJ:KAMEHA:000001",
        type_="Facture",
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
    return kwargs


class MakeEnvelopeTests(unittest.TestCase):
    def test_builds_complete_envelope_with_defaults(self):
        envelope = make_envelope(**_valid_kwargs())

        self.assertEqual(envelope["id"], "OBJ:KAMEHA:000001")
        self.assertEqual(envelope["type"], "Facture")
        self.assertEqual(envelope["label"], "Facture Foodex #123")
        self.assertEqual(
            envelope["provenance"],
            {
                "source": "inbox/facture_foodex_123.pdf",
                "origin_ref": None,
                "author": "agent:perception",
                "event_id": None,
            },
        )
        self.assertEqual(envelope["temporal"]["valid_from"], "2028-04-01T00:00:00Z")
        self.assertIsNone(envelope["temporal"]["valid_to"])
        self.assertEqual(envelope["temporal"]["version"], 1)
        self.assertEqual(
            envelope["confidence"], {"nature": "fait", "score": 1.0, "evidence": []}
        )
        self.assertEqual(envelope["permissions"]["authority"], 2)
        self.assertEqual(envelope["lifecycle"], {"state": "actif", "history": []})

    def test_builds_with_explicit_optional_fields(self):
        envelope = make_envelope(
            **_valid_kwargs(
                origin_ref="email:msg-42",
                event_id="EVT:KAMEHA:000007",
                valid_to="2028-05-01T00:00:00Z",
                version=3,
                evidence=["EVT:KAMEHA:000007"],
                state="archive",
                history=[{"from": "actif", "to": "archive", "ts": "2028-05-02"}],
            )
        )
        self.assertEqual(envelope["provenance"]["origin_ref"], "email:msg-42")
        self.assertEqual(envelope["provenance"]["event_id"], "EVT:KAMEHA:000007")
        self.assertEqual(envelope["temporal"]["valid_to"], "2028-05-01T00:00:00Z")
        self.assertEqual(envelope["temporal"]["version"], 3)
        self.assertEqual(envelope["confidence"]["evidence"], ["EVT:KAMEHA:000007"])
        self.assertEqual(envelope["lifecycle"]["state"], "archive")
        self.assertEqual(len(envelope["lifecycle"]["history"]), 1)

    def test_envelope_is_json_serializable(self):
        envelope = make_envelope(**_valid_kwargs())
        # L'enveloppe universelle est un objet JSON (Backlog, section 1).
        roundtrip = json.loads(json.dumps(envelope))
        self.assertEqual(roundtrip, envelope)

    def test_rejects_invalid_nature_at_construction(self):
        with self.assertRaises(EnvelopeError):
            make_envelope(**_valid_kwargs(nature="deviné"))

    def test_default_lists_are_not_shared_between_calls(self):
        first = make_envelope(**_valid_kwargs())
        first["confidence"]["evidence"].append("x")
        first["lifecycle"]["history"].append("y")

        second = make_envelope(**_valid_kwargs())
        self.assertEqual(second["confidence"]["evidence"], [])
        self.assertEqual(second["lifecycle"]["history"], [])


class FiveNaturesTests(unittest.TestCase):
    """Les 5 natures de confiance de la Constitution (loi 5)."""

    def test_exactly_five_natures_defined(self):
        self.assertEqual(len(NATURES), 5)
        self.assertEqual(
            set(NATURES), {"fait", "mesuré", "estimé", "hypothèse", "projection"}
        )

    def test_each_of_the_five_natures_is_accepted(self):
        for nature in NATURES:
            with self.subTest(nature=nature):
                envelope = make_envelope(**_valid_kwargs(nature=nature))
                self.assertTrue(validate_envelope(envelope))

    def test_nature_outside_the_five_is_rejected(self):
        for bogus_nature in ("invente", "deviné", "", "FAIT", None, 42):
            with self.subTest(nature=bogus_nature):
                envelope = make_envelope(**_valid_kwargs())
                envelope["confidence"]["nature"] = bogus_nature
                with self.assertRaises(EnvelopeError):
                    validate_envelope(envelope)


class ValidateEnvelopeStructureTests(unittest.TestCase):
    """Verifie que chaque champ obligatoire de chaque facette est controle."""

    def setUp(self):
        self.envelope = make_envelope(**_valid_kwargs())

    def _corrupt_and_expect_rejection(self, mutate):
        envelope = copy.deepcopy(self.envelope)
        mutate(envelope)
        with self.assertRaises(EnvelopeError):
            validate_envelope(envelope)

    # --- structure generale -------------------------------------------

    def test_envelope_must_be_a_dict(self):
        with self.assertRaises(EnvelopeError):
            validate_envelope(["not", "a", "dict"])

    def test_valid_envelope_passes(self):
        self.assertTrue(validate_envelope(self.envelope))

    def test_each_top_level_key_is_required(self):
        for key in (
            "id", "type", "label", "provenance", "temporal",
            "confidence", "permissions", "lifecycle",
        ):
            with self.subTest(missing=key):
                self._corrupt_and_expect_rejection(lambda e, key=key: e.pop(key))

    def test_id_type_label_must_be_non_empty_strings(self):
        for field in ("id", "type", "label"):
            for bogus in ("", "   ", None, 123):
                with self.subTest(field=field, value=bogus):
                    self._corrupt_and_expect_rejection(
                        lambda e, field=field, bogus=bogus: e.__setitem__(field, bogus)
                    )

    # --- provenance -----------------------------------------------------

    def test_provenance_must_be_a_dict(self):
        self._corrupt_and_expect_rejection(lambda e: e.__setitem__("provenance", "nope"))

    def test_provenance_required_keys(self):
        for key in ("source", "origin_ref", "author", "event_id"):
            with self.subTest(missing=key):
                self._corrupt_and_expect_rejection(lambda e, key=key: e["provenance"].pop(key))

    def test_provenance_source_and_author_must_be_non_empty(self):
        for field in ("source", "author"):
            for bogus in ("", "   ", None, 123):
                with self.subTest(field=field, value=bogus):
                    self._corrupt_and_expect_rejection(
                        lambda e, field=field, bogus=bogus: e["provenance"].__setitem__(field, bogus)
                    )

    def test_provenance_optional_fields_reject_non_string_non_none(self):
        for field in ("origin_ref", "event_id"):
            with self.subTest(field=field):
                self._corrupt_and_expect_rejection(
                    lambda e, field=field: e["provenance"].__setitem__(field, 123)
                )

    # --- temporal (bi-temporalite) ---------------------------------------

    def test_temporal_must_be_a_dict(self):
        self._corrupt_and_expect_rejection(lambda e: e.__setitem__("temporal", "nope"))

    def test_temporal_required_keys(self):
        for key in ("valid_from", "valid_to", "ts_record", "version"):
            with self.subTest(missing=key):
                self._corrupt_and_expect_rejection(lambda e, key=key: e["temporal"].pop(key))

    def test_valid_from_must_be_iso8601(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["temporal"].__setitem__("valid_from", "pas une date")
        )

    def test_ts_record_must_be_iso8601(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["temporal"].__setitem__("ts_record", "pas une date")
        )

    def test_valid_to_must_be_iso8601_when_present(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["temporal"].__setitem__("valid_to", "pas une date")
        )

    def test_valid_to_must_be_strictly_after_valid_from(self):
        def mutate(e):
            e["temporal"]["valid_from"] = "2028-04-10T00:00:00Z"
            e["temporal"]["valid_to"] = "2028-04-01T00:00:00Z"

        self._corrupt_and_expect_rejection(mutate)

    def test_valid_to_equal_to_valid_from_is_rejected(self):
        def mutate(e):
            e["temporal"]["valid_from"] = "2028-04-10T00:00:00Z"
            e["temporal"]["valid_to"] = "2028-04-10T00:00:00Z"

        self._corrupt_and_expect_rejection(mutate)

    def test_valid_from_without_timezone_is_rejected(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["temporal"].__setitem__("valid_from", "2028-04-01T10:00:00")
        )

    def test_ts_record_without_timezone_is_rejected(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["temporal"].__setitem__("ts_record", "2028-04-01T10:00:00")
        )

    def test_valid_to_without_timezone_is_rejected(self):
        def mutate(e):
            e["temporal"]["valid_to"] = "2028-04-02T10:00:00"

        self._corrupt_and_expect_rejection(mutate)

    def test_timestamps_with_explicit_timezone_are_accepted(self):
        for value in ("2028-04-01T10:00:00Z", "2028-04-01T10:00:00+02:00", "2028-04-01T10:00:00-05:00"):
            with self.subTest(value=value):
                envelope = copy.deepcopy(self.envelope)
                envelope["temporal"]["valid_from"] = value
                envelope["temporal"]["ts_record"] = value
                self.assertTrue(validate_envelope(envelope))

    def test_version_must_be_a_positive_integer(self):
        for bogus in (0, -1, "1", 1.5, True):
            with self.subTest(value=bogus):
                self._corrupt_and_expect_rejection(
                    lambda e, bogus=bogus: e["temporal"].__setitem__("version", bogus)
                )

    # --- confidence -----------------------------------------------------

    def test_confidence_must_be_a_dict(self):
        self._corrupt_and_expect_rejection(lambda e: e.__setitem__("confidence", "nope"))

    def test_confidence_required_keys(self):
        for key in ("nature", "score", "evidence"):
            with self.subTest(missing=key):
                self._corrupt_and_expect_rejection(lambda e, key=key: e["confidence"].pop(key))

    def test_score_must_be_within_zero_one(self):
        for bogus in (-0.01, 1.01, "1", None, True):
            with self.subTest(value=bogus):
                self._corrupt_and_expect_rejection(
                    lambda e, bogus=bogus: e["confidence"].__setitem__("score", bogus)
                )

    def test_score_boundaries_are_accepted(self):
        for boundary in (0.0, 1.0):
            with self.subTest(value=boundary):
                envelope = copy.deepcopy(self.envelope)
                envelope["confidence"]["score"] = boundary
                self.assertTrue(validate_envelope(envelope))

    def test_evidence_must_be_a_list(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["confidence"].__setitem__("evidence", "EVT:1")
        )

    def test_evidence_items_must_be_non_empty_strings(self):
        for bogus_list in ([""], [123], [None], ["   "]):
            with self.subTest(value=bogus_list):
                self._corrupt_and_expect_rejection(
                    lambda e, bogus_list=bogus_list: e["confidence"].__setitem__("evidence", bogus_list)
                )

    def test_evidence_with_valid_string_items_is_accepted(self):
        envelope = copy.deepcopy(self.envelope)
        envelope["confidence"]["evidence"] = ["EVT:KAMEHA:000001", "EVT:KAMEHA:000002"]
        self.assertTrue(validate_envelope(envelope))

    # --- permissions -----------------------------------------------------

    def test_permissions_must_be_a_dict(self):
        self._corrupt_and_expect_rejection(lambda e: e.__setitem__("permissions", "nope"))

    def test_permissions_required_keys(self):
        for key in ("owner", "visibility", "authority"):
            with self.subTest(missing=key):
                self._corrupt_and_expect_rejection(lambda e, key=key: e["permissions"].pop(key))

    def test_owner_and_visibility_must_be_non_empty(self):
        for field in ("owner", "visibility"):
            for bogus in ("", "   ", None, 123):
                with self.subTest(field=field, value=bogus):
                    self._corrupt_and_expect_rejection(
                        lambda e, field=field, bogus=bogus: e["permissions"].__setitem__(field, bogus)
                    )

    def test_authority_must_be_within_n0_n5(self):
        for bogus in (-1, 6, "2", 1.5, True):
            with self.subTest(value=bogus):
                self._corrupt_and_expect_rejection(
                    lambda e, bogus=bogus: e["permissions"].__setitem__("authority", bogus)
                )

    def test_authority_boundaries_are_accepted(self):
        for boundary in (0, 5):
            with self.subTest(value=boundary):
                envelope = copy.deepcopy(self.envelope)
                envelope["permissions"]["authority"] = boundary
                self.assertTrue(validate_envelope(envelope))

    # --- lifecycle -----------------------------------------------------

    def test_lifecycle_must_be_a_dict(self):
        self._corrupt_and_expect_rejection(lambda e: e.__setitem__("lifecycle", "nope"))

    def test_lifecycle_required_keys(self):
        for key in ("state", "history"):
            with self.subTest(missing=key):
                self._corrupt_and_expect_rejection(lambda e, key=key: e["lifecycle"].pop(key))

    def test_state_must_be_non_empty_string(self):
        for bogus in ("", "   ", None, 123):
            with self.subTest(value=bogus):
                self._corrupt_and_expect_rejection(
                    lambda e, bogus=bogus: e["lifecycle"].__setitem__("state", bogus)
                )

    def test_history_must_be_a_list(self):
        self._corrupt_and_expect_rejection(
            lambda e: e["lifecycle"].__setitem__("history", "not-a-list")
        )

    def test_history_items_must_be_dicts(self):
        for bogus_list in (["abc"], [123], [None]):
            with self.subTest(value=bogus_list):
                self._corrupt_and_expect_rejection(
                    lambda e, bogus_list=bogus_list: e["lifecycle"].__setitem__("history", bogus_list)
                )

    def test_history_with_valid_dict_items_is_accepted(self):
        envelope = copy.deepcopy(self.envelope)
        envelope["lifecycle"]["history"] = [
            {"from": "actif", "to": "archive", "ts": "2028-05-02T00:00:00Z"}
        ]
        self.assertTrue(validate_envelope(envelope))


if __name__ == "__main__":
    unittest.main()
