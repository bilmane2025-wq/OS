"""Tests T-M25-1..4 : les vues (instantanee, quotidienne, acces absolu,
inbox).

DoD T-M25-1 : rendu teste avec 0 et avec 3 alertes ; silence par defaut ;
un estime n'a jamais l'apparence d'un fait. DoD T-M25-2 : priorites
triees par impact x urgence. DoD T-M25-3 : navigation KPI -> preuve.
DoD T-M25-4 : affichage du journal d'ingestion.
"""
import os
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from calc import kpi_catalog  # noqa: E402
from core import event_store, rules  # noqa: E402
from experience import views  # noqa: E402
from perception import dedup  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


def _anomaly(conn, severity="haute", impact=100.0, type_="test/anomalie"):
    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        "INSERT INTO anomalies (anomaly_id, type, severity, probability, impact, "
        "recommendation, state, created_at, refs_json) VALUES (?, ?, ?, 1.0, ?, ?, "
        "'ouverte', '2028-04-01T00:00:00Z', '{}')",
        (anomaly_id, type_, severity, impact, f"Corriger {type_}"))
    conn.commit()
    return anomaly_id


class ViewsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_views.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)
        rules.load_seed_rules(self.conn)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class InstantViewTests(ViewsTestCase):
    def test_zero_alerts_silence_by_default(self):
        """DoD : rendu avec 0 alerte - le succes est une seule phrase,
        rien d'autre n'est montre."""
        view = views.instant(self.conn)
        self.assertEqual(view["phrase"], "Tout est sous contrôle.")
        self.assertEqual(view["alerts"], [])

        rendered = views.render_instant(self.conn)
        self.assertIn("Tout est sous contrôle.", rendered)
        self.assertNotIn("alerte", rendered.split("</p>")[0])

    def test_three_alerts_are_shown_never_more(self):
        """DoD : rendu avec 3 alertes - et jamais plus de 3 meme s'il y a
        davantage d'anomalies."""
        for i in range(5):
            _anomaly(self.conn, type_=f"test/anomalie-{i}")

        view = views.instant(self.conn)
        self.assertEqual(len(view["alerts"]), 3)
        self.assertIn("attention", view["phrase"])

        rendered = views.render_instant(self.conn)
        self.assertEqual(rendered.count('class="alerte'), 3)

    def test_estimated_tresorerie_never_looks_like_a_fact(self):
        make_event(self.conn, "PERCEPTION.StatementLine",
                   {"record": {"date": "2028-04-01", "montant": "50,00",
                               "contrepartie": "X", "libelle": "y"}}, 1,
                   nature="estimé", score=0.4)
        kpi_catalog.compute(self.conn, "tresorerie")

        view = views.instant(self.conn)
        self.assertIn("[estimé]", view["tresorerie"])  # marquage distinct

    def test_factual_tresorerie_carries_no_estimate_tag(self):
        make_event(self.conn, "PERCEPTION.StatementLine",
                   {"record": {"date": "2028-04-01", "montant": "50,00",
                               "contrepartie": "X", "libelle": "y"}}, 1)
        kpi_catalog.compute(self.conn, "tresorerie")
        view = views.instant(self.conn)
        self.assertNotIn("[", view["tresorerie"])


class DailyViewTests(ViewsTestCase):
    def test_priorities_are_sorted_by_impact_times_urgency(self):
        """DoD T-M25-2 : priorites triees par impact x urgence."""
        low = _anomaly(self.conn, severity="douce", impact=10.0, type_="basse")
        high = _anomaly(self.conn, severity="haute", impact=1000.0, type_="critique")
        medium = _anomaly(self.conn, severity="moyenne", impact=50.0, type_="moyenne")
        _anomaly(self.conn, severity="douce", impact=1.0, type_="negligeable")

        view = views.daily(self.conn)

        self.assertEqual(len(view["priorites"]), 3)  # 3 priorites max
        self.assertEqual([p["anomaly_id"] for p in view["priorites"]],
                         [high, medium, low])

    def test_daily_shows_yesterday_result_with_confidence(self):
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "C1", "montant": "60,00"}}, 1)
        kpi_catalog.compute_all(self.conn)

        view = views.daily(self.conn)
        self.assertIn("60.00 EUR", view["resultat"]["ca"])
        rendered = views.render_daily(self.conn)
        self.assertIn("priorité", rendered)


class DetailViewTests(ViewsTestCase):
    def test_navigation_from_kpi_to_proof(self):
        """DoD T-M25-3 : navigation KPI -> preuve (chaque chiffre est une
        porte)."""
        make_event(self.conn, "PERCEPTION.OrderObserved",
                   {"record": {"commande_id": "C1", "montant": "60,00"}}, 1)
        kpi_catalog.compute(self.conn, "ca")

        view = views.detail(self.conn, kpi_name="ca")
        self.assertEqual(view["kind"], "kpi")
        self.assertEqual(len(view["unfolded"]["events"]), 1)
        self.assertEqual(view["unfolded"]["events"][0]["source"], "inbox/test")

        rendered = views.render_detail(self.conn, "ca")
        self.assertIn("kpi/ca@1", rendered)
        self.assertIn("inbox/test", rendered)  # jusqu'au fichier d'origine


class InboxViewTests(ViewsTestCase):
    def test_each_deposit_is_visible_with_its_status(self):
        """DoD T-M25-4 : affichage du journal d'ingestion."""
        dedup.record_ingestion(
            self.conn, "ING:1", source="inbox", file="releve.csv", hash_="a" * 64,
            records=3, new_records=2, duplicates=1, anomalies=0, errors=0,
            status="processed", ts="2028-04-01T00:00:00Z")
        dedup.record_ingestion(
            self.conn, "ING:2", source="inbox", file="mystere.docx", hash_="b" * 64,
            records=1, new_records=0, duplicates=0, anomalies=1, errors=0,
            status="quarantined", ts="2028-04-02T00:00:00Z")

        view = views.inbox_view(self.conn)
        self.assertEqual(len(view["ingestions"]), 2)
        statuses = {i["file"]: i["status"] for i in view["ingestions"]}
        self.assertEqual(statuses, {"releve.csv": "processed",
                                    "mystere.docx": "quarantined"})

        rendered = views.render_inbox(self.conn)
        self.assertIn("releve.csv", rendered)
        self.assertIn("quarantined", rendered)


if __name__ == "__main__":
    unittest.main()
