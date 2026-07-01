"""Tests T-M07-1 : validation & quarantaine (perception.quality).

DoD : test avec lignes valides/invalides. Critere backlog : une ligne
invalide n'entre jamais dans le journal comme un fait ; elle est mise en
quarantaine tracee.
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from perception import quality  # noqa: E402


class ValidateTests(unittest.TestCase):
    def test_valid_record_passes(self):
        profile = {"required": ["montant", "date"], "numeric": ["montant"], "date": ["date"]}
        record = {"montant": 42.5, "date": "2028-04-01T00:00:00Z"}

        result = quality.validate(record, profile)
        self.assertEqual(result, {"valid": True, "errors": []})

    def test_empty_profile_accepts_anything(self):
        result = quality.validate({"n'importe quoi": "ok"}, {})
        self.assertTrue(result["valid"])

    def test_missing_required_field_is_invalid(self):
        profile = {"required": ["montant", "fournisseur"]}
        result = quality.validate({"montant": 42}, profile)

        self.assertFalse(result["valid"])
        self.assertTrue(any("fournisseur" in e for e in result["errors"]))

    def test_empty_required_field_is_invalid(self):
        profile = {"required": ["fournisseur"]}
        result = quality.validate({"fournisseur": ""}, profile)
        self.assertFalse(result["valid"])

    def test_non_numeric_amount_is_invalid(self):
        profile = {"numeric": ["montant"]}
        result = quality.validate({"montant": "quarante-deux"}, profile)

        self.assertFalse(result["valid"])
        self.assertTrue(any("montant" in e for e in result["errors"]))

    def test_numeric_string_with_comma_is_accepted(self):
        profile = {"numeric": ["montant"]}
        result = quality.validate({"montant": "42,50"}, profile)
        self.assertTrue(result["valid"])

    def test_boolean_is_not_accepted_as_numeric(self):
        profile = {"numeric": ["actif"]}
        result = quality.validate({"actif": True}, profile)
        self.assertFalse(result["valid"])

    def test_invalid_date_is_invalid(self):
        profile = {"date": ["date"]}
        result = quality.validate({"date": "pas une date"}, profile)

        self.assertFalse(result["valid"])
        self.assertTrue(any("date" in e for e in result["errors"]))

    def test_naive_date_without_timezone_is_invalid(self):
        profile = {"date": ["date"]}
        result = quality.validate({"date": "2028-04-01T00:00:00"}, profile)
        self.assertFalse(result["valid"])

    def test_date_within_period_is_valid(self):
        profile = {
            "period_field": "date",
            "period": {"since": "2028-01-01T00:00:00Z", "until": "2029-01-01T00:00:00Z"},
        }
        result = quality.validate({"date": "2028-06-15T00:00:00Z"}, profile)
        self.assertTrue(result["valid"])

    def test_date_before_period_is_invalid(self):
        profile = {
            "period_field": "date",
            "period": {"since": "2028-01-01T00:00:00Z", "until": "2029-01-01T00:00:00Z"},
        }
        result = quality.validate({"date": "2027-12-31T00:00:00Z"}, profile)

        self.assertFalse(result["valid"])
        self.assertTrue(any("hors periode" in e for e in result["errors"]))

    def test_date_after_period_is_invalid(self):
        profile = {
            "period_field": "date",
            "period": {"since": "2028-01-01T00:00:00Z", "until": "2029-01-01T00:00:00Z"},
        }
        result = quality.validate({"date": "2029-01-01T00:00:00Z"}, profile)
        self.assertFalse(result["valid"])

    def test_multiple_errors_are_all_reported(self):
        profile = {"required": ["fournisseur"], "numeric": ["montant"], "date": ["date"]}
        record = {"montant": "abc", "date": "pas une date"}

        result = quality.validate(record, profile)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["errors"]), 3)

    def test_valid_and_invalid_lines_mixed(self):
        """DoD : test avec lignes valides/invalides."""
        profile = {"required": ["montant", "date"], "numeric": ["montant"], "date": ["date"]}
        lines = [
            {"montant": 42, "date": "2028-01-01T00:00:00Z"},           # valide
            {"montant": "quarante-deux", "date": "2028-01-01T00:00:00Z"},  # montant invalide
            {"montant": 42, "date": "pas une date"},                    # date invalide
            {"date": "2028-01-01T00:00:00Z"},                           # champ manquant
            {"montant": 10.5, "date": "2028-02-01T00:00:00Z"},          # valide
        ]

        results = [quality.validate(line, profile) for line in lines]
        self.assertEqual([r["valid"] for r in results], [True, False, False, False, True])


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_quality.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_quarantine_writes_a_system_quarantine_event(self):
        event_id, anomaly_id = quality.quarantine(
            self.conn, {"montant": "abc"}, ["montant n'est pas numerique"], source="inbox/export.csv"
        )

        row = self.conn.execute(
            "SELECT type, source, payload_json FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        type_, source, payload_json = row
        self.assertEqual(type_, "SYSTEM.Quarantine")
        self.assertEqual(source, "inbox/export.csv")

        payload = json.loads(payload_json)["payload"]
        self.assertEqual(payload["record"], {"montant": "abc"})
        self.assertEqual(payload["reasons"], ["montant n'est pas numerique"])

    def test_quarantine_writes_a_traceable_anomaly(self):
        event_id, anomaly_id = quality.quarantine(
            self.conn, {"montant": "abc"}, ["montant n'est pas numerique"]
        )

        row = self.conn.execute(
            "SELECT type, state, refs_json FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        type_, state, refs_json = row
        self.assertEqual(type_, "quality/invalid-record")
        self.assertEqual(state, "ouverte")
        self.assertEqual(json.loads(refs_json)["event_id"], event_id)

    def test_invalid_record_never_enters_the_journal_as_a_fact(self):
        """Critere backlog : une ligne invalide n'entre jamais dans le
        journal comme un fait."""
        quality.validate({"montant": "abc"}, {"numeric": ["montant"]})
        quality.quarantine(self.conn, {"montant": "abc"}, ["montant n'est pas numerique"])

        perception_events = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type LIKE 'PERCEPTION.%'"
        ).fetchone()[0]
        self.assertEqual(perception_events, 0)

        quarantine_events = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'SYSTEM.Quarantine'"
        ).fetchone()[0]
        self.assertEqual(quarantine_events, 1)


if __name__ == "__main__":
    unittest.main()
