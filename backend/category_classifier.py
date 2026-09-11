"""
backend/category_classifier.py

Authoritative shared classification for interview category performance states.
Single source of truth shared across Phase 7 (Strategy Engine), Phase 9 (Coaching),
and Phase 6 (Analytics). Pure leaf module with zero internal dependencies to prevent circular imports.
"""

from typing import Literal

# Canonical Category State Constants (Phase 7 canonical uppercase strings)
CATEGORY_STATE_UNSEEN = "UNSEEN"
CATEGORY_STATE_COVERED_UNSCORED = "COVERED_UNSCORED"
CATEGORY_STATE_NEEDS_FOCUS = "NEEDS_FOCUS"
CATEGORY_STATE_MODERATE = "MODERATE"
CATEGORY_STATE_STRONG = "STRONG"

CategoryState = Literal[
    "UNSEEN",
    "COVERED_UNSCORED",
    "NEEDS_FOCUS",
    "MODERATE",
    "STRONG"
]

# Canonical Threshold Boundaries
THRESHOLD_NEEDS_FOCUS = 6.0
THRESHOLD_STRONG = 7.0
TECH_STRONG_THRESHOLD = 7.0
TECH_MODERATE_THRESHOLD = 6.0


def classify_scored_category(average: float) -> str:
    """
    Pure score-to-state classifier for evaluated categories:
    - average < 6.0        -> "NEEDS_FOCUS"
    - 6.0 <= average < 7.0 -> "MODERATE"
    - average >= 7.0       -> "STRONG"
    """
    if average < THRESHOLD_NEEDS_FOCUS:
        return CATEGORY_STATE_NEEDS_FOCUS
    elif average < THRESHOLD_STRONG:
        return CATEGORY_STATE_MODERATE
    else:
        return CATEGORY_STATE_STRONG


def classify_category_state(bank_questions_asked: int, evaluated_bank_scores: list[float]) -> str:
    """
    Classifies category state from question count and evaluated score history:
    - UNSEEN: bank_questions_asked == 0
    - COVERED_UNSCORED: bank_questions_asked > 0 and len(evaluated_bank_scores) == 0
    - Scored: evaluated on recent-2 bank scores via classify_scored_category()
    """
    if bank_questions_asked == 0:
        return CATEGORY_STATE_UNSEEN

    if not evaluated_bank_scores:
        return CATEGORY_STATE_COVERED_UNSCORED

    recent = evaluated_bank_scores[-2:]
    avg = sum(recent) / len(recent)
    return classify_scored_category(avg)


def compute_category_status(avg_score: float) -> str:
    """
    Phase 9 canonical category status helper (lowercase):
    Returns 'needs_focus', 'moderate', or 'strong'.
    """
    return classify_scored_category(avg_score).lower()
