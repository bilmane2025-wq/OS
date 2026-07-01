"""Tests T-M02-2 : chargement des regles seed (categorisation, KPI, seuils).

Prouve le critere du backlog : les regles seed sont interrogeables par
date. DoD : au moins 10 regles seed chargees et testees.
"""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import rules  # noqa: E402

SEED_PATH = rules.DEFAULT_SEED_PATH


class SeedFileTests(unittest.TestCase):
    """Integrite du fichier data/seed_rules.json, independamment de la DB."""

    def setUp(self):
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            self.entries = json.load(f)

    def test_at_least_ten_seed_rules(self):
        self.assertGreaterEqual(len(self.entries), 10)

    def test_every_entry_has_the_required_fields(self):
        for entry in self.entries:
            with self.subTest(name=entry.get("name")):
                self.assertIn("name", entry)
                self.assertIn("valid_from", entry)
                self.assertIn("body", entry)
                self.assertIsInstance(entry["body"], dict)

    def test_names_are_unique(self):
        names = [entry["name"] for entry in self.entries]
        self.assertEqual(len(names), len(set(names)))

    def test_covers_the_four_rule_families(self):
        prefixes = {entry["name"].split("/", 1)[0] for entry in self.entries}
        self.assertIn("categorization", prefixes)
        self.assertIn("kpi", prefixes)
        self.assertIn("fx-rate", prefixes)
        self.assertTrue(
            "reconciliation" in prefixes or "alert-threshold" in prefixes,
            "au moins une regle de seuil (reconciliation/* ou alert-threshold/*) attendue",
        )

    def test_kpi_seed_covers_the_eight_mvp_indicators(self):
        kpi_names = {
            entry["name"].split("/", 1)[1]
            for entry in self.entries
            if entry["name"].startswith("kpi/")
        }
        expected = {
            "ca", "marge", "food_cost", "ticket_moyen",
            "commandes_jour", "tresorerie", "commission", "dependance_fournisseur",
        }
        self.assertEqual(kpi_names, expected)


class LoadSeedRulesTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_seed.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_load_seed_rules_inserts_all_entries_as_version_one(self):
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            expected_count = len(json.load(f))

        inserted = rules.load_seed_rules(self.conn)

        self.assertEqual(len(inserted), expected_count)
        self.assertGreaterEqual(len(inserted), 10)
        for entry in inserted:
            self.assertEqual(entry["version"], 1)
            self.assertEqual(entry["origin"], "seed")

    def test_seed_rules_are_queryable_by_date(self):
        """Critere backlog : les regles seed sont interrogeables par date."""
        rules.load_seed_rules(self.conn)

        result = rules.get(self.conn, "kpi/ca", "2028-06-01T00:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result["body"]["label"], "Chiffre d'affaires")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["origin"], "seed")

    def test_every_seeded_rule_is_queryable_by_date(self):
        inserted = rules.load_seed_rules(self.conn)

        for entry in inserted:
            with self.subTest(name=entry["name"]):
                fetched = rules.get(self.conn, entry["name"], "2028-06-01T00:00:00Z")
                self.assertIsNotNone(fetched)
                self.assertEqual(fetched["body"], entry["body"])

    def test_seed_query_before_valid_from_returns_none(self):
        rules.load_seed_rules(self.conn)

        result = rules.get(self.conn, "kpi/ca", "2019-01-01T00:00:00Z")
        self.assertIsNone(result)

    def test_loading_seed_twice_is_idempotent(self):
        first_pass = rules.load_seed_rules(self.conn)
        second_pass = rules.load_seed_rules(self.conn)

        self.assertGreaterEqual(len(first_pass), 10)
        self.assertEqual(second_pass, [])

        row_count = self.conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
        self.assertEqual(row_count, len(first_pass))

        # Toujours version 1 : aucun redemarrage ne cree de version 2.
        version = self.conn.execute(
            "SELECT MAX(version) FROM rules WHERE name = ?", ("kpi/ca",)
        ).fetchone()[0]
        self.assertEqual(version, 1)

    def test_seed_never_overrides_a_pre_existing_manual_version(self):
        rules.add_version(
            self.conn, "kpi/ca", {"label": "CA (definition maison)"},
            valid_from="2020-01-01T00:00:00Z", origin="manual",
        )

        rules.load_seed_rules(self.conn)

        result = rules.get(self.conn, "kpi/ca", "2028-06-01T00:00:00Z")
        self.assertEqual(result["origin"], "manual")
        self.assertEqual(result["body"], {"label": "CA (definition maison)"})

        version = self.conn.execute(
            "SELECT MAX(version) FROM rules WHERE name = ?", ("kpi/ca",)
        ).fetchone()[0]
        self.assertEqual(version, 1)


if __name__ == "__main__":
    unittest.main()
