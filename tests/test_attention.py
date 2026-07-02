"""Tests T-M27-1 : budget d'attention (plafond + dedup).

Criteres backlog : plafond respecte ; dedup des alertes. DoD : test
anti-fatigue.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experience import attention  # noqa: E402


def _alert(type_, severity="moyenne", refs=None):
    return {"type": type_, "severity": severity, "recommendation": "Corriger.",
            "refs": refs or [type_]}


class AttentionBudgetTests(unittest.TestCase):
    def test_cap_is_respected_never_more_than_the_budget(self):
        """DoD anti-fatigue : 10 sollicitations distinctes -> 3 montrees,
        7 comptees, aucune perdue silencieusement."""
        alerts = [_alert(f"type/{i}") for i in range(10)]

        outcome = attention.budget(alerts, cap=3)

        self.assertEqual(len(outcome["shown"]), 3)
        self.assertEqual(outcome["suppressed"], 7)
        self.assertEqual(outcome["total"], 10)

    def test_duplicates_are_deduplicated_before_the_cap(self):
        """Critere backlog : dedup - la meme alerte repetee ne consomme
        qu'une place du budget."""
        alerts = [_alert("seuil/tresorerie", refs=[f"ref-{i}"]) for i in range(4)]
        alerts.append(_alert("autre/type"))

        outcome = attention.budget(alerts, cap=3)

        self.assertEqual(outcome["total"], 2)  # 4 identiques -> 1 + 1 autre
        self.assertEqual(outcome["suppressed"], 0)
        merged = next(a for a in outcome["shown"] if a["type"] == "seuil/tresorerie")
        self.assertEqual(merged["refs"], ["ref-0", "ref-1", "ref-2", "ref-3"])

    def test_most_severe_alerts_win_the_budget(self):
        alerts = [_alert("doux/1", "douce"), _alert("doux/2", "douce"),
                  _alert("grave/1", "haute"), _alert("moyen/1", "moyenne"),
                  _alert("grave/2", "haute")]

        outcome = attention.budget(alerts, cap=3)
        shown_types = [a["type"] for a in outcome["shown"]]
        self.assertEqual(shown_types, ["grave/1", "grave/2", "moyen/1"])

    def test_dedup_keeps_the_highest_severity(self):
        alerts = [_alert("seuil/tresorerie", "douce"),
                  _alert("seuil/tresorerie", "haute")]
        outcome = attention.budget(alerts)
        self.assertEqual(outcome["shown"][0]["severity"], "haute")

    def test_empty_input_yields_empty_budget(self):
        outcome = attention.budget([])
        self.assertEqual(outcome, {"shown": [], "suppressed": 0, "total": 0})

    def test_zero_cap_shows_nothing_but_counts_everything(self):
        outcome = attention.budget([_alert("a"), _alert("b")], cap=0)
        self.assertEqual(outcome["shown"], [])
        self.assertEqual(outcome["suppressed"], 2)

    def test_negative_cap_is_rejected(self):
        with self.assertRaises(ValueError):
            attention.budget([], cap=-1)


if __name__ == "__main__":
    unittest.main()
