"""
backend/analytics.py

Pure deterministic analytics and progress tracking calculations for completed
interview sessions in the AI Interview Simulator.

All metrics are calculated directly from atomic persisted records without
creating redundant summary tables or introducing blended overall scores.
"""

import sqlite3
from typing import Any

try:
    from .category_classifier import compute_category_status
except (ImportError, ValueError):
    from category_classifier import compute_category_status


def _resolve_effective_category(
    direct_category: str | None,
    parent_category: str | None,
    session_category: str | None
) -> str:
    """
    Resolves the category of a turn according to Section 4:
    follow-up turn -> parent_turn_id -> parent session_turn -> parent question_id -> questions.category
    If that cannot be resolved, use the session category as the final fallback.
    """
    if direct_category and direct_category.strip():
        return direct_category.strip()
    if parent_category and parent_category.strip():
        return parent_category.strip()
    if session_category and session_category.strip():
        return session_category.strip()
    return "General"


def _calculate_dimension_change(
    chronological_sessions: list[dict[str, Any]],
    score_key: str
) -> tuple[float | None, int | None, int | None]:
    """
    Calculates the first vs latest percentage change for a specific dimension independently.
    Only sessions with non-null values for score_key are eligible.
    If fewer than 2 eligible completed sessions exist, percentage change = null.
    Otherwise: ((latest_score - first_score) / first_score) * 100, rounded to 1 decimal place.
    If first_score == 0: percentage change = null.
    Returns: (percent_change, first_session_id, latest_session_id)
    """
    eligible = [s for s in chronological_sessions if s.get(score_key) is not None]
    if len(eligible) < 2:
        first_id = eligible[0]["session_id"] if len(eligible) == 1 else None
        latest_id = eligible[0]["session_id"] if len(eligible) == 1 else None
        return None, first_id, latest_id

    first_s = eligible[0]
    latest_s = eligible[-1]
    first_score = first_s[score_key]
    latest_score = latest_s[score_key]

    first_id = first_s["session_id"]
    latest_id = latest_s["session_id"]

    if first_score == 0:
        return None, first_id, latest_id

    delta_percent = round(((latest_score - first_score) / first_score) * 100.0, 1)
    return delta_percent, first_id, latest_id


def _compute_category_status(avg_score: float) -> str:
    """
    Section 5 Category Status:
    Delegates to shared category_classifier.compute_category_status().
    average >= 7.0: strong
    6.0 <= average < 7.0: moderate
    average < 6.0: needs_focus
    """
    return compute_category_status(avg_score)


def _fetch_completed_sessions_and_turns(
    connection: sqlite3.Connection
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Retrieves all completed interview sessions in chronological order along with all of their turns.
    Excludes active, incomplete, and abandoned sessions (status != 'completed').
    """
    session_rows = connection.execute(
        """
        SELECT id, category, difficulty, current_turn, max_turns, created_at, completed_at
        FROM interview_sessions
        WHERE status = 'completed'
        ORDER BY completed_at ASC, id ASC
        """
    ).fetchall()

    if not session_rows:
        return [], []

    completed_session_ids = [r["id"] for r in session_rows]
    placeholders = ",".join("?" for _ in completed_session_ids)

    turn_rows = connection.execute(
        f"""
        SELECT
            st.id AS turn_id,
            st.session_id,
            st.turn_number,
            st.question_id,
            st.question_text,
            st.is_follow_up,
            st.parent_turn_id,
            st.answer_id,
            st.status AS turn_status,
            q.category AS direct_category,
            parent_q.category AS parent_category,
            s.category AS session_category,
            e.score AS technical_score,
            sa.delivery_score AS delivery_score,
            sa.speaking_rate_wpm,
            sa.filler_rate,
            nv.nonverbal_telemetry_score AS nonverbal_score
        FROM session_turns st
        JOIN interview_sessions s ON s.id = st.session_id
        LEFT JOIN questions q ON q.id = st.question_id
        LEFT JOIN session_turns parent_st ON parent_st.id = st.parent_turn_id
        LEFT JOIN questions parent_q ON parent_q.id = parent_st.question_id
        LEFT JOIN answers a ON a.id = st.answer_id
        LEFT JOIN evaluations e ON e.answer_id = a.id
        LEFT JOIN speech_analytics sa ON sa.answer_id = a.id
        LEFT JOIN nonverbal_analytics nv ON nv.answer_id = a.id
        WHERE st.session_id IN ({placeholders})
        ORDER BY s.completed_at ASC, s.id ASC, st.turn_number ASC
        """,
        completed_session_ids
    ).fetchall()

    return [dict(r) for r in session_rows], [dict(r) for r in turn_rows]


def _build_session_metrics(
    sessions: list[dict[str, Any]],
    turns: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Builds per-session metrics and annotates turns with their resolved effective category.
    Returns: (session_metrics_list, annotated_turns)
    """
    turns_by_session: dict[int, list[dict[str, Any]]] = {s["id"]: [] for s in sessions}
    annotated_turns: list[dict[str, Any]] = []

    for turn in turns:
        sid = turn["session_id"]
        turn["effective_category"] = _resolve_effective_category(
            turn["direct_category"],
            turn["parent_category"],
            turn["session_category"]
        )
        annotated_turns.append(turn)
        if sid in turns_by_session:
            turns_by_session[sid].append(turn)

    session_metrics: list[dict[str, Any]] = []

    for s in sessions:
        sid = s["id"]
        sturns = turns_by_session.get(sid, [])

        # Technical scores from evaluated answers
        tech_scores = [t["technical_score"] for t in sturns if t["technical_score"] is not None]
        # Delivery scores from speech analytics
        deliv_scores = [t["delivery_score"] for t in sturns if t["delivery_score"] is not None]
        # Nonverbal scores from vision analytics
        nv_scores = [t["nonverbal_score"] for t in sturns if t["nonverbal_score"] is not None]

        # Speaking rate and filler rate for trends
        wpms = [t["speaking_rate_wpm"] for t in sturns if t["speaking_rate_wpm"] is not None]
        fillers = [t["filler_rate"] for t in sturns if t["filler_rate"] is not None]

        turns_count = len(sturns)
        evaluated_count = len(tech_scores)
        bank_count = sum(1 for t in sturns if not bool(t["is_follow_up"]))
        follow_up_count = sum(1 for t in sturns if bool(t["is_follow_up"]))

        tech_score = round(sum(tech_scores) / len(tech_scores), 1) if tech_scores else None
        deliv_score = round(sum(deliv_scores) / len(deliv_scores), 1) if deliv_scores else None
        nv_score = round(sum(nv_scores) / len(nv_scores), 1) if nv_scores else None

        avg_wpm = round(sum(wpms) / len(wpms), 1) if wpms else None
        avg_filler = round(sum(fillers) / len(fillers), 3) if fillers else None

        session_metrics.append({
            "session_id": sid,
            "created_at": s["created_at"],
            "completed_at": s["completed_at"],
            "category": s["category"],
            "difficulty": s["difficulty"],
            "turns_count": turns_count,
            "evaluated_answers_count": evaluated_count,
            "bank_questions_count": bank_count,
            "follow_up_count": follow_up_count,
            "technical_score": tech_score,
            "delivery_score": deliv_score,
            "nonverbal_score": nv_score,
            "has_audio": len(deliv_scores) > 0,
            "has_video": len(nv_scores) > 0,
            "speaking_rate_wpm": avg_wpm,
            "filler_rate": avg_filler
        })

    return session_metrics, annotated_turns


def get_analytics_overview(connection: sqlite3.Connection) -> dict[str, Any]:
    """
    Computes global overview analytics according to Section 7 of the specification:
    - Macro volume counts (interviews, turns, evaluated answers, bank questions, follow-ups)
    - Cross-interview dimension averages (technical, delivery, nonverbal)
    - Modality availability
    - First vs latest changes per dimension
    - Category performance, strongest categories, and categories needing focus (with tie-breaking)
    - Chronological trend series
    """
    sessions, raw_turns = _fetch_completed_sessions_and_turns(connection)

    if not sessions:
        return {
            "total_completed_interviews": 0,
            "total_turns": 0,
            "total_evaluated_answers": 0,
            "total_bank_questions": 0,
            "total_follow_ups": 0,
            "technical_average": None,
            "delivery_average": None,
            "nonverbal_average": None,
            "modality_availability": {
                "has_audio": False,
                "has_video": False
            },
            "change": {
                "technical_percent": None,
                "delivery_percent": None,
                "nonverbal_percent": None,
                "technical_first_session_id": None,
                "technical_latest_session_id": None,
                "delivery_first_session_id": None,
                "delivery_latest_session_id": None,
                "nonverbal_first_session_id": None,
                "nonverbal_latest_session_id": None
            },
            "categories": [],
            "strongest_categories": [],
            "categories_needing_focus": [],
            "trends": {
                "sessions": []
            }
        }

    session_metrics, annotated_turns = _build_session_metrics(sessions, raw_turns)

    # Macro volume counts
    total_completed = len(session_metrics)
    total_turns = sum(s["turns_count"] for s in session_metrics)
    total_evaluated = sum(s["evaluated_answers_count"] for s in session_metrics)
    total_bank_q = sum(s["bank_questions_count"] for s in session_metrics)
    total_follow_ups = sum(s["follow_up_count"] for s in session_metrics)

    # Cross-interview dimension averages (Section 8: arithmetic mean of all atomic records)
    all_tech_scores = [t["technical_score"] for t in annotated_turns if t["technical_score"] is not None]
    all_deliv_scores = [t["delivery_score"] for t in annotated_turns if t["delivery_score"] is not None]
    all_nv_scores = [t["nonverbal_score"] for t in annotated_turns if t["nonverbal_score"] is not None]

    tech_avg = round(sum(all_tech_scores) / len(all_tech_scores), 1) if all_tech_scores else None
    deliv_avg = round(sum(all_deliv_scores) / len(all_deliv_scores), 1) if all_deliv_scores else None
    nv_avg = round(sum(all_nv_scores) / len(all_nv_scores), 1) if all_nv_scores else None

    # Modality availability across all completed interviews
    has_audio = any(s["has_audio"] for s in session_metrics)
    has_video = any(s["has_video"] for s in session_metrics)

    # First vs latest percentage changes (Section 9)
    tech_change, tech_first_id, tech_latest_id = _calculate_dimension_change(session_metrics, "technical_score")
    deliv_change, deliv_first_id, deliv_latest_id = _calculate_dimension_change(session_metrics, "delivery_score")
    nv_change, nv_first_id, nv_latest_id = _calculate_dimension_change(session_metrics, "nonverbal_score")

    # Category performance (Sections 5 & 6)
    # Group all evaluated answers by resolved category
    cat_scores: dict[str, list[int]] = {}
    for t in annotated_turns:
        if t["technical_score"] is not None:
            cat_name = t["effective_category"]
            cat_scores.setdefault(cat_name, []).append(t["technical_score"])

    categories: list[dict[str, Any]] = []
    for cat_name, scores in cat_scores.items():
        avg_score = round(sum(scores) / len(scores), 1)
        categories.append({
            "category": cat_name,
            "evaluated_answers_count": len(scores),
            "average_score": avg_score,
            "best_score": max(scores),
            "worst_score": min(scores),
            "status": _compute_category_status(avg_score)
        })

    # Sort categories deterministically: average desc, answer count desc, category asc
    categories.sort(key=lambda c: (-c["average_score"], -c["evaluated_answers_count"], c["category"]))

    strongest_categories: list[dict[str, Any]] = []
    categories_needing_focus: list[dict[str, Any]] = []

    if categories:
        max_avg = max(c["average_score"] for c in categories)
        min_avg = min(c["average_score"] for c in categories)

        # Strongest: all tied at max_avg, sorted: avg desc, count desc, name asc
        strongest_categories = [c for c in categories if c["average_score"] == max_avg]
        strongest_categories.sort(key=lambda c: (-c["average_score"], -c["evaluated_answers_count"], c["category"]))

        # Categories needing focus: all tied at min_avg, sorted: avg asc, count desc, name asc
        categories_needing_focus = [c for c in categories if c["average_score"] == min_avg]
        categories_needing_focus.sort(key=lambda c: (c["average_score"], -c["evaluated_answers_count"], c["category"]))

    # Chronological trend observations (Section 10: no interpolation)
    trends_sessions: list[dict[str, Any]] = [
        {
            "session_id": s["session_id"],
            "completed_at": s["completed_at"],
            "category": s["category"],
            "technical_score": s["technical_score"],
            "delivery_score": s["delivery_score"],
            "nonverbal_score": s["nonverbal_score"],
            "speaking_rate_wpm": s["speaking_rate_wpm"],
            "filler_rate": s["filler_rate"]
        }
        for s in session_metrics
    ]

    return {
        "total_completed_interviews": total_completed,
        "total_turns": total_turns,
        "total_evaluated_answers": total_evaluated,
        "total_bank_questions": total_bank_q,
        "total_follow_ups": total_follow_ups,
        "technical_average": tech_avg,
        "delivery_average": deliv_avg,
        "nonverbal_average": nv_avg,
        "modality_availability": {
            "has_audio": has_audio,
            "has_video": has_video
        },
        "change": {
            "technical_percent": tech_change,
            "delivery_percent": deliv_change,
            "nonverbal_percent": nv_change,
            "technical_first_session_id": tech_first_id,
            "technical_latest_session_id": tech_latest_id,
            "delivery_first_session_id": deliv_first_id,
            "delivery_latest_session_id": deliv_latest_id,
            "nonverbal_first_session_id": nv_first_id,
            "nonverbal_latest_session_id": nv_latest_id
        },
        "categories": categories,
        "strongest_categories": strongest_categories,
        "categories_needing_focus": categories_needing_focus,
        "trends": {
            "sessions": trends_sessions
        }
    }


def get_analytics_history(
    connection: sqlite3.Connection,
    limit: int = 20,
    offset: int = 0
) -> dict[str, Any]:
    """
    Returns paginated interview history according to Section 11 of the specification.
    Includes only completed sessions, ordered chronologically newest first.
    """
    sessions, raw_turns = _fetch_completed_sessions_and_turns(connection)

    if not sessions:
        return {
            "total_completed": 0,
            "limit": limit,
            "offset": offset,
            "sessions": []
        }

    session_metrics, _ = _build_session_metrics(sessions, raw_turns)

    # Reverse to present newest first (completed_at DESC)
    sessions_desc = list(reversed(session_metrics))
    total_completed = len(sessions_desc)

    # Apply pagination slice
    paged = sessions_desc[offset: offset + limit]

    history_items = [
        {
            "session_id": s["session_id"],
            "created_at": s["created_at"],
            "completed_at": s["completed_at"],
            "category": s["category"],
            "difficulty": s["difficulty"],
            "turns_count": s["turns_count"],
            "evaluated_answers_count": s["evaluated_answers_count"],
            "bank_questions_count": s["bank_questions_count"],
            "follow_up_count": s["follow_up_count"],
            "technical_score": s["technical_score"],
            "delivery_score": s["delivery_score"],
            "nonverbal_score": s["nonverbal_score"],
            "has_audio": s["has_audio"],
            "has_video": s["has_video"]
        }
        for s in paged
    ]

    return {
        "total_completed": total_completed,
        "limit": limit,
        "offset": offset,
        "sessions": history_items
    }
