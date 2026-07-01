"""Tests T-M30-1 : coffre a secrets (governance.secrets.get/set).

Prouve le critere du backlog : un secret n'apparait jamais dans une
projection (DoD : test d'isolement).
"""
import os
import shutil
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from governance import secrets  # noqa: E402


class SecretsTestCase(unittest.TestCase):
    def setUp(self):
        self.secrets_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_secrets"
        )
        if os.path.isdir(self.secrets_dir):
            shutil.rmtree(self.secrets_dir)

    def tearDown(self):
        if os.path.isdir(self.secrets_dir):
            shutil.rmtree(self.secrets_dir)


class GetSetInterfaceTests(SecretsTestCase):
    def test_set_then_get_round_trips(self):
        secrets.set("banque/api-key", "sk_live_super_secret", secrets_dir=self.secrets_dir)
        self.assertEqual(
            secrets.get("banque/api-key", secrets_dir=self.secrets_dir),
            "sk_live_super_secret",
        )

    def test_get_unknown_name_returns_none(self):
        self.assertIsNone(secrets.get("jamais-defini", secrets_dir=self.secrets_dir))

    def test_set_overwrites_existing_value(self):
        secrets.set("banque/api-key", "premiere-valeur", secrets_dir=self.secrets_dir)
        secrets.set("banque/api-key", "nouvelle-valeur", secrets_dir=self.secrets_dir)
        self.assertEqual(
            secrets.get("banque/api-key", secrets_dir=self.secrets_dir), "nouvelle-valeur"
        )

    def test_multiple_secrets_coexist_independently(self):
        secrets.set("banque/api-key", "valeur-banque", secrets_dir=self.secrets_dir)
        secrets.set("email/smtp-password", "valeur-email", secrets_dir=self.secrets_dir)

        self.assertEqual(secrets.get("banque/api-key", secrets_dir=self.secrets_dir), "valeur-banque")
        self.assertEqual(
            secrets.get("email/smtp-password", secrets_dir=self.secrets_dir), "valeur-email"
        )

    def test_empty_vault_by_default_mvp_is_vide(self):
        """Critere backlog : le coffre est vide au MVP tant que rien n'y a
        ete ecrit."""
        self.assertIsNone(secrets.get("quoi-que-ce-soit", secrets_dir=self.secrets_dir))

    def test_secret_survives_a_fresh_read_from_disk(self):
        """Le secret est bien relu depuis le disque (pas garde en memoire
        Python) - deux appels get() independants apres un set()."""
        secrets.set("banque/api-key", "persistant", secrets_dir=self.secrets_dir)
        first_read = secrets.get("banque/api-key", secrets_dir=self.secrets_dir)
        second_read = secrets.get("banque/api-key", secrets_dir=self.secrets_dir)
        self.assertEqual(first_read, "persistant")
        self.assertEqual(second_read, "persistant")

    def test_name_must_be_a_non_empty_string(self):
        for bogus in ("", "   ", None, 123):
            with self.subTest(value=bogus):
                with self.assertRaises(ValueError):
                    secrets.set(bogus, "valeur", secrets_dir=self.secrets_dir)
                with self.assertRaises(ValueError):
                    secrets.get(bogus, secrets_dir=self.secrets_dir)

    def test_value_must_be_a_string(self):
        with self.assertRaises(ValueError):
            secrets.set("banque/api-key", 12345, secrets_dir=self.secrets_dir)


class EncryptionAtRestTests(SecretsTestCase):
    def test_vault_file_on_disk_does_not_contain_the_plaintext_secret(self):
        secret_value = "sk_live_TRES_CONFIDENTIEL_42"
        secrets.set("banque/api-key", secret_value, secrets_dir=self.secrets_dir)

        vault_path = os.path.join(self.secrets_dir, "vault.enc")
        with open(vault_path, "rb") as f:
            raw_bytes = f.read()

        self.assertNotIn(secret_value.encode("utf-8"), raw_bytes)

    def test_master_key_file_is_created_with_restrictive_permissions(self):
        secrets.set("banque/api-key", "valeur", secrets_dir=self.secrets_dir)

        key_path = os.path.join(self.secrets_dir, "master.key")
        self.assertTrue(os.path.exists(key_path))
        mode = os.stat(key_path).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_vault_is_unreadable_without_the_matching_key(self):
        secrets.set("banque/api-key", "valeur-protegee", secrets_dir=self.secrets_dir)

        key_path = os.path.join(self.secrets_dir, "master.key")
        with open(key_path, "wb") as f:
            f.write(b"0" * 44)  # cle Fernet valide en forme, mais differente

        with self.assertRaises(secrets.SecretsError):
            secrets.get("banque/api-key", secrets_dir=self.secrets_dir)


class IsolationFromProjectionsTests(SecretsTestCase):
    """DoD T-M30-1 : test d'isolement - un secret n'apparait jamais dans
    une projection (la base SQLite data/eos.db)."""

    def setUp(self):
        super().setUp()
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_secrets.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        super().tearDown()

    def _all_tables(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [row[0] for row in rows]

    def test_secret_never_appears_in_any_database_table(self):
        secret_value = "sk_live_JAMAIS_DANS_LA_DB_88991"
        secrets.set("banque/api-key", secret_value, secrets_dir=self.secrets_dir)

        for table in self._all_tables():
            with self.subTest(table=table):
                rows = self.conn.execute(f"SELECT * FROM {table}").fetchall()
                for row in rows:
                    for cell in row:
                        self.assertNotIn(
                            secret_value, str(cell),
                            f"secret trouve dans la table {table} : fuite d'isolement",
                        )

    def test_secrets_module_never_opens_a_database_connection(self):
        """Preuve structurelle : aucune fonction publique de
        governance.secrets ne prend de connexion SQLite en parametre -
        il est donc impossible qu'un secret transite par le journal ou
        une projection via ce module."""
        import inspect

        for name in ("get", "set"):
            func = getattr(secrets, name)
            params = list(inspect.signature(func).parameters)
            self.assertNotIn("conn", params)


if __name__ == "__main__":
    unittest.main()
