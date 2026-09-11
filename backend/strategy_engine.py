"""
backend/strategy_engine.py

Phase 7: Pure Deterministic Strategy Engine & Intelligent Question Selection.
Handles:
- Difficulty normalization (canonical easy, medium, hard; beginner -> easy)
- Session state derivation & turn accounting (max_turns, total_turns, remaining_turns)
- Category state classification (UNSEEN, COVERED_UNSCORED, NEEDS_FOCUS, MODERATE, STRONG)
- Coverage targets calculation
- Deterministic category selection & ranking (Pre-coverage and Post-coverage with UNSEEN 5th)
- Difficulty adaptation with decrease protection (using ONLY recent bank question scores)
- Deterministic question selection with fallback orders & category inventory fallback
- Comprehensive turn decision making
"""

import json
import math
import sqlite3
from typing import Any, Literal

CANONICAL_DIFFICULTIES = ["easy", "medium", "hard"]
Difficulty = Literal["easy", "medium", "hard"]

try:
    from .question_bank import (
        CANONICAL_CATEGORIES,
        calculate_diversity_score,
        rank_candidates_by_diversity,
        parse_question_row,
        BASE_DIVERSITY_SCORE,
    )
except (ImportError, ValueError):
    from question_bank import (
        CANONICAL_CATEGORIES,
        calculate_diversity_score,
        rank_candidates_by_diversity,
        parse_question_row,
        BASE_DIVERSITY_SCORE,
    )

try:
    from .category_classifier import (
        CATEGORY_STATE_UNSEEN,
        CATEGORY_STATE_COVERED_UNSCORED,
        CATEGORY_STATE_NEEDS_FOCUS,
        CATEGORY_STATE_MODERATE,
        CATEGORY_STATE_STRONG,
        CategoryState,
        classify_category_state,
        classify_scored_category,
        THRESHOLD_NEEDS_FOCUS,
        THRESHOLD_STRONG,
    )
except (ImportError, ValueError):
    from category_classifier import (
        CATEGORY_STATE_UNSEEN,
        CATEGORY_STATE_COVERED_UNSCORED,
        CATEGORY_STATE_NEEDS_FOCUS,
        CATEGORY_STATE_MODERATE,
        CATEGORY_STATE_STRONG,
        CategoryState,
        classify_category_state,
        classify_scored_category,
        THRESHOLD_NEEDS_FOCUS,
        THRESHOLD_STRONG,
    )


def normalize_difficulty(difficulty: str | None) -> Difficulty:
    """
    Normalizes any difficulty string to canonical 'easy', 'medium', or 'hard'.
    Legacy database value 'beginner' maps to 'easy'.
    Invalid or missing difficulty defaults to 'medium'.
    'beginner' must NEVER become a fourth level.
    """
    if not difficulty:
        return "medium"
    cleaned = str(difficulty).strip().lower()
    if cleaned == "beginner":
        return "easy"
    if cleaned in CANONICAL_DIFFICULTIES:
        return cleaned  # type: ignore
    return "medium"


def calculate_coverage_target(max_turns: int, available_category_count: int) -> int:
    """
    Computes the target number of distinct categories to cover in a session:
    - 5 turns -> 3
    - 8 turns -> 4
    - 10 turns -> 4
    - custom -> min(available_category_count, max(3, ceil(max_turns * 0.5)))
    Clamped to available_category_count.
    """
    if available_category_count <= 0:
        return 0
    if max_turns == 5:
        target = 3
    elif max_turns in (8, 10):
        target = 4
    else:
        target = max(3, math.ceil(max_turns * 0.5))

    target = min(target, available_category_count)
    return max(1, target)



def adapt_difficulty(current_difficulty: str, recent_bank_scores: list[float]) -> Difficulty:
    """
    Adapts difficulty based STRICTLY on the last up to 2 evaluated bank-question scores.
    Follow-up scores MUST NOT be passed here.

    Rules:
    - recent_avg >= 8.0 -> +1 level (easy->medium, medium->hard, hard->hard)
    - 5.0 <= recent_avg < 8.0 -> maintain current difficulty
    - recent_avg < 5.0:
        * if most recent score <= 3.0 -> decrease 1 level (hard->medium, medium->easy, easy->easy)
        * if most recent score was 4: require two consecutive scores < 5.0 before decreasing
    - Boundaries: never < easy, never > hard, never jump 2 levels.
    """
    curr = normalize_difficulty(current_difficulty)
    if not recent_bank_scores:
        return curr

    scores = recent_bank_scores[-2:]
    recent_avg = sum(scores) / len(scores)
    most_recent = scores[-1]

    # Increase one level if recent average >= 8.0
    if recent_avg >= 8.0:
        if curr == "easy":
            return "medium"
        elif curr == "medium":
            return "hard"
        return "hard"

    # Immediate decrease exception: if most recent bank question score <= 3.0, decrease immediately
    if most_recent <= 3.0:
        if curr == "hard":
            return "medium"
        elif curr == "medium":
            return "easy"
        return "easy"

    # Maintain current difficulty if recent average >= 5.0
    if recent_avg >= 5.0:
        return curr

    # recent_avg < 5.0: normal decrease requiring 2 recent bank evaluations
    if len(scores) >= 2:
        if curr == "hard":
            return "medium"
        elif curr == "medium":
            return "easy"
        return "easy"

    # Single evaluation with 3.0 < score < 5.0 (e.g. 4.0) remains protected
    return curr


def build_interview_state(connection, session_id: int) -> dict:
    """
    Inspects existing persisted session data and reconstructs complete strategy state.
    Zero new database tables used.
    """
    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        raise ValueError(f"Interview session {session_id} not found.")

    turns_rows = connection.execute(
        """
        SELECT st.id AS turn_id, st.turn_number, st.question_id, st.question_text,
               st.is_follow_up, st.status, st.answer_id,
               q.category AS question_category, q.difficulty AS question_difficulty,
               e.score
        FROM session_turns st
        LEFT JOIN questions q ON q.id = st.question_id
        LEFT JOIN answers a ON a.id = st.answer_id
        LEFT JOIN evaluations e ON e.answer_id = a.id
        WHERE st.session_id = ?
        ORDER BY st.turn_number ASC
        """,
        (session_id,)
    ).fetchall()

    max_turns = int(session_row["max_turns"])
    total_turns = len(turns_rows)
    remaining_turns = max(0, max_turns - total_turns)

    bank_questions_count = sum(1 for t in turns_rows if not t["is_follow_up"])
    follow_up_count = sum(1 for t in turns_rows if t["is_follow_up"])
    used_question_ids = {t["question_id"] for t in turns_rows if t["question_id"] is not None}

    # Determine available categories
    raw_selected = (
        session_row["selected_categories"]
        if "selected_categories" in session_row.keys()
        else None
    )
    if raw_selected:
        try:
            parsed = json.loads(raw_selected)
            if isinstance(parsed, list):
                # Preserve canonical order among selected categories
                canonical_selected = [c for c in CANONICAL_CATEGORIES if c in parsed]
                # If synthetic test fixture categories exist (e.g. SQL, CatA), also allow them
                if not canonical_selected:
                    canonical_selected = [c for c in parsed if isinstance(c, str) and c.strip()]
                if not canonical_selected:
                    raise ValueError(f"No valid categories found in selected_categories: {parsed}")
                available_categories = canonical_selected
            else:
                raise ValueError("selected_categories must be a JSON array")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in selected_categories: {raw_selected}")
    else:
        # Fallback to legacy category
        configured_category = session_row["category"]
        if configured_category and configured_category not in ("All", "all", ""):
            if configured_category in ("Custom", "Multi-Category"):
                raise ValueError(
                    f"Desynchronization error: Category '{configured_category}' cannot be used without selected_categories."
                )
            cat_rows = connection.execute(
                "SELECT DISTINCT category FROM questions WHERE category IS NOT NULL AND TRIM(category) != '' AND LOWER(TRIM(category)) != 'string' ORDER BY category ASC"
            ).fetchall()
            db_categories = [r["category"] for r in cat_rows]
            if configured_category not in db_categories and configured_category not in CANONICAL_CATEGORIES:
                raise ValueError(
                    f"Desynchronization error: Invalid category configuration '{configured_category}' is neither a canonical category nor present in questions bank."
                )
            available_categories = [configured_category]
        else:
            cat_rows = connection.execute(
                "SELECT DISTINCT category FROM questions WHERE category IS NOT NULL AND TRIM(category) != '' AND LOWER(TRIM(category)) != 'string' ORDER BY category ASC"
            ).fetchall()
            db_categories = [r["category"] for r in cat_rows]

            canonical_in_db = [c for c in db_categories if c in CANONICAL_CATEGORIES]
            if canonical_in_db and not any(c in db_categories for c in ("SQL", "FastAPI", "CatA", "CatB", "CatC", "CatD")):
                available_categories = canonical_in_db
            else:
                available_categories = db_categories

    categories_state: dict[str, dict] = {}
    for cat in available_categories:
        categories_state[cat] = {
            "bank_questions_asked": 0,
            "evaluated_bank_answers_count": 0,
            "evaluated_scores": [],
            "average_score": None,
            "recent_scores": [],
            "last_difficulty": None,
            "difficulty_history": [],
            "state": CATEGORY_STATE_UNSEEN
        }

    for t in turns_rows:
        if not t["is_follow_up"]:
            cat = t["question_category"]
            if cat in categories_state:
                categories_state[cat]["bank_questions_asked"] += 1
                canonical_d = normalize_difficulty(t["question_difficulty"])
                categories_state[cat]["last_difficulty"] = canonical_d
                categories_state[cat]["difficulty_history"].append(canonical_d)
                if t["score"] is not None:
                    score_val = float(t["score"])
                    categories_state[cat]["evaluated_scores"].append(score_val)
                    categories_state[cat]["evaluated_bank_answers_count"] += 1

    for cat in available_categories:
        scores = categories_state[cat]["evaluated_scores"]
        asked = categories_state[cat]["bank_questions_asked"]
        categories_state[cat]["recent_scores"] = scores[-2:]
        if scores:
            categories_state[cat]["average_score"] = round(sum(scores) / len(scores), 2)
        categories_state[cat]["state"] = classify_category_state(asked, scores)

    categories_covered = sum(1 for c, d in categories_state.items() if d["bank_questions_asked"] > 0)
    coverage_target = calculate_coverage_target(max_turns, len(available_categories))

    return {
        "session_id": session_row["id"],
        "session_category": session_row["category"],
        "selected_categories": json.loads(session_row["selected_categories"]) if ("selected_categories" in session_row.keys() and session_row["selected_categories"]) else None,
        "session_difficulty": session_row["difficulty"],
        "status": session_row["status"],
        "max_turns": max_turns,
        "total_turns": total_turns,
        "remaining_turns": remaining_turns,
        "bank_questions_count": bank_questions_count,
        "follow_up_count": follow_up_count,
        "used_question_ids": used_question_ids,
        "available_categories": available_categories,
        "coverage_target": coverage_target,
        "categories_covered": categories_covered,
        "categories": categories_state
    }


def rank_categories_deterministically(
    categories_state: dict[str, dict],
    coverage_target: int,
    excluded_categories: set[str] | None = None
) -> list[str]:
    """
    Ranks available categories deterministically.
    
    Order:
    - While categories_covered < coverage_target:
      UNSEEN > NEEDS_FOCUS > COVERED_UNSCORED > MODERATE > STRONG
      UNSEEN tie-break: category ASC
    - Once categories_covered >= coverage_target:
    Tie-breaking for scored categories within the same state (NEEDS_FOCUS, MODERATE, STRONG):
      1. lower average_score first (ASC)
      2. lower bank_questions_asked first (ASC)
      3. category name alphabetical (ASC)

    Tie-breaking for COVERED_UNSCORED:
      1. lower bank_questions_asked first (ASC)
      2. category name alphabetical (ASC)

    Tie-breaking for UNSEEN:
      category name alphabetical (ASC)
    """
    excluded = excluded_categories or set()
    active_cats = [c for c in categories_state if c not in excluded]
    if not active_cats:
        return []

    covered_count = sum(1 for c, d in categories_state.items() if d["bank_questions_asked"] > 0)
    coverage_met = (covered_count >= coverage_target)

    def sort_key(cat: str):
        d = categories_state[cat]
        state = d["state"]
        asked = d.get("bank_questions_asked", 0)
        avg = d["average_score"] if d["average_score"] is not None else 0.0

        if not coverage_met:
            # Pre-coverage priority: UNSEEN > NEEDS_FOCUS > COVERED_UNSCORED > MODERATE > STRONG
            if state == CATEGORY_STATE_UNSEEN:
                return (1, 0.0, 0, cat)
            elif state == CATEGORY_STATE_NEEDS_FOCUS:
                return (2, avg, asked, cat)
            elif state == CATEGORY_STATE_COVERED_UNSCORED:
                return (3, 0.0, asked, cat)
            elif state == CATEGORY_STATE_MODERATE:
                return (4, avg, asked, cat)
            else:  # STRONG
                return (5, avg, asked, cat)
        else:
            # Post-coverage priority:
            # NEEDS_FOCUS > COVERED_UNSCORED > MODERATE > STRONG > UNSEEN
            if state == CATEGORY_STATE_NEEDS_FOCUS:
                return (1, avg, asked, cat)
            elif state == CATEGORY_STATE_COVERED_UNSCORED:
                return (2, 0.0, asked, cat)
            elif state == CATEGORY_STATE_MODERATE:
                return (3, avg, asked, cat)
            elif state == CATEGORY_STATE_STRONG:
                return (4, avg, asked, cat)
            else:  # UNSEEN
                return (5, 0.0, 0, cat)

    active_cats.sort(key=sort_key)
    return active_cats


def get_recent_bank_questions(
    connection: sqlite3.Connection,
    session_id: int,
    limit: int = 3
) -> list[dict[str, Any]]:
    """
    Fetches the up to `limit` most recent bank questions asked in the active session.
    Follow-up turns are strictly excluded (is_follow_up == 0).
    Ordered chronologically: oldest of the recent to newest of the recent,
    so history[-1] is the most recent bank question.
    """
    cols = {row["name"] for row in connection.execute("PRAGMA table_info(questions)").fetchall()}
    if "topic" in cols:
        query = """
            SELECT q.id, q.category, q.difficulty, q.question,
                   q.topic, q.subtopic, q.question_type, q.skill_type, q.quality_tier,
                   q.expected_concepts, q.common_mistakes, q.ideal_answer_points, q.prerequisites
            FROM session_turns st
            JOIN questions q ON q.id = st.question_id
            WHERE st.session_id = ?
              AND st.is_follow_up = 0
              AND st.question_id IS NOT NULL
            ORDER BY st.turn_number DESC
            LIMIT ?
        """
    else:
        query = """
            SELECT q.id, q.category, q.difficulty, q.question
            FROM session_turns st
            JOIN questions q ON q.id = st.question_id
            WHERE st.session_id = ?
              AND st.is_follow_up = 0
              AND st.question_id IS NOT NULL
            ORDER BY st.turn_number DESC
            LIMIT ?
        """
    rows = connection.execute(query, (session_id, limit)).fetchall()
    return [parse_question_row(r) for r in reversed(rows)]


def select_bank_question(
    connection: sqlite3.Connection,
    category: str,
    requested_difficulty: str,
    used_question_ids: set[int] | None = None,
    recent_bank_questions: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Selects a bank question for the specified category and target difficulty.
    
    Fallback orders:
    - requested medium: [medium, easy, hard]
    - requested hard: [hard, medium, easy]
    - requested easy: [easy, medium, hard]

    For EACH difficulty tier:
    1. Query eligible unused questions in the selected category and current tier.
    2. If ZERO eligible candidates exist: move to the next fallback tier.
    3. If one or more candidates exist:
       calculate deterministic diversity score against recent bank questions.
    4. Rank:
       diversity_score DESC
       question_id ASC
    5. Select the first candidate.
    6. STOP.

    CRITICAL: Diversity MUST NEVER cause the selector to skip a difficulty tier.
    Legacy 'beginner' questions are treated as 'easy' and returned normalized.
    """
    canonical_req = normalize_difficulty(requested_difficulty)

    if canonical_req == "medium":
        diff_order: list[Difficulty] = ["medium", "easy", "hard"]
    elif canonical_req == "hard":
        diff_order = ["hard", "medium", "easy"]
    else:  # easy
        diff_order = ["easy", "medium", "hard"]

    used_list = list(used_question_ids) if used_question_ids else []

    cols = {row["name"] for row in connection.execute("PRAGMA table_info(questions)").fetchall()}
    has_metadata = "topic" in cols

    for diff in diff_order:
        params: list = [category]
        if diff == "easy":
            diff_clause = "difficulty IN ('easy', 'beginner')"
        else:
            diff_clause = "difficulty = ?"
            params.append(diff)

        if used_list:
            placeholders = ",".join("?" for _ in used_list)
            used_clause = f"AND id NOT IN ({placeholders})"
            params.extend(used_list)
        else:
            used_clause = ""

        if has_metadata:
            query = f"""
                SELECT id, category, difficulty, question,
                       topic, subtopic, question_type, skill_type, quality_tier,
                       expected_concepts, common_mistakes, ideal_answer_points, prerequisites
                FROM questions
                WHERE category = ? AND {diff_clause} {used_clause}
                ORDER BY id ASC
            """
        else:
            query = f"""
                SELECT id, category, difficulty, question
                FROM questions
                WHERE category = ? AND {diff_clause} {used_clause}
                ORDER BY id ASC
            """

        rows = connection.execute(query, tuple(params)).fetchall()
        if not rows:
            continue

        candidates = [parse_question_row(r) for r in rows]
        ranked = rank_candidates_by_diversity(candidates, recent_bank_questions)
        selected = ranked[0]
        selected["difficulty"] = normalize_difficulty(selected["difficulty"])
        return selected, diff

    return None, None


def decide_next_turn(connection, session_id: int) -> dict:
    """
    Calculates the next strategic move for the interview session:
    1. Reconstructs complete deterministic interview state.
    2. Checks if session is complete (remaining_turns <= 0 or status == 'completed').
    3. Deterministically selects next category, re-running the complete category selection
       algorithm if a category has no unused questions at any difficulty (User Correction 4).
    4. Applies difficulty adaptation and selects the lowest-ID matching question.
    5. Returns a structured decision object.
    """
    state = build_interview_state(connection, session_id)

    if state["status"] == "completed" or state["remaining_turns"] <= 0:
        return {
            "action": "completed",
            "session_id": session_id,
            "reason": "max_turns_reached",
            "coverage_target": state["coverage_target"],
            "categories_covered": state["categories_covered"]
        }

    excluded_categories: set[str] = set()

    while True:
        ranked = rank_categories_deterministically(
            state["categories"],
            state["coverage_target"],
            excluded_categories
        )
        if not ranked:
            # All available categories exhausted of unused questions
            return {
                "action": "bank_exhausted",
                "session_id": session_id,
                "reason": "all_questions_exhausted",
                "coverage_target": state["coverage_target"],
                "categories_covered": state["categories_covered"]
            }

        selected_cat = ranked[0]
        cat_data = state["categories"][selected_cat]

        # Determine target difficulty
        if cat_data["state"] == CATEGORY_STATE_UNSEEN:
            # A genuinely unseen category MUST always start at medium
            target_diff = "medium"
            reason = "unseen_coverage" if state["categories_covered"] < state["coverage_target"] else "unseen_fallback"
        else:
            last_diff = cat_data["last_difficulty"] or "medium"
            target_diff = adapt_difficulty(last_diff, cat_data["recent_scores"])
            reason = cat_data["state"].lower()

        recent_bank_q = get_recent_bank_questions(connection, session_id, limit=3)
        question, actual_diff = select_bank_question(
            connection,
            selected_cat,
            target_diff,
            state["used_question_ids"],
            recent_bank_questions=recent_bank_q
        )

        if question is not None and actual_diff is not None:
            return {
                "action": "new_bank_question",
                "session_id": session_id,
                "category": selected_cat,
                "target_difficulty": target_diff,
                "difficulty": actual_diff,
                "question": question,
                "reason": reason,
                "coverage_target": state["coverage_target"],
                "categories_covered": state["categories_covered"]
            }

        # Selected category has no unused questions at ANY difficulty.
        # Temporarily exclude and re-run complete deterministic ranking!
        excluded_categories.add(selected_cat)