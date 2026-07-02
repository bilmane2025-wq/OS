"""Tests T-M26-1 : proactivite niveaux 1-2 (regles de seuil -> alertes
groupees).

Criteres backlog : pas d'alerte sur le non-actionnable ; regroupement.
DoD : test seuils.
"""
import os
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from calc import kpi_catalog  # noqa: E402
from core import event_store, rules  # noqa: E402
from experience import proactivity  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


def _anomaly(conn, type_, severity="moyenne"):
    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, type, severity, probability, impact, "
        "recommendation, state, created_at, refs_json) VALUES (?, ?, ?, 1.0, NULL, "
        "'Corriger.', 'ouverte', '2028-04-01T00:00:00Z', '{}')",
        (anomaly_id, type_, severity))
    conn.commit()
    return anomaly_id


class ProactivityTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_proactivity.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _set_tresorerie(self, amount):
        make_event(self.conn, "PERCEPTION.StatementLine",
                   {"record": {"date": "2028-04-01", "montant": amount,
                               "contrepartie": "X", "libelle": "solde"}},
                   int(float(amount.replace(",", "."))) % 28 + 1)
        kpi_catalog.compute(self.conn, "tresorerie")


class ThresholdTests(ProactivityTestCase):
    """DoD : test seuils (regle seed alert-threshold/tresorerie-basse,
    seuil 2000)."""

    def test_tresorerie_below_threshold_raises_a_grouped_alert(self):
        self._set_tresorerie("500,00")

        alerts = proactivity.threshold_alerts(self.conn)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "seuil/tresorerie")
        self.assertIn("500.00", alerts[0]["message"])
        self.assertIn("2000", alerts[0]["message"])
        self.assertTrue(alerts[0]["recommendation"])          # actionnable
        self.assertEqual(alerts[0]["rule"],
                         "alert-threshold/tresorerie-basse@1")  # regle tracee

    def test_tresorerie_above_threshold_stays_silent(self):
        self._set_tresorerie("5000,00")
        self.assertEqual(proactivity.threshold_alerts(self.conn), [])

    def test_unknown_kpi_value_never_alerts_non_actionable(self):
        """Critere backlog : pas d'alerte sur le non-actionnable - un KPI
        sans donnee ne declenche pas d'alerte de seuil."""
        kpi_catalog.compute(self.conn, "tresorerie")  # aucune donnee -> None
        self.assertEqual(proactivity.threshold_alerts(self.conn), [])

    def test_threshold_is_versioned_a_v2_changes_the_verdict(self):
        self._set_tresorerie("500,00")
        v1 = rules.get(self.conn, "alert-threshold/tresorerie-basse",
                       "2028-01-01T00:00:00Z")
        rules.add_version(self.conn, "alert-threshold/tresorerie-basse",
                          dict(v1["body"], seuil_montant=100),
                          valid_from="2028-06-01T00:00:00Z", origin="manual")

        before = proactivity.threshold_alerts(self.conn, "2028-05-01T00:00:00Z")
        after = proactivity.threshold_alerts(self.conn, "2028-07-01T00:00:00Z")
        self.assertEqual(len(before), 1)   # v1 : seuil 2000 -> alerte
        self.assertEqual(after, [])        # v2 : seuil 100 -> silence


class GroupingTests(ProactivityTestCase):
    def test_same_type_alerts_are_grouped_into_one_with_a_count(self):
        """Critere backlog : regroupement - 5 anomalies du meme type = 1
        sollicitation comptee, jamais une rafale."""
        for _ in range(5):
            _anomaly(self.conn, "quality/invalid-record")
        _anomaly(self.conn, "gap/donnee-attendue-absente", severity="douce")

        grouped = proactivity.group_alerts(proactivity.collect_alerts(self.conn))

        self.assertEqual(len(grouped), 2)
        by_type = {g["type"]: g for g in grouped}
        self.assertEqual(by_type["quality/invalid-record"]["count"], 5)
        self.assertEqual(len(by_type["quality/invalid-record"]["refs"]), 5)
        self.assertEqual(by_type["gap/donnee-attendue-absente"]["count"], 1)

    def test_groups_are_sorted_most_severe_first(self):
        _anomaly(self.conn, "type/doux", severity="douce")
        _anomaly(self.conn, "type/grave", severity="haute")

        grouped = proactivity.group_alerts(proactivity.collect_alerts(self.conn))
        self.assertEqual([g["type"] for g in grouped], ["type/grave", "type/doux"])

    def test_collect_merges_threshold_alerts_and_anomalies(self):
        self._set_tresorerie("500,00")
        _anomaly(self.conn, "quality/invalid-record")

        alerts = proactivity.collect_alerts(self.conn)
        types = {a["type"] for a in alerts}
        self.assertEqual(types, {"seuil/tresorerie", "quality/invalid-record"})


if __name__ == "__main__":
    unittest.main()
