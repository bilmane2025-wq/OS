"""Tests T-M25-5 : formulaires manuels (mode officiel).

Criteres backlog : toute source a une saisie manuelle equivalente.
DoD : chaque type d'evenement creable a la main.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from calc import kpi_catalog  # noqa: E402
from core import event_store, rules  # noqa: E402
from experience import views  # noqa: E402
from governance import permissions  # noqa: E402

HUMAN = "human:pierre"


class FormsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_forms.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)
        permissions.grant(self.conn, HUMAN, "ManualEntry", 1)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class EveryEventTypeCreatableTests(FormsTestCase):
    """DoD : chaque type d'evenement creable a la main."""

    CASES = {
        "facture": {"fournisseur": "Foodex", "montant": "120,00",
                    "date": "2028-04-01"},
        "depense": {"libelle": "Loyer avril", "montant": "-1500,00",
                    "date": "2028-04-01"},
        "vente": {"montant": "24,50", "date": "2028-04-01"},
        "decision": {"decision": "Changer de fournisseur", "motif": "prix"},
        "correction": {"cible": "EVT:X", "champ": "montant", "valeur": "125,00"},
    }

    def test_the_five_official_forms_are_declared(self):
        schemas = views.load_form_schemas()
        self.assertEqual(sorted(schemas),
                         ["correction", "decision", "depense", "facture", "vente"])

    def test_each_form_creates_a_manual_entry_event(self):
        for form, fields in self.CASES.items():
            with self.subTest(form=form):
                outcome = views.submit_manual(self.conn, form, fields, HUMAN)

                row = self.conn.execute(
                    "SELECT type, author, payload_json FROM events WHERE event_id = ?",
                    (outcome["event_id"],)).fetchone()
                self.assertEqual(row[0], "HUMAN.ManualEntry")
                self.assertEqual(row[1], HUMAN)
                payload = json.loads(row[2])["payload"]
                self.assertEqual(payload["form"], form)
                self.assertEqual(payload["fields"], fields)

    def test_manual_sale_feeds_the_kpis_like_any_source(self):
        """Toute source a une saisie manuelle equivalente : une vente
        saisie a la main alimente le CA exactement comme un export."""
        views.submit_manual(self.conn, "vente",
                            {"montant": "24,50", "date": "2028-04-01"}, HUMAN)
        detail = kpi_catalog.compute(self.conn, "ca")
        self.assertAlmostEqual(detail["value"], 24.5)
        self.assertEqual(detail["nature"], "fait")


class FormGuardsTests(FormsTestCase):
    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(views.FormError):
            views.submit_manual(self.conn, "facture", {"fournisseur": "Foodex"}, HUMAN)
        count = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(count, 0)

    def test_unknown_form_is_rejected(self):
        with self.assertRaises(views.FormError):
            views.submit_manual(self.conn, "inconnu", {}, HUMAN)

    def test_unauthorized_actor_is_blocked_by_the_authority_ladder(self):
        with self.assertRaises(permissions.AuthorityError):
            views.submit_manual(self.conn, "vente",
                                {"montant": "10,00", "date": "2028-04-01"},
                                "agent:anonyme")

    def test_each_submission_leaves_an_access_trace(self):
        """Chaque action sensible est tracee (integration M29)."""
        outcome = views.submit_manual(self.conn, "vente",
                                      {"montant": "24,50", "date": "2028-04-01"}, HUMAN)
        row = self.conn.execute(
            "SELECT subject, action, target FROM access_log").fetchone()
        self.assertEqual(row, (HUMAN, "manual-entry", outcome["event_id"]))

    def test_forms_page_renders_every_schema(self):
        rendered = views.render_forms()
        for form in ("facture", "depense", "vente", "decision", "correction"):
            self.assertIn(f'data-form="{form}"', rendered)


if __name__ == "__main__":
    unittest.main()
