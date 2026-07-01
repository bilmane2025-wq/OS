"""Tests T-M28-1 : echelle d'autorite N0-N5 (governance.permissions).

Prouve le critere du backlog : une action irreversible sans N5 est
bloquee (DoD : test de blocage prouve).
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from governance import permissions  # noqa: E402


class PermissionsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_permissions.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class GrantAndAuthorityOfTests(PermissionsTestCase):
    def test_unknown_actor_defaults_to_n0(self):
        self.assertEqual(permissions.authority_of(self.conn, "agent:inconnu", "Facture"), 0)

    def test_grant_then_authority_of_reflects_the_value(self):
        permissions.grant(self.conn, "human:pierre", "Facture", 4)
        self.assertEqual(permissions.authority_of(self.conn, "human:pierre", "Facture"), 4)

    def test_grant_is_idempotent_and_overwrites(self):
        permissions.grant(self.conn, "agent:doctrine", "Regle", 2)
        permissions.grant(self.conn, "agent:doctrine", "Regle", 3)
        self.assertEqual(permissions.authority_of(self.conn, "agent:doctrine", "Regle"), 3)

    def test_authority_is_scoped_per_object_type(self):
        permissions.grant(self.conn, "human:pierre", "Facture", 4)
        self.assertEqual(permissions.authority_of(self.conn, "human:pierre", "Paiement"), 0)

    def test_grant_rejects_out_of_range_authority(self):
        for bogus in (-1, 6, 1.5, True, "4"):
            with self.subTest(value=bogus):
                with self.assertRaises(ValueError):
                    permissions.grant(self.conn, "human:pierre", "Facture", bogus)

    def test_grant_rejects_empty_subject_or_object_type(self):
        with self.assertRaises(ValueError):
            permissions.grant(self.conn, "", "Facture", 2)
        with self.assertRaises(ValueError):
            permissions.grant(self.conn, "human:pierre", "", 2)


class IrreversibleTransitionRequiresN5Tests(PermissionsTestCase):
    """Critere backlog : une action irreversible sans N5 est bloquee."""

    def test_irreversible_transition_is_blocked_below_n5(self):
        permissions.grant(self.conn, "agent:tresorerie", "Paiement", 4)

        with self.assertRaises(permissions.AuthorityError):
            permissions.check(
                self.conn, "agent:tresorerie",
                {"object_type": "Paiement", "action": "executer-paiement", "irreversible": True},
            )

    def test_irreversible_transition_is_allowed_at_n5(self):
        permissions.grant(self.conn, "human:pierre", "Paiement", 5)

        result = permissions.check(
            self.conn, "human:pierre",
            {"object_type": "Paiement", "action": "executer-paiement", "irreversible": True},
        )
        self.assertTrue(result)

    def test_irreversible_transition_for_unknown_actor_is_blocked(self):
        with self.assertRaises(permissions.AuthorityError):
            permissions.check(
                self.conn, "agent:jamais-vu",
                {"object_type": "Paiement", "irreversible": True},
            )

    def test_material_transition_also_requires_n5(self):
        permissions.grant(self.conn, "agent:achats", "Contrat", 4)

        with self.assertRaises(permissions.AuthorityError):
            permissions.check(
                self.conn, "agent:achats",
                {"object_type": "Contrat", "action": "signer-contrat-materiel", "material": True},
            )

    def test_material_transition_is_allowed_at_n5(self):
        permissions.grant(self.conn, "human:pierre", "Contrat", 5)

        result = permissions.check(
            self.conn, "human:pierre",
            {"object_type": "Contrat", "material": True},
        )
        self.assertTrue(result)

    def test_irreversible_and_material_together_still_only_require_n5(self):
        permissions.grant(self.conn, "human:pierre", "Contrat", 5)

        result = permissions.check(
            self.conn, "human:pierre",
            {"object_type": "Contrat", "irreversible": True, "material": True},
        )
        self.assertTrue(result)

    def test_required_authority_cannot_bypass_the_n5_floor(self):
        """Meme si l'appelant sous-declare required_authority, le plancher
        N5 s'applique des que irreversible/material est vrai."""
        permissions.grant(self.conn, "agent:tresorerie", "Paiement", 4)

        with self.assertRaises(permissions.AuthorityError):
            permissions.check(
                self.conn, "agent:tresorerie",
                {"object_type": "Paiement", "irreversible": True, "required_authority": 1},
            )

    def test_blocked_transition_raises_a_descriptive_error(self):
        permissions.grant(self.conn, "agent:tresorerie", "Paiement", 4)

        with self.assertRaises(permissions.AuthorityError) as ctx:
            permissions.check(
                self.conn, "agent:tresorerie",
                {"object_type": "Paiement", "action": "executer-paiement", "irreversible": True},
            )
        message = str(ctx.exception)
        self.assertIn("executer-paiement", message)
        self.assertIn("agent:tresorerie", message)


class OrdinaryTransitionTests(PermissionsTestCase):
    def test_reversible_transition_allowed_when_authority_sufficient(self):
        permissions.grant(self.conn, "agent:categorisation", "Ecriture", 2)

        result = permissions.check(
            self.conn, "agent:categorisation",
            {"object_type": "Ecriture", "required_authority": 2},
        )
        self.assertTrue(result)

    def test_reversible_transition_blocked_when_authority_insufficient(self):
        permissions.grant(self.conn, "agent:categorisation", "Ecriture", 1)

        with self.assertRaises(permissions.AuthorityError):
            permissions.check(
                self.conn, "agent:categorisation",
                {"object_type": "Ecriture", "required_authority": 2},
            )

    def test_default_required_authority_is_n0(self):
        """Sans required_authority explicite, une simple observation (N0)
        est autorisee meme pour un acteur inconnu."""
        result = permissions.check(self.conn, "agent:jamais-vu", {"object_type": "Ecriture"})
        self.assertTrue(result)

    def test_authority_exactly_matching_required_is_allowed(self):
        permissions.grant(self.conn, "agent:categorisation", "Ecriture", 3)
        result = permissions.check(
            self.conn, "agent:categorisation",
            {"object_type": "Ecriture", "required_authority": 3},
        )
        self.assertTrue(result)

    def test_higher_authority_than_required_is_allowed(self):
        permissions.grant(self.conn, "human:pierre", "Ecriture", 4)
        result = permissions.check(
            self.conn, "human:pierre",
            {"object_type": "Ecriture", "required_authority": 1},
        )
        self.assertTrue(result)

    def test_missing_object_type_is_rejected(self):
        with self.assertRaises(ValueError):
            permissions.check(self.conn, "human:pierre", {"required_authority": 1})

    def test_out_of_range_required_authority_is_rejected(self):
        with self.assertRaises(ValueError):
            permissions.check(
                self.conn, "human:pierre",
                {"object_type": "Ecriture", "required_authority": 6},
            )


if __name__ == "__main__":
    unittest.main()
