"""Tests T-M11-2 : la contradiction est un etat (gaps.declare_contradiction
/ resolve_contradiction).

Criteres backlog : aucune ecrasure silencieuse ; les deux versions
conservees. DoD : test resolution tracee.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from core import event_store  # noqa: E402
from graph import gaps, graph_engine  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class ContradictionTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_contradiction.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "542,80", "fournisseur": "Foodex"}}, 1)
        self.invoice_id = graph_engine.apply(self.conn, event)[0]

        self.version_a = {"value": "542,80", "source": "pdf", "event_id": "EVT:A",
                          "score": 0.9, "authority": 1}
        self.version_b = {"value": "544,00", "source": "email", "event_id": "EVT:B",
                          "score": 0.6, "authority": 2}

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _declare(self, version_a=None, version_b=None):
        return gaps.declare_contradiction(
            self.conn, self.invoice_id,
            version_a or self.version_a, version_b or self.version_b)

    def test_contradiction_creates_a_tension_object_with_both_versions(self):
        outcome = self._declare()

        tension = graph_engine.get_object(self.conn, outcome["tension_id"])
        self.assertEqual(tension["type"], "Tension")
        self.assertEqual(tension["state"], "ouverte")
        self.assertEqual(tension["body"]["version_a"]["value"], "542,80")
        self.assertEqual(tension["body"]["version_b"]["value"], "544,00")

    def test_tension_is_linked_to_the_contested_object_by_contredit(self):
        outcome = self._declare()
        out = graph_engine.neighbors(self.conn, outcome["tension_id"], "out")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rel"], "contredit")
        self.assertEqual(out[0]["object"]["object_id"], self.invoice_id)

    def test_no_silent_overwrite_the_contested_object_is_untouched(self):
        """Aucune ecrasure silencieuse : l'objet conteste garde sa valeur
        d'origine tant que la resolution n'a pas tranche."""
        before = graph_engine.get_object(self.conn, self.invoice_id)
        self._declare()
        after = graph_engine.get_object(self.conn, self.invoice_id)
        self.assertEqual(before["body"], after["body"])

    def test_resolution_by_proof_higher_score_wins(self):
        outcome = self._declare()
        resolved = gaps.resolve_contradiction(self.conn, outcome["tension_id"])

        self.assertEqual(resolved["resolution"], {"winner": "version_a", "criterion": "preuve"})
        tension = graph_engine.get_object(self.conn, outcome["tension_id"])
        self.assertEqual(tension["state"], "resolue")
        # Les deux versions restent conservees apres resolution.
        self.assertEqual(tension["body"]["version_a"]["value"], "542,80")
        self.assertEqual(tension["body"]["version_b"]["value"], "544,00")

    def test_resolution_by_authority_when_scores_tie(self):
        version_a = dict(self.version_a, score=0.7, authority=1)
        version_b = dict(self.version_b, score=0.7, authority=3)
        outcome = self._declare(version_a, version_b)

        resolved = gaps.resolve_contradiction(self.conn, outcome["tension_id"])
        self.assertEqual(resolved["resolution"],
                         {"winner": "version_b", "criterion": "autorite"})

    def test_escalation_to_human_when_nothing_discriminates(self):
        version_a = dict(self.version_a, score=0.7, authority=2)
        version_b = dict(self.version_b, score=0.7, authority=2)
        outcome = self._declare(version_a, version_b)

        resolved = gaps.resolve_contradiction(self.conn, outcome["tension_id"])
        self.assertEqual(resolved["resolution"]["criterion"], "escalade-humaine")
        self.assertIsNone(resolved["resolution"]["winner"])
        tension = graph_engine.get_object(self.conn, outcome["tension_id"])
        self.assertEqual(tension["state"], "escalade-humaine")

    def test_resolution_is_traced_by_a_contradiction_resolved_event(self):
        """DoD : resolution tracee."""
        outcome = self._declare()
        resolved = gaps.resolve_contradiction(self.conn, outcome["tension_id"])

        row = self.conn.execute(
            "SELECT type, payload_json FROM events WHERE event_id = ?",
            (resolved["event_id"],),
        ).fetchone()
        self.assertEqual(row[0], "SYSTEM.ContradictionResolved")
        payload = json.loads(row[1])["payload"]
        self.assertEqual(payload["resolution"]["criterion"], "preuve")
        self.assertEqual(payload["version_a"]["value"], "542,80")
        self.assertEqual(payload["version_b"]["value"], "544,00")


if __name__ == "__main__":
    unittest.main()
