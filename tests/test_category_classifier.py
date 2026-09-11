"""
tests/test_category_classifier.py

Unit tests for backend/category_classifier.py
Verifies authoritative single-source-of-truth category performance state logic.
"""

import unittest
from backend.category_classifier import (
    CATEGORY_STATE_UNSEEN,
    CATEGORY_STATE_COVERED_UNSCORED,
    CATEGORY_STATE_NEEDS_FOCUS,
    CATEGORY_STATE_MODERATE,
    CATEGORY_STATE_STRONG,
    THRESHOLD_NEEDS_FOCUS,
    THRESHOLD_STRONG,
    TECH_STRONG_THRESHOLD,
    TECH_MODERATE_THRESHOLD,
    classify_scored_category,
    classify_category_state,
    compute_category_status,
)
from backend import strategy_engine
from backend import coaching
from backend import analytics


class TestCategoryClassifier(unittest.TestCase):
    def test_constants_and_thresholds(self):
        """Verify canonical constants and boundary thresholds."""
        self.assertEqual(CATEGORY_STATE_UNSEEN, "UNSEEN")
        self.assertEqual(CATEGORY_STATE_COVERED_UNSCORED, "COVERED_UNSCORED")
        self.assertEqual(CATEGORY_STATE_NEEDS_FOCUS, "NEEDS_FOCUS")
        self.assertEqual(CATEGORY_STATE_MODERATE, "MODERATE")
        self.assertEqual(CATEGORY_STATE_STRONG, "STRONG")

        self.assertEqual(THRESHOLD_NEEDS_FOCUS, 6.0)
        self.assertEqual(THRESHOLD_STRONG, 7.0)
        self.assertEqual(TECH_STRONG_THRESHOLD, 7.0)
        self.assertEqual(TECH_MODERATE_THRESHOLD, 6.0)

    def test_classify_scored_category(self):
        """Verify pure score-to-state classification boundaries."""
        # Needs focus: < 6.0
        self.assertEqual(classify_scored_category(0.0), "NEEDS_FOCUS")
        self.assertEqual(classify_scored_category(5.9), "NEEDS_FOCUS")
        self.assertEqual(classify_scored_category(5.999), "NEEDS_FOCUS")

        # Moderate: 6.0 <= avg < 7.0
        self.assertEqual(classify_scored_category(6.0), "MODERATE")
        self.assertEqual(classify_scored_category(6.5), "MODERATE")
        self.assertEqual(classify_scored_category(6.999), "MODERATE")

        # Strong: >= 7.0
        self.assertEqual(classify_scored_category(7.0), "STRONG")
        self.assertEqual(classify_scored_category(8.5), "STRONG")
        self.assertEqual(classify_scored_category(10.0), "STRONG")

    def test_classify_category_state_unseen(self):
        """0 bank questions asked is UNSEEN regardless of score list."""
        self.assertEqual(classify_category_state(0, []), "UNSEEN")
        self.assertEqual(classify_category_state(0, [8.0]), "UNSEEN")

    def test_classify_category_state_covered_unscored(self):
        """>= 1 bank questions asked but no evaluated scores is COVERED_UNSCORED."""
        self.assertEqual(classify_category_state(1, []), "COVERED_UNSCORED")
        self.assertEqual(classify_category_state(2, []), "COVERED_UNSCORED")

    def test_classify_category_state_single_score(self):
        """Single evaluated bank score uses that score for classification."""
        self.assertEqual(classify_category_state(1, [5.9]), "NEEDS_FOCUS")
        self.assertEqual(classify_category_state(1, [6.0]), "MODERATE")
        self.assertEqual(classify_category_state(1, [6.9]), "MODERATE")
        self.assertEqual(classify_category_state(1, [7.0]), "STRONG")

    def test_classify_category_state_recent_two_window(self):
        """Multiple scores strictly use the most recent 2 scores."""
        # 2 scores
        self.assertEqual(classify_category_state(2, [3.0, 5.0]), "NEEDS_FOCUS")
        self.assertEqual(classify_category_state(2, [6.2, 6.8]), "MODERATE")
        self.assertEqual(classify_category_state(2, [8.0, 9.5]), "STRONG")

        # 3 scores (first score 9.0 ignored, last 2 are 9.0, 4.0 -> avg 6.5)
        self.assertEqual(classify_category_state(3, [9.0, 9.0, 4.0]), "MODERATE")
        # last 2 are 9.0, 7.0 -> avg 8.0
        self.assertEqual(classify_category_state(3, [9.0, 9.0, 7.0]), "STRONG")
        # last 2 are 4.0, 5.0 -> avg 4.5
        self.assertEqual(classify_category_state(3, [9.0, 4.0, 5.0]), "NEEDS_FOCUS")

    def test_compute_category_status(self):
        """Phase 6/9 lowercase category status helper."""
        self.assertEqual(compute_category_status(8.5), "strong")
        self.assertEqual(compute_category_status(7.0), "strong")
        self.assertEqual(compute_category_status(6.9), "moderate")
        self.assertEqual(compute_category_status(6.0), "moderate")
        self.assertEqual(compute_category_status(5.9), "needs_focus")
        self.assertEqual(compute_category_status(1.0), "needs_focus")

    def test_strategy_engine_integration(self):
        """Verify strategy_engine re-exports and utilizes shared logic."""
        self.assertEqual(strategy_engine.classify_category_state(0, []), "UNSEEN")
        self.assertEqual(strategy_engine.classify_category_state(1, []), "COVERED_UNSCORED")
        self.assertEqual(strategy_engine.classify_category_state(1, [5.9]), "NEEDS_FOCUS")
        self.assertEqual(strategy_engine.classify_category_state(1, [6.5]), "MODERATE")
        self.assertEqual(strategy_engine.classify_category_state(1, [7.5]), "STRONG")
        self.assertEqual(strategy_engine.CATEGORY_STATE_UNSEEN, CATEGORY_STATE_UNSEEN)
        self.assertEqual(strategy_engine.CATEGORY_STATE_STRONG, CATEGORY_STATE_STRONG)

    def test_coaching_integration(self):
        """Verify coaching re-exports and utilizes shared logic."""
        self.assertEqual(coaching.compute_category_status(8.5), "strong")
        self.assertEqual(coaching.compute_category_status(6.5), "moderate")
        self.assertEqual(coaching.compute_category_status(5.5), "needs_focus")
        self.assertEqual(coaching.TECH_STRONG_THRESHOLD, TECH_STRONG_THRESHOLD)
        self.assertEqual(coaching.TECH_MODERATE_THRESHOLD, TECH_MODERATE_THRESHOLD)

    def test_analytics_integration(self):
        """Verify analytics delegates _compute_category_status to shared logic."""
        self.assertEqual(analytics._compute_category_status(8.5), "strong")
        self.assertEqual(analytics._compute_category_status(6.5), "moderate")
        self.assertEqual(analytics._compute_category_status(5.5), "needs_focus")


if __name__ == "__main__":
    unittest.main()
