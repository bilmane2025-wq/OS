"""Tests T-M11-1 : le trou est un Objet (gaps.declare / gaps.resolve).

Critere backlog : une donnee attendue absente devient un trou visible,
jamais un zero muet. DoD : test trou cree, puis resolu a l'arrivee du
reel.
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

EXPECTED = {
    "label": "Releve bancaire d'avril 2028",
    "expected_type": "PERCEPTION.StatementLine",
    "expected_source": "banque (export CSV)",
    "due": "2028-05-05T00:00:00Z",
}


class GapsTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_gaps.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_declare_creates_a_visible_gap_object(self):
        outcome = gaps.declare(self.conn, EXPECTED)

        gap = graph_engine.get_object(self.conn, outcome["gap_id"])
        self.assertIsNotNone(gap)  # jamais un zero muet : le trou existe
        self.assertEqual(gap["type"], "Trou")
        self.assertEqual(gap["state"], "ouvert")
        self.assertEqual(gap["body"]["expected_source"], "banque (export CSV)")
        # L'inconnu est etiquete comme tel, pas comme un fait.
        self.assertEqual(gap["envelope"]["confidence"]["nature"], "hypothèse")

    def test_declare_writes_a_gap_detected_event(self):
        outcome = gaps.declare(self.conn, EXPECTED)
        (type_,) = self.conn.execute(
            "SELECT type FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        self.assertEqual(type_, "SYSTEM.GapDetected")

    def test_declare_creates_a_soft_anomaly(self):
        outcome = gaps.declare(self.conn, EXPECTED)
        row = self.conn.execute(
            "SELECT type, severity, state FROM anomalies WHERE anomaly_id = ?",
            (outcome["anomaly_id"],),
        ).fetchone()
        self.assertEqual(row, ("gap/donnee-attendue-absente", "douce", "ouverte"))

    def test_gap_is_resolved_when_the_real_data_arrives(self):
        """DoD : trou cree, puis resolu a l'arrivee du reel."""
        declared = gaps.declare(self.conn, EXPECTED)

        real_event = make_event(self.conn, "PERCEPTION.StatementLine",
                                {"record": {"date": "2028-04-30", "montant": "100",
                                            "contrepartie": "X", "libelle": "releve"}}, 9)
        graph_engine.apply(self.conn, real_event)

        gaps.resolve(self.conn, declared["gap_id"], real_event["event_id"])

        gap = graph_engine.get_object(self.conn, declared["gap_id"])
        self.assertEqual(gap["state"], "resolu")
        self.assertEqual(gap["body"]["resolu_par"], real_event["event_id"])
        # Le trou n'est jamais supprime (loi 2) : il reste, a l'etat resolu.
        self.assertIsNotNone(gap)

        anomaly_state = self.conn.execute(
            "SELECT state FROM anomalies WHERE anomaly_id = ?",
            (declared["anomaly_id"],),
        ).fetchone()[0]
        self.assertEqual(anomaly_state, "resolue")

    def test_resolution_is_traced_in_the_journal(self):
        declared = gaps.declare(self.conn, EXPECTED)
        outcome = gaps.resolve(self.conn, declared["gap_id"], "EVT:REEL")

        (payload_json,) = self.conn.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", (outcome["event_id"],)
        ).fetchone()
        payload = json.loads(payload_json)["payload"]
        self.assertEqual(payload["gap_id"], declared["gap_id"])
        self.assertEqual(payload["resolved_by_event"], "EVT:REEL")

    def test_resolving_an_unknown_gap_raises(self):
        with self.assertRaises(LookupError):
            gaps.resolve(self.conn, "TROU:EOS:404", "EVT:X")


if __name__ == "__main__":
    unittest.main()
