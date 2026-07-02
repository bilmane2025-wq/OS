"""Tests T-M13-1 : algebre de confiance.

Criteres backlog : aucune valeur nue ; un KPI issu d'estimation est
etiquete estimation. DoD : test des regles de propagation.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calc import confidence  # noqa: E402


class NatureOrderTests(unittest.TestCase):
    def test_the_five_natures_in_strength_order(self):
        self.assertEqual(confidence.NATURE_ORDER,
                         ("fait", "mesuré", "estimé", "hypothèse", "projection"))

    def test_weakest_of_fait_and_estime_is_estime(self):
        self.assertEqual(confidence.weakest_nature(["fait", "estimé"]), "estimé")

    def test_a_single_projection_contaminates_everything(self):
        self.assertEqual(
            confidence.weakest_nature(["fait", "fait", "mesuré", "projection"]),
            "projection")

    def test_all_fait_stays_fait(self):
        self.assertEqual(confidence.weakest_nature(["fait", "fait"]), "fait")

    def test_empty_collection_is_hypothese_never_a_silent_fact(self):
        self.assertEqual(confidence.weakest_nature([]), "hypothèse")

    def test_unknown_nature_is_rejected(self):
        with self.assertRaises(confidence.ConfidenceError):
            confidence.weakest_nature(["fait", "deviné"])


class ScoreTests(unittest.TestCase):
    def test_combined_score_is_the_minimum(self):
        self.assertEqual(confidence.combine_scores([1.0, 0.4, 0.8]), 0.4)

    def test_empty_scores_yield_zero(self):
        self.assertEqual(confidence.combine_scores([]), 0.0)


class CombineTests(unittest.TestCase):
    """DoD : regles de propagation - somme -> min des confiances ;
    estimation reste estimation."""

    def test_combination_carries_weakest_nature_and_lowest_score(self):
        result = confidence.combine([("fait", 1.0), ("estimé", 0.6), ("fait", 0.9)])
        self.assertEqual(result, {"nature": "estimé", "score": 0.6})

    def test_estimation_never_becomes_a_fact_by_aggregation(self):
        result = confidence.combine([("estimé", 0.5)] * 100)
        self.assertEqual(result["nature"], "estimé")

    def test_no_naked_value_output_always_has_nature_and_score(self):
        for items in ([], [("fait", 1.0)], [("projection", 0.1), ("fait", 1.0)]):
            with self.subTest(items=items):
                result = confidence.combine(items)
                self.assertIn("nature", result)
                self.assertIn("score", result)
                self.assertIn(result["nature"], confidence.NATURE_ORDER)

    def test_empty_combination_is_hypothese_zero(self):
        self.assertEqual(confidence.combine([]), {"nature": "hypothèse", "score": 0.0})

    def test_invalid_nature_in_any_term_is_rejected(self):
        with self.assertRaises(confidence.ConfidenceError):
            confidence.combine([("fait", 1.0), ("inventé", 0.5)])


if __name__ == "__main__":
    unittest.main()
