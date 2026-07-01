"""Tests T-M02-1 : corpus de regles versionnees bi-temporelles.

Prouve les criteres du backlog : deux versions coexistent ; get(name,
at_date) renvoie la version applicable a cette date, jamais simplement la
derniere creee ; le rejeu par date est fidele quel que soit le nombre de
versions ajoutees ensuite.
"""
import os
import sqlite3
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import rules  # noqa: E402


class RulesTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_rules.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _row_count(self, name):
        return self.conn.execute(
            "SELECT COUNT(*) FROM rules WHERE name = ?", (name,)
        ).fetchone()[0]


class AddVersionTests(RulesTestCase):
    def test_first_version_is_number_one(self):
        result = rules.add_version(
            self.conn,
            "categorization/foodex",
            {"contrepartie": "Foodex", "categorie": "achats-marchandises"},
            valid_from="2028-01-01T00:00:00Z",
        )
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["rule_id"], "RULE:categorization/foodex")
        self.assertEqual(result["name"], "categorization/foodex")

    def test_two_versions_coexist(self):
        rules.add_version(
            self.conn, "categorization/foodex", {"categorie": "A"},
            valid_from="2028-01-01T00:00:00Z",
        )
        rules.add_version(
            self.conn, "categorization/foodex", {"categorie": "B"},
            valid_from="2028-04-01T00:00:00Z",
        )

        self.assertEqual(self._row_count("categorization/foodex"), 2)

        versions = self.conn.execute(
            "SELECT version, body_json FROM rules WHERE name = ? ORDER BY version",
            ("categorization/foodex",),
        ).fetchall()
        self.assertEqual([v for v, _ in versions], [1, 2])

    def test_version_numbers_increment_per_name_independently(self):
        rules.add_version(self.conn, "kpi/ca", {"formule": "sum(ventes)"}, valid_from="2028-01-01T00:00:00Z")
        rules.add_version(self.conn, "kpi/marge", {"formule": "ca - couts"}, valid_from="2028-01-01T00:00:00Z")
        result = rules.add_version(
            self.conn, "kpi/ca", {"formule": "sum(ventes) - remises"}, valid_from="2028-02-01T00:00:00Z"
        )
        self.assertEqual(result["version"], 2)

    def test_body_round_trips(self):
        body = {"seuil": 0.05, "categorie": "achats-marchandises", "actif": True}
        result = rules.add_version(
            self.conn, "reconciliation/seuil", body, valid_from="2028-01-01T00:00:00Z"
        )
        self.assertEqual(result["body"], body)

        fetched = rules.get(self.conn, "reconciliation/seuil", "2028-06-01T00:00:00Z")
        self.assertEqual(fetched["body"], body)

    def test_ts_record_defaults_to_now_and_differs_from_valid_from(self):
        result = rules.add_version(
            self.conn, "kpi/food_cost", {"formule": "couts / ca"}, valid_from="2020-01-01T00:00:00Z"
        )
        ts_record = datetime.fromisoformat(result["ts_record"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        self.assertLess(abs((now - ts_record).total_seconds()), 30)

    def test_explicit_ts_record_is_respected(self):
        result = rules.add_version(
            self.conn, "kpi/food_cost", {"formule": "couts / ca"},
            valid_from="2020-01-01T00:00:00Z", ts_record="2028-06-15T00:00:00Z",
        )
        self.assertEqual(result["ts_record"], "2028-06-15T00:00:00Z")

    def test_rejects_naive_valid_from(self):
        with self.assertRaises(rules.RuleError):
            rules.add_version(
                self.conn, "kpi/ca", {"formule": "sum(ventes)"}, valid_from="2028-01-01T00:00:00"
            )

    def test_never_overwrites_an_existing_version(self):
        """La cle primaire (name, version) empeche structurellement tout
        ecrasement, y compris via une requete directe."""
        rules.add_version(self.conn, "kpi/ca", {"formule": "v1"}, valid_from="2028-01-01T00:00:00Z")

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO rules (rule_id, name, version, valid_from, ts_record, "
                "body_json, origin, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("RULE:kpi/ca", "kpi/ca", 1, "2028-01-01T00:00:00Z", "2028-01-01T00:00:00Z",
                 '{"formule": "v1-tampered"}', "manual", 1),
            )

        # La version 1 d'origine n'a pas bouge.
        fetched = rules.get(self.conn, "kpi/ca", "2028-06-01T00:00:00Z")
        self.assertEqual(fetched["body"], {"formule": "v1"})


class GetAppliesByDateTests(RulesTestCase):
    def setUp(self):
        super().setUp()
        rules.add_version(
            self.conn, "categorization/foodex", {"categorie": "janvier"},
            valid_from="2028-01-01T00:00:00Z",
        )
        rules.add_version(
            self.conn, "categorization/foodex", {"categorie": "avril"},
            valid_from="2028-04-01T00:00:00Z",
        )
        rules.add_version(
            self.conn, "categorization/foodex", {"categorie": "aout"},
            valid_from="2028-08-01T00:00:00Z",
        )

    def test_get_returns_the_version_in_effect_at_the_date_not_the_latest(self):
        """Critere backlog : get(name, avril-2028) renvoie la version
        d'avril, pas la derniere (aout)."""
        result = rules.get(self.conn, "categorization/foodex", "2028-04-15T00:00:00Z")
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["body"], {"categorie": "avril"})

    def test_get_returns_january_version_for_a_march_date(self):
        result = rules.get(self.conn, "categorization/foodex", "2028-03-20T00:00:00Z")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["body"], {"categorie": "janvier"})

    def test_get_returns_latest_version_for_a_date_after_all_versions(self):
        result = rules.get(self.conn, "categorization/foodex", "2028-12-01T00:00:00Z")
        self.assertEqual(result["version"], 3)
        self.assertEqual(result["body"], {"categorie": "aout"})

    def test_get_returns_none_before_the_first_version(self):
        result = rules.get(self.conn, "categorization/foodex", "2027-01-01T00:00:00Z")
        self.assertIsNone(result)

    def test_get_at_exact_valid_from_boundary_returns_that_version(self):
        result = rules.get(self.conn, "categorization/foodex", "2028-04-01T00:00:00Z")
        self.assertEqual(result["version"], 2)

    def test_get_unknown_rule_name_returns_none(self):
        result = rules.get(self.conn, "does/not-exist", "2028-04-15T00:00:00Z")
        self.assertIsNone(result)

    def test_rejects_naive_at_date(self):
        with self.assertRaises(rules.RuleError):
            rules.get(self.conn, "categorization/foodex", "2028-04-15T00:00:00")

    def test_faithful_replay_across_many_dates_is_deterministic(self):
        """DoD : rejeu fidele des regles par date prouve - interroger les
        memes dates plusieurs fois donne toujours la meme reponse, quelle
        que soit l'ordre ou le nombre de versions ajoutees depuis."""
        expectations = [
            ("2028-01-15T00:00:00Z", 1, "janvier"),
            ("2028-03-31T23:59:59Z", 1, "janvier"),
            ("2028-04-01T00:00:00Z", 2, "avril"),
            ("2028-07-31T00:00:00Z", 2, "avril"),
            ("2028-08-01T00:00:00Z", 3, "aout"),
            ("2028-10-01T00:00:00Z", 3, "aout"),
        ]

        for at_date, expected_version, expected_categorie in expectations:
            with self.subTest(at_date=at_date):
                result = rules.get(self.conn, "categorization/foodex", at_date)
                self.assertEqual(result["version"], expected_version)
                self.assertEqual(result["body"]["categorie"], expected_categorie)

        # Une regle plus recente encore n'affecte jamais les dates passees deja verifiees.
        rules.add_version(
            self.conn, "categorization/foodex", {"categorie": "decembre"},
            valid_from="2028-12-01T00:00:00Z",
        )
        for at_date, expected_version, expected_categorie in expectations:
            with self.subTest(replay=at_date):
                result = rules.get(self.conn, "categorization/foodex", at_date)
                self.assertEqual(result["version"], expected_version)
                self.assertEqual(result["body"]["categorie"], expected_categorie)


class ValidToAndActiveTests(RulesTestCase):
    def test_valid_to_closes_a_version_explicitly(self):
        rules.add_version(
            self.conn, "alert-threshold/tresorerie", {"seuil": 1000},
            valid_from="2028-01-01T00:00:00Z", valid_to="2028-02-01T00:00:00Z",
        )

        within = rules.get(self.conn, "alert-threshold/tresorerie", "2028-01-15T00:00:00Z")
        after = rules.get(self.conn, "alert-threshold/tresorerie", "2028-02-15T00:00:00Z")

        self.assertIsNotNone(within)
        self.assertIsNone(after)

    def test_inactive_version_is_never_returned(self):
        rules.add_version(
            self.conn, "kpi/ticket_moyen", {"formule": "ca / commandes"},
            valid_from="2028-01-01T00:00:00Z", active=False,
        )

        result = rules.get(self.conn, "kpi/ticket_moyen", "2028-06-01T00:00:00Z")
        self.assertIsNone(result)

    def test_inactive_version_does_not_shadow_an_earlier_active_one(self):
        rules.add_version(
            self.conn, "kpi/ticket_moyen", {"formule": "v1"}, valid_from="2028-01-01T00:00:00Z",
        )
        rules.add_version(
            self.conn, "kpi/ticket_moyen", {"formule": "v2-retiree"},
            valid_from="2028-03-01T00:00:00Z", active=False,
        )

        result = rules.get(self.conn, "kpi/ticket_moyen", "2028-06-01T00:00:00Z")
        self.assertEqual(result["body"], {"formule": "v1"})


class NoOverlapInvariantTests(RulesTestCase):
    """Invariant metier : deux versions d'une meme regle ne sont jamais
    actives sur une meme periode de validite - pour toute date, get() ne
    peut renvoyer qu'une seule version a la fois, jamais deux."""

    def setUp(self):
        super().setUp()
        rules.add_version(
            self.conn, "alert-threshold/marge", {"seuil": 0.10},
            valid_from="2028-01-01T00:00:00Z",
        )
        rules.add_version(
            self.conn, "alert-threshold/marge", {"seuil": 0.12},
            valid_from="2028-06-01T00:00:00Z",
        )
        rules.add_version(
            self.conn, "alert-threshold/marge", {"seuil": 0.15},
            valid_from="2028-09-01T00:00:00Z",
        )

    def test_each_date_resolves_to_exactly_one_version_never_two(self):
        expectations = [
            ("2028-01-01T00:00:00Z", 1),
            ("2028-03-15T00:00:00Z", 1),
            ("2028-05-31T23:59:59Z", 1),
            ("2028-06-01T00:00:00Z", 2),
            ("2028-07-15T00:00:00Z", 2),
            ("2028-08-31T23:59:59Z", 2),
            ("2028-09-01T00:00:00Z", 3),
            ("2028-12-31T23:59:59Z", 3),
        ]

        for at_date, expected_version in expectations:
            with self.subTest(at_date=at_date):
                result = rules.get(self.conn, "alert-threshold/marge", at_date)
                # get() ne peut structurellement renvoyer qu'un seul objet
                # (jamais une liste) : la seule facon de verifier
                # l'absence d'ambiguite est de prouver que c'est toujours
                # la version attendue, jamais une des deux autres.
                self.assertIsNotNone(result)
                self.assertEqual(result["version"], expected_version)
                other_versions = {1, 2, 3} - {expected_version}
                self.assertNotIn(result["version"], other_versions)

    def test_version_boundary_is_never_shared_by_two_versions(self):
        """A l'instant precis ou une version prend effet, l'ancienne
        version n'est plus jamais renvoyee - aucun chevauchement possible
        a la frontiere."""
        just_before = rules.get(self.conn, "alert-threshold/marge", "2028-05-31T23:59:59Z")
        at_boundary = rules.get(self.conn, "alert-threshold/marge", "2028-06-01T00:00:00Z")

        self.assertEqual(just_before["version"], 1)
        self.assertEqual(at_boundary["version"], 2)
        self.assertNotEqual(just_before["version"], at_boundary["version"])


if __name__ == "__main__":
    unittest.main()
