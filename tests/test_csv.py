"""Tests T-M05-2 : parseur CSV generique + profils source.

Criteres backlog : un CSV inconnu sans profil -> anomalie « profil
manquant », jamais d'interpretation devinee. DoD : au moins 1 profil reel
(releve bancaire) teste.
"""
import json
import os
import shutil
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from perception.parsers import csv_parser  # noqa: E402

RELEVE_CSV = (
    "Date valeur;Montant;Devise;Contrepartie;Communication\n"
    "2028-04-01T00:00:00Z;-142,50;EUR;Foodex;Facture 123\n"
    "2028-04-02T00:00:00Z;890,00;EUR;Uber Eats;Versement semaine 13\n"
    "2028-04-03T00:00:00Z;abc;EUR;Inconnu;Ligne invalide\n"
)


class CsvTestCase(unittest.TestCase):
    def setUp(self):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_csv")
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(base)
        self.base = base
        self.db_path = os.path.join(base, "eos.db")
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        csv_parser.load_profiles_as_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.base)

    def _write(self, filename, content):
        path = os.path.join(self.base, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path


class MissingProfileTests(CsvTestCase):
    def test_unknown_csv_without_profile_creates_profil_manquant_anomaly(self):
        path = self._write("mystere-export.csv", "a,b\n1,2\n")

        outcome = csv_parser.parse(self.conn, path)

        self.assertEqual(outcome["status"], "no_profile")
        row = self.conn.execute(
            "SELECT type, state FROM anomalies WHERE anomaly_id = ?", (outcome["anomaly_id"],)
        ).fetchone()
        self.assertEqual(row, ("perception/profil-manquant", "ouverte"))

    def test_unknown_csv_is_never_interpreted_into_events(self):
        path = self._write("mystere-export.csv", "a,b\n1,2\n")
        csv_parser.parse(self.conn, path)

        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type LIKE 'PERCEPTION.%'"
        ).fetchone()[0]
        self.assertEqual(count, 0)


class BankStatementProfileTests(CsvTestCase):
    """DoD : au moins 1 profil reel (releve bancaire) teste."""

    def test_profile_is_found_by_filename_match(self):
        profile = csv_parser.find_profile(self.conn, "releve-avril.csv")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "source-profile/banque-releve")

    def test_valid_lines_become_statement_line_events(self):
        path = self._write("releve-avril.csv", RELEVE_CSV)

        outcome = csv_parser.parse(self.conn, path)

        self.assertEqual(outcome["status"], "parsed")
        self.assertEqual(outcome["records"], 3)
        self.assertEqual(len(outcome["appended"]), 2)  # la 3e ligne est invalide

        rows = self.conn.execute(
            "SELECT payload_json FROM events WHERE type = 'PERCEPTION.StatementLine'"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        record = json.loads(rows[0][0])["payload"]["record"]
        self.assertEqual(set(record.keys()), {"date", "montant", "devise", "contrepartie", "libelle"})

    def test_invalid_line_is_quarantined_never_a_fact(self):
        path = self._write("releve-avril.csv", RELEVE_CSV)
        outcome = csv_parser.parse(self.conn, path)

        self.assertEqual(len(outcome["quarantined"]), 1)
        quarantine_count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'SYSTEM.Quarantine'"
        ).fetchone()[0]
        self.assertEqual(quarantine_count, 1)

    def test_replaying_the_import_creates_zero_duplicates(self):
        path = self._write("releve-avril.csv", RELEVE_CSV)
        csv_parser.parse(self.conn, path)
        second = csv_parser.parse(self.conn, path)

        self.assertEqual(len(second["appended"]), 0)
        self.assertEqual(second["duplicates"], 2)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'PERCEPTION.StatementLine'"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_profile_result_carries_name_and_version(self):
        path = self._write("releve-avril.csv", RELEVE_CSV)
        outcome = csv_parser.parse(self.conn, path)
        self.assertEqual(outcome["profile"], "source-profile/banque-releve@1")


class ProfilesAsRulesTests(CsvTestCase):
    def test_profiles_are_loaded_as_versioned_rules(self):
        from core import rules
        profile = rules.get(self.conn, "source-profile/banque-releve", "2028-01-01T00:00:00Z")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["version"], 1)
        self.assertEqual(profile["origin"], "seed")

    def test_loading_profiles_twice_is_idempotent(self):
        inserted = csv_parser.load_profiles_as_rules(self.conn)
        self.assertEqual(inserted, [])

    def test_new_profile_version_wins_from_its_valid_from_date(self):
        """Le profil est une regle versionnee : une v2 datee remplace la
        v1 a partir de sa date d'effet, sans l'ecraser."""
        from core import rules
        v1 = rules.get(self.conn, "source-profile/banque-releve", "2028-01-01T00:00:00Z")
        new_body = dict(v1["body"], delimiter=",")
        rules.add_version(self.conn, "source-profile/banque-releve", new_body,
                          valid_from="2028-06-01T00:00:00Z", origin="manual")

        before = csv_parser.find_profile(self.conn, "releve.csv", "2028-05-01T00:00:00Z")
        after = csv_parser.find_profile(self.conn, "releve.csv", "2028-07-01T00:00:00Z")
        self.assertEqual(before["version"], 1)
        self.assertEqual(after["version"], 2)


if __name__ == "__main__":
    unittest.main()
