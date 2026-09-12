"""
backend/insights_engine.py

Phase 14: Advanced Performance Analytics & Longitudinal Interview Insights.
Deterministic analytics layer providing multi-session trajectory analysis,
difficulty resilience, consistency metrics, answer quality patterns, communication trends,
objective nonverbal telemetry, and resume claim defense analytics.

Zero database schema modifications.
Zero blended scores.
Strict turn isolation:
  - Bank questions (is_follow_up=0, claim_id IS NULL, question_id IS NOT NULL) solely govern
    primary technical progression, category progression, difficulty progression,
    difficulty resilience, and consistency.
  - Remedial follow-ups provide answer-quality evidence only.
  - Claim probes provide resume claim defense analytics only.
"""

import os
import json
import math
import sqlite3
from typing import Any

try:
    from .category_classifier import compute_category_status
except (ImportError, ValueError):
    from category_classifier import compute_category_status

try:
    from .gemini_config import get_gemini_model
except (ImportError, ValueError):
    from gemini_config import get_gemini_model

try:
    from .coaching import classify_answer_quality
except (ImportError, ValueError):
    try:
        from coaching import classify_answer_quality
    except (ImportError, ValueError):
        classify_answer_quality = None

CANONICAL_CATEGORIES = ["Python", "Databases", "System Design", "Behavioral"]
CANONICAL_DIFFICULTIES = ["easy", "medium", "hard"]


def normalize_difficulty(difficulty: str | None) -> str:
    if not difficulty:
        return "medium"
    d = difficulty.strip().lower()
    if d == "beginner":
        return "easy"
    if d in CANONICAL_DIFFICULTIES:
        return d
    return "medium"


def resolve_effective_category(
    direct_category: str | None,
    parent_category: str | None,
    session_category: str | None
) -> str:
    if direct_category and direct_category.strip():
        return direct_category.strip()
    if parent_category and parent_category.strip():
        return parent_category.strip()
    if session_category and session_category.strip():
        sess_cat = session_category.strip()
        if sess_cat not in ("Multi-Category", "Custom", "All", "all"):
            return sess_cat
    return "General"


def is_bank_question(turn: dict[str, Any]) -> bool:
    is_fu = bool(turn.get("is_follow_up"))
    claim_id = turn.get("claim_id")
    qid = turn.get("question_id")
    return (not is_fu) and (not claim_id) and (qid is not None)


def is_remedial_follow_up(turn: dict[str, Any]) -> bool:
    is_fu = bool(turn.get("is_follow_up"))
    claim_id = turn.get("claim_id")
    return is_fu and (not claim_id)


def is_claim_probe(turn: dict[str, Any]) -> bool:
    claim_id = turn.get("claim_id")
    return bool(claim_id)


def calculate_wpm_distance(wpm: float) -> float:
    if wpm < 115.0:
        return round(115.0 - wpm, 2)
    elif wpm > 165.0:
        return round(wpm - 165.0, 2)
    return 0.0


def fetch_completed_sessions_and_turns(
    connection: sqlite3.Connection
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    session_rows = connection.execute(
        """
        SELECT id, category, difficulty, current_turn, max_turns, created_at, completed_at,
               candidate_profile, job_context
        FROM interview_sessions
        WHERE status = 'completed'
        ORDER BY completed_at ASC, id ASC
        """
    ).fetchall()

    if not session_rows:
        return [], {}

    sessions = [dict(r) for r in session_rows]
    session_ids = [s["id"] for s in sessions]
    placeholders = ",".join("?" for _ in session_ids)

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
            st.claim_id,
            q.category AS direct_category,
            q.difficulty AS question_difficulty,
            parent_q.category AS parent_category,
            s.category AS session_category,
            a.answer AS candidate_answer,
            e.score AS technical_score,
            e.technical_accuracy,
            sa.delivery_score,
            sa.speaking_rate_wpm,
            sa.filler_rate,
            sa.long_pause_count,
            sa.pause_count,
            sa.average_pause_duration,
            sa.repeated_words_count,
            nv.nonverbal_telemetry_score,
            nv.face_detected_ratio,
            nv.centering_offset,
            nv.gaze_deviation_ratio,
            nv.avg_yaw_degrees,
            nv.avg_pitch_degrees,
            nv.avg_roll_degrees,
            nv.head_motion_frequency_hz,
            nv.motion_energy,
            nv.camera_quality_flags
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
        session_ids
    ).fetchall()

    turns_by_session: dict[int, list[dict[str, Any]]] = {s["id"]: [] for s in sessions}
    for r in turn_rows:
        t = dict(r)
        t["effective_category"] = resolve_effective_category(
            t["direct_category"],
            t["parent_category"],
            t["session_category"]
        )
        turns_by_session[t["session_id"]].append(t)

    return sessions, turns_by_session


def calculate_technical_progression(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    timeline = []
    scores = []

    for s in sessions:
        sturns = turns_by_session.get(s["id"], [])
        bank_evals = [
            t["technical_score"] for t in sturns
            if is_bank_question(t) and t["technical_score"] is not None
        ]
        if bank_evals:
            bank_score = round(sum(bank_evals) / len(bank_evals), 2)
            scores.append(bank_score)
            timeline.append({
                "session_id": s["id"],
                "completed_at": s["completed_at"],
                "bank_score": bank_score
            })

    n = len(scores)
    if n == 0:
        return {
            "sample_size": 0,
            "first_score": None,
            "latest_score": None,
            "absolute_change": None,
            "percent_change": None,
            "window_change": None,
            "trend": "insufficient_data",
            "timeline": []
        }

    first_score = scores[0]
    latest_score = scores[-1]

    if n == 1:
        return {
            "sample_size": 1,
            "first_score": first_score,
            "latest_score": latest_score,
            "absolute_change": None,
            "percent_change": None,
            "window_change": None,
            "trend": "insufficient_data",
            "timeline": timeline
        }

    absolute_change = round(latest_score - first_score, 2)
    percent_change = (
        round(((latest_score - first_score) / first_score) * 100.0, 1)
        if first_score > 0 else None
    )

    if n == 2:
        return {
            "sample_size": 2,
            "first_score": first_score,
            "latest_score": latest_score,
            "absolute_change": absolute_change,
            "percent_change": percent_change,
            "window_change": None,
            "trend": "insufficient_data",
            "timeline": timeline
        }

    # n >= 3
    if absolute_change >= 0.5:
        trend = "improving"
    elif absolute_change <= -0.5:
        trend = "declining"
    else:
        trend = "stable"

    window_change = None
    if n >= 4:
        half = n // 2
        earlier_half = scores[:half]
        recent_half = scores[half:]
        window_change = round(
            (sum(recent_half) / len(recent_half)) - (sum(earlier_half) / len(earlier_half)),
            2
        )

    return {
        "sample_size": n,
        "first_score": first_score,
        "latest_score": latest_score,
        "absolute_change": absolute_change,
        "percent_change": percent_change,
        "window_change": window_change,
        "trend": trend,
        "timeline": timeline
    }


def calculate_consistency(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    valid_sessions = []
    for s in sessions:
        sturns = turns_by_session.get(s["id"], [])
        bank_evals = [
            t["technical_score"] for t in sturns
            if is_bank_question(t) and t["technical_score"] is not None
        ]
        if bank_evals:
            bank_score = round(sum(bank_evals) / len(bank_evals), 2)
            cats = sorted(list({
                t["effective_category"] for t in sturns
                if is_bank_question(t) and t["effective_category"]
            }))
            valid_sessions.append({
                "session_id": s["id"],
                "score": bank_score,
                "completed_at": s["completed_at"],
                "categories": cats
            })

    n = len(valid_sessions)
    if n == 0:
        return {
            "min_score": None,
            "max_score": None,
            "span": None,
            "standard_deviation": None,
            "earlier_standard_deviation": None,
            "recent_standard_deviation": None,
            "best_session": None,
            "worst_session": None
        }

    scores = [item["score"] for item in valid_sessions]
    min_score = round(min(scores), 2)
    max_score = round(max(scores), 2)
    span = round(max_score - min_score, 2)

    std_dev = None
    if n >= 3:
        mean_s = sum(scores) / n
        var = sum((x - mean_s) ** 2 for x in scores) / (n - 1)
        std_dev = round(math.sqrt(var), 2)

    earlier_std = None
    recent_std = None
    if n >= 4:
        half = n // 2
        e_scores = scores[:half]
        r_scores = scores[half:]
        if len(e_scores) >= 2:
            e_mean = sum(e_scores) / len(e_scores)
            e_var = sum((x - e_mean) ** 2 for x in e_scores) / (len(e_scores) - 1)
            earlier_std = round(math.sqrt(e_var), 2)
        if len(r_scores) >= 2:
            r_mean = sum(r_scores) / len(r_scores)
            r_var = sum((x - r_mean) ** 2 for x in r_scores) / (len(r_scores) - 1)
            recent_std = round(math.sqrt(r_var), 2)

    # Stable tie-breaking: first maximal / minimal element in chronological order
    best_item = max(valid_sessions, key=lambda x: x["score"])
    worst_item = min(valid_sessions, key=lambda x: x["score"])

    return {
        "min_score": min_score,
        "max_score": max_score,
        "span": span,
        "standard_deviation": std_dev,
        "earlier_standard_deviation": earlier_std,
        "recent_standard_deviation": recent_std,
        "best_session": {
            "session_id": best_item["session_id"],
            "score": best_item["score"],
            "completed_at": best_item["completed_at"],
            "categories": best_item["categories"]
        },
        "worst_session": {
            "session_id": worst_item["session_id"],
            "score": worst_item["score"],
            "completed_at": worst_item["completed_at"],
            "categories": worst_item["categories"]
        }
    }


def calculate_category_progression(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    result = []

    for cat in CANONICAL_CATEGORIES:
        timeline = []
        scores = []

        for s in sessions:
            sturns = turns_by_session.get(s["id"], [])
            cat_bank_evals = [
                t["technical_score"] for t in sturns
                if is_bank_question(t) and t["technical_score"] is not None and t["effective_category"] == cat
            ]
            if cat_bank_evals:
                avg = round(sum(cat_bank_evals) / len(cat_bank_evals), 2)
                scores.append(avg)
                timeline.append({
                    "session_id": s["id"],
                    "completed_at": s["completed_at"],
                    "score": avg
                })

        m = len(scores)
        if m == 0:
            result.append({
                "category": cat,
                "observations_count": 0,
                "first_score": None,
                "latest_score": None,
                "absolute_change": None,
                "trend": "insufficient_data",
                "status": "insufficient_data",
                "timeline": []
            })
            continue

        first_score = scores[0]
        latest_score = scores[-1]
        status = compute_category_status(latest_score)

        if m == 1:
            result.append({
                "category": cat,
                "observations_count": 1,
                "first_score": first_score,
                "latest_score": latest_score,
                "absolute_change": None,
                "trend": "insufficient_data",
                "status": status,
                "timeline": timeline
            })
        elif m == 2:
            abs_change = round(latest_score - first_score, 2)
            result.append({
                "category": cat,
                "observations_count": 2,
                "first_score": first_score,
                "latest_score": latest_score,
                "absolute_change": abs_change,
                "trend": "insufficient_data",
                "status": status,
                "timeline": timeline
            })
        else:
            abs_change = round(latest_score - first_score, 2)
            if abs_change >= 0.5:
                trend = "improving"
            elif abs_change <= -0.5:
                trend = "declining"
            else:
                trend = "stable"
            result.append({
                "category": cat,
                "observations_count": m,
                "first_score": first_score,
                "latest_score": latest_score,
                "absolute_change": abs_change,
                "trend": trend,
                "status": status,
                "timeline": timeline
            })

    return result


def calculate_difficulty_progression(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    tier_scores: dict[str, list[float]] = {"easy": [], "medium": [], "hard": []}
    session_tier_scores: dict[str, dict[int, list[float]]] = {
        "easy": {},
        "medium": {},
        "hard": {}
    }

    for s in sessions:
        sid = s["id"]
        sturns = turns_by_session.get(sid, [])
        for t in sturns:
            if is_bank_question(t) and t["technical_score"] is not None:
                diff = normalize_difficulty(t.get("question_difficulty"))
                score = float(t["technical_score"])
                tier_scores[diff].append(score)
                if sid not in session_tier_scores[diff]:
                    session_tier_scores[diff][sid] = []
                session_tier_scores[diff][sid].append(score)

    distribution = {d: len(tier_scores[d]) for d in CANONICAL_DIFFICULTIES}
    tier_averages = {
        d: (round(sum(tier_scores[d]) / len(tier_scores[d]), 2) if tier_scores[d] else None)
        for d in CANONICAL_DIFFICULTIES
    }

    hard_scores = tier_scores["hard"]
    hard_success_rate = None
    if hard_scores:
        hard_pass = sum(1 for s in hard_scores if s >= 7.0)
        hard_success_rate = round((hard_pass / len(hard_scores)) * 100.0, 1)

    # Resilience calculated independently for medium and hard
    resilience: dict[str, float | None] = {"medium": None, "hard": None}
    for diff in ("medium", "hard"):
        sessions_with_diff = [s for s in sessions if s["id"] in session_tier_scores[diff]]
        m = len(sessions_with_diff)
        if m >= 2:
            half = m // 2
            earlier_sessions = sessions_with_diff[:half]
            recent_sessions = sessions_with_diff[half:]

            earlier_scores = [
                sc for s in earlier_sessions for sc in session_tier_scores[diff].get(s["id"], [])
            ]
            recent_scores = [
                sc for s in recent_sessions for sc in session_tier_scores[diff].get(s["id"], [])
            ]

            if earlier_scores and recent_scores:
                earlier_avg = sum(earlier_scores) / len(earlier_scores)
                recent_avg = sum(recent_scores) / len(recent_scores)
                resilience[diff] = round(recent_avg - earlier_avg, 2)

    return {
        "distribution": distribution,
        "tier_averages": tier_averages,
        "hard_success_rate": hard_success_rate,
        "resilience": resilience
    }


def calculate_answer_quality_patterns(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    distribution = {
        "strong": 0,
        "shallow_incomplete": 0,
        "inaccurate": 0,
        "non_answer": 0
    }
    weakness_by_category: dict[str, int] = {}
    evaluated_turns = []

    for s in sessions:
        sturns = turns_by_session.get(s["id"], [])
        for t in sturns:
            if t["technical_score"] is not None:
                evaluated_turns.append((s["id"], t))
                if classify_answer_quality:
                    pat = classify_answer_quality(
                        score=t["technical_score"],
                        candidate_answer=t.get("candidate_answer"),
                        technical_accuracy=t.get("technical_accuracy"),
                        question_text=t.get("question_text")
                    )
                else:
                    score = t["technical_score"]
                    pat = "strong" if score >= 8 else ("inaccurate" if score <= 4 else "shallow/incomplete")

                if pat == "irrelevant/non-answer":
                    distribution["non_answer"] += 1
                elif pat == "inaccurate":
                    distribution["inaccurate"] += 1
                    cat = t.get("effective_category", "General")
                    weakness_by_category[cat] = weakness_by_category.get(cat, 0) + 1
                elif pat == "strong":
                    distribution["strong"] += 1
                else:
                    distribution["shallow_incomplete"] += 1
                    cat = t.get("effective_category", "General")
                    weakness_by_category[cat] = weakness_by_category.get(cat, 0) + 1

    total = len(evaluated_turns)
    percentages = {
        k: (round((distribution[k] / total) * 100.0, 1) if total > 0 else 0.0)
        for k in distribution
    }

    # Evolution over session halves
    earlier_strong_prop = None
    recent_strong_prop = None
    earlier_inacc_prop = None
    recent_inacc_prop = None

    if len(sessions) >= 2:
        half = len(sessions) // 2
        earlier_sids = {s["id"] for s in sessions[:half]}
        recent_sids = {s["id"] for s in sessions[half:]}

        earlier_turns = [t for sid, t in evaluated_turns if sid in earlier_sids]
        recent_turns = [t for sid, t in evaluated_turns if sid in recent_sids]

        if earlier_turns:
            e_strong = sum(
                1 for t in earlier_turns
                if (classify_answer_quality(
                    score=t["technical_score"],
                    candidate_answer=t.get("candidate_answer"),
                    technical_accuracy=t.get("technical_accuracy"),
                    question_text=t.get("question_text")
                ) if classify_answer_quality else "shallow/incomplete") == "strong"
            )
            e_inacc = sum(
                1 for t in earlier_turns
                if (classify_answer_quality(
                    score=t["technical_score"],
                    candidate_answer=t.get("candidate_answer"),
                    technical_accuracy=t.get("technical_accuracy"),
                    question_text=t.get("question_text")
                ) if classify_answer_quality else "shallow/incomplete") == "inaccurate"
            )
            earlier_strong_prop = round((e_strong / len(earlier_turns)) * 100.0, 1)
            earlier_inacc_prop = round((e_inacc / len(earlier_turns)) * 100.0, 1)

        if recent_turns:
            r_strong = sum(
                1 for t in recent_turns
                if (classify_answer_quality(
                    score=t["technical_score"],
                    candidate_answer=t.get("candidate_answer"),
                    technical_accuracy=t.get("technical_accuracy"),
                    question_text=t.get("question_text")
                ) if classify_answer_quality else "shallow/incomplete") == "strong"
            )
            r_inacc = sum(
                1 for t in recent_turns
                if (classify_answer_quality(
                    score=t["technical_score"],
                    candidate_answer=t.get("candidate_answer"),
                    technical_accuracy=t.get("technical_accuracy"),
                    question_text=t.get("question_text")
                ) if classify_answer_quality else "shallow/incomplete") == "inaccurate"
            )
            recent_strong_prop = round((r_strong / len(recent_turns)) * 100.0, 1)
            recent_inacc_prop = round((r_inacc / len(recent_turns)) * 100.0, 1)

    recurring_weakness = sorted([
        cat for cat, count in weakness_by_category.items() if count >= 2
    ])

    return {
        "total_evaluated_answers": total,
        "distribution": distribution,
        "percentages": percentages,
        "earlier_strong_proportion": earlier_strong_prop,
        "recent_strong_proportion": recent_strong_prop,
        "earlier_inaccurate_proportion": earlier_inacc_prop,
        "recent_inaccurate_proportion": recent_inacc_prop,
        "categories_with_recurring_weakness": recurring_weakness
    }


def calculate_communication_trends(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    session_speech_summaries = []
    all_speech_turns = []

    for s in sessions:
        sturns = turns_by_session.get(s["id"], [])
        speech_turns = [
            t for t in sturns
            if t.get("speaking_rate_wpm") is not None or t.get("delivery_score") is not None
        ]
        if speech_turns:
            all_speech_turns.extend(speech_turns)
            deliv_scores = [t["delivery_score"] for t in speech_turns if t.get("delivery_score") is not None]
            wpms = [t["speaking_rate_wpm"] for t in speech_turns if t.get("speaking_rate_wpm") is not None]
            fillers = [t["filler_rate"] for t in speech_turns if t.get("filler_rate") is not None]
            long_pauses = [t["long_pause_count"] for t in speech_turns if t.get("long_pause_count") is not None]
            pauses = [t["pause_count"] for t in speech_turns if t.get("pause_count") is not None]
            pause_durs = [t["average_pause_duration"] for t in speech_turns if t.get("average_pause_duration") is not None]

            session_speech_summaries.append({
                "session_id": s["id"],
                "completed_at": s["completed_at"],
                "delivery_score": round(sum(deliv_scores) / len(deliv_scores), 2) if deliv_scores else None,
                "speaking_rate_wpm": round(sum(wpms) / len(wpms), 2) if wpms else None,
                "filler_rate": round(sum(fillers) / len(fillers), 2) if fillers else None,
                "long_pause_count": sum(long_pauses) if long_pauses else 0,
                "pause_count": sum(pauses) if pauses else 0,
                "average_pause_duration": round(sum(pause_durs) / len(pause_durs), 2) if pause_durs else None
            })

    n = len(session_speech_summaries)
    if n == 0:
        return None

    # Delivery trend
    d_first = session_speech_summaries[0]["delivery_score"]
    d_latest = session_speech_summaries[-1]["delivery_score"]
    d_change = (
        round(d_latest - d_first, 2)
        if (n >= 2 and d_first is not None and d_latest is not None) else None
    )
    if n < 3 or d_change is None:
        d_trend = "insufficient_data"
    else:
        if d_change >= 0.5:
            d_trend = "improving"
        elif d_change <= -0.5:
            d_trend = "declining"
        else:
            d_trend = "stable"

    # Filler rate trend
    f_first = session_speech_summaries[0]["filler_rate"]
    f_latest = session_speech_summaries[-1]["filler_rate"]
    f_change = (
        round(f_latest - f_first, 2)
        if (n >= 2 and f_first is not None and f_latest is not None) else None
    )
    if n < 3 or f_change is None:
        f_trend = "insufficient_data"
    else:
        if f_change <= -1.0:
            f_trend = "improving"
        elif f_change >= 1.0:
            f_trend = "declining"
        else:
            f_trend = "stable"

    # Speaking rate trend based on distance to [115, 165]
    w_first = session_speech_summaries[0]["speaking_rate_wpm"]
    w_latest = session_speech_summaries[-1]["speaking_rate_wpm"]
    first_dist = calculate_wpm_distance(w_first) if w_first is not None else None
    latest_dist = calculate_wpm_distance(w_latest) if w_latest is not None else None

    if n < 3 or first_dist is None or latest_dist is None:
        w_trend = "insufficient_data"
    else:
        if latest_dist < first_dist:
            w_trend = "improving"
        elif latest_dist > first_dist:
            w_trend = "declining"
        else:
            w_trend = "stable"

    # Global pause aggregations across all speech turns
    tot_long_pauses = sum(t["long_pause_count"] for t in all_speech_turns if t.get("long_pause_count") is not None)
    tot_pauses = sum(t["pause_count"] for t in all_speech_turns if t.get("pause_count") is not None)
    pause_durs = [t["average_pause_duration"] for t in all_speech_turns if t.get("average_pause_duration") is not None]
    avg_pause_dur = round(sum(pause_durs) / len(pause_durs), 2) if pause_durs else None

    return {
        "sample_size": n,
        "delivery": {
            "first": d_first,
            "latest": d_latest,
            "absolute_change": d_change,
            "trend": d_trend
        },
        "speaking_rate": {
            "first_wpm": w_first,
            "latest_wpm": w_latest,
            "first_distance": first_dist,
            "latest_distance": latest_dist,
            "trend": w_trend
        },
        "filler_rate": {
            "first": f_first,
            "latest": f_latest,
            "absolute_change": f_change,
            "trend": f_trend
        },
        "pause_behavior": {
            "total_long_pauses": tot_long_pauses,
            "total_pauses": tot_pauses,
            "average_pause_duration": avg_pause_dur
        },
        "timeline": session_speech_summaries
    }


def calculate_nonverbal_trends(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    session_nv_summaries = []

    for s in sessions:
        sturns = turns_by_session.get(s["id"], [])
        nv_turns = [
            t for t in sturns
            if t.get("nonverbal_telemetry_score") is not None
        ]
        if nv_turns:
            scores = [t["nonverbal_telemetry_score"] for t in nv_turns if t.get("nonverbal_telemetry_score") is not None]
            faces = [t["face_detected_ratio"] for t in nv_turns if t.get("face_detected_ratio") is not None]
            centers = [t["centering_offset"] for t in nv_turns if t.get("centering_offset") is not None]
            gazes = [t["gaze_deviation_ratio"] for t in nv_turns if t.get("gaze_deviation_ratio") is not None]
            motions = [t["head_motion_frequency_hz"] for t in nv_turns if t.get("head_motion_frequency_hz") is not None]
            energies = [t["motion_energy"] for t in nv_turns if t.get("motion_energy") is not None]

            # Collect flags
            all_flags = []
            for t in nv_turns:
                flags_raw = t.get("camera_quality_flags")
                if flags_raw:
                    try:
                        parsed = json.loads(flags_raw) if isinstance(flags_raw, str) else flags_raw
                        if isinstance(parsed, list):
                            all_flags.extend(parsed)
                        elif isinstance(parsed, str):
                            all_flags.append(parsed)
                    except Exception:
                        all_flags.append(str(flags_raw))

            session_nv_summaries.append({
                "session_id": s["id"],
                "completed_at": s["completed_at"],
                "nonverbal_telemetry_score": round(sum(scores) / len(scores), 2) if scores else None,
                "face_detected_ratio": round(sum(faces) / len(faces), 2) if faces else None,
                "centering_offset": round(sum(centers) / len(centers), 2) if centers else None,
                "gaze_deviation_ratio": round(sum(gazes) / len(gazes), 2) if gazes else None,
                "head_motion_frequency_hz": round(sum(motions) / len(motions), 2) if motions else None,
                "motion_energy": round(sum(energies) / len(energies), 2) if energies else None,
                "camera_quality_flags": sorted(list(set(all_flags)))
            })

    n = len(session_nv_summaries)
    if n == 0:
        return None

    first = session_nv_summaries[0]
    latest = session_nv_summaries[-1]

    def delta(key: str) -> float | None:
        if n >= 2 and first.get(key) is not None and latest.get(key) is not None:
            return round(latest[key] - first[key], 2)
        return None

    absolute_change = {
        "nonverbal_telemetry_score": delta("nonverbal_telemetry_score"),
        "face_detected_ratio": delta("face_detected_ratio"),
        "centering_offset": delta("centering_offset"),
        "gaze_deviation_ratio": delta("gaze_deviation_ratio"),
        "head_motion_frequency_hz": delta("head_motion_frequency_hz"),
        "motion_energy": delta("motion_energy")
    }

    return {
        "sample_size": n,
        "first": first,
        "latest": latest,
        "absolute_change": absolute_change,
        "timeline": session_nv_summaries
    }


def calculate_resume_claim_analytics(
    sessions: list[dict[str, Any]],
    turns_by_session: dict[int, list[dict[str, Any]]]
) -> dict[str, Any]:
    sessions_with_claims = 0
    total_claim_instances_available = 0
    probed_claim_instances = set()
    probed_projects = set()

    substantiation = {
        "strongly_substantiated": 0,
        "partially_substantiated": 0,
        "weakly_substantiated": 0
    }
    probed_claims_details = []

    for s in sessions:
        sid = s["id"]
        raw_profile = s.get("candidate_profile")
        claims_list = []
        if raw_profile:
            try:
                prof = json.loads(raw_profile) if isinstance(raw_profile, str) else raw_profile
                if isinstance(prof, dict):
                    claims_list = prof.get("claims", [])
            except Exception:
                claims_list = []

        if claims_list:
            sessions_with_claims += 1
            total_claim_instances_available += len(claims_list)

        claims_by_id = {
            c.get("claim_id"): c for c in claims_list
            if isinstance(c, dict) and c.get("claim_id")
        }

        sturns = turns_by_session.get(sid, [])
        for t in sturns:
            cid = t.get("claim_id")
            if cid:
                instance_key = (sid, cid)
                probed_claim_instances.add(instance_key)
                claim_meta = claims_by_id.get(cid, {})
                proj_name = claim_meta.get("project_name")
                if proj_name:
                    probed_projects.add(proj_name)

                score = t.get("technical_score")
                subst_status = "unscored"
                if score is not None:
                    score_val = float(score)
                    if score_val >= 7.0:
                        substantiation["strongly_substantiated"] += 1
                        subst_status = "strongly_substantiated"
                    elif score_val >= 5.0:
                        substantiation["partially_substantiated"] += 1
                        subst_status = "partially_substantiated"
                    else:
                        substantiation["weakly_substantiated"] += 1
                        subst_status = "weakly_substantiated"

                probed_claims_details.append({
                    "session_id": sid,
                    "claim_id": cid,
                    "project_name": proj_name,
                    "category": claim_meta.get("category"),
                    "statement": claim_meta.get("statement"),
                    "score": score,
                    "substantiation_status": subst_status
                })

    return {
        "sessions_with_claims": sessions_with_claims,
        "total_claim_instances_available_across_sessions": total_claim_instances_available,
        "claim_instances_probed": len(probed_claim_instances),
        "projects_probed": len(probed_projects),
        "substantiation_breakdown": substantiation,
        "probed_claims": probed_claims_details
    }


def generate_insights_executive_summary(payload: dict[str, Any]) -> str:
    total = payload.get("total_completed_interviews", 0)
    if total == 0:
        return "No completed interview sessions recorded. Complete an interview session to generate performance insights."

    tech = payload.get("technical_progression", {})
    trend = tech.get("trend", "stable")
    first = tech.get("first_score")
    latest = tech.get("latest_score")
    abs_change = tech.get("absolute_change")
    cons = payload.get("consistency", {})
    best_s = cons.get("best_session")

    # Deterministic fallback text
    if trend == "improving" and abs_change is not None:
        perf_sentence = f"Technical performance shows consistent growth from {first} to {latest} (+{abs_change} pts)."
    elif trend == "declining" and abs_change is not None:
        perf_sentence = f"Technical performance reflects a downward trend from {first} to {latest} ({abs_change} pts)."
    elif first is not None and latest is not None and abs_change is not None:
        perf_sentence = f"Technical performance has remained steady between {first} and {latest} ({abs_change:+} pts)."
    elif latest is not None:
        perf_sentence = f"Technical proficiency was evaluated at {latest}/10 across completed sessions."
    else:
        perf_sentence = "Technical evaluations are pending across recorded sessions."

    if best_s and best_s.get("score") is not None:
        cats_str = ", ".join(best_s.get("categories", [])) or "General"
        cons_sentence = f"Peak capability was reached in session {best_s.get('session_id')} with {best_s.get('score')}/10 in {cats_str}."
    else:
        cons_sentence = f"Total of {total} interview sessions have been evaluated."

    claims_info = payload.get("resume_claim_analytics", {})
    if claims_info.get("claim_instances_probed", 0) > 0:
        strong_sub = claims_info.get("substantiation_breakdown", {}).get("strongly_substantiated", 0)
        probed_cnt = claims_info.get("claim_instances_probed", 0)
        third_sentence = f"Resume defense demonstrated strong grounding in {strong_sub} of {probed_cnt} probed claims."
    else:
        third_sentence = "Continue practicing across domains to deepen longitudinal consistency."

    fallback_text = f"{perf_sentence} {cons_sentence} {third_sentence}"

    # Optional Gemini enhancement
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return fallback_text

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        facts = {
            "total_completed_interviews": total,
            "technical_trend": trend,
            "first_score": first,
            "latest_score": latest,
            "absolute_change": abs_change,
            "best_session_score": best_s.get("score") if best_s else None,
            "best_session_categories": best_s.get("categories") if best_s else None,
            "claim_instances_probed": claims_info.get("claim_instances_probed"),
            "strongly_substantiated_claims": claims_info.get("substantiation_breakdown", {}).get("strongly_substantiated")
        }
        prompt = (
            "You are an interview performance analyst. Synthesize a concise 2-3 sentence executive performance "
            "summary based STRICTLY on these deterministic facts. Do NOT calculate new numbers, do NOT alter any scores, "
            "and do NOT invent any claims or facts outside this JSON:\n" + json.dumps(facts)
        )
        resp = client.models.generate_content(
            model=get_gemini_model(),
            contents=prompt
        )
        if resp and resp.text and len(resp.text.strip()) > 20:
            return resp.text.strip()
    except Exception:
        pass

    return fallback_text


def get_analytics_insights(connection: sqlite3.Connection) -> dict[str, Any]:
    sessions, turns_by_session = fetch_completed_sessions_and_turns(connection)

    tech_progression = calculate_technical_progression(sessions, turns_by_session)
    consistency = calculate_consistency(sessions, turns_by_session)
    cat_progression = calculate_category_progression(sessions, turns_by_session)
    diff_progression = calculate_difficulty_progression(sessions, turns_by_session)
    ans_quality = calculate_answer_quality_patterns(sessions, turns_by_session)
    comm_trends = calculate_communication_trends(sessions, turns_by_session)
    nv_trends = calculate_nonverbal_trends(sessions, turns_by_session)
    claim_analytics = calculate_resume_claim_analytics(sessions, turns_by_session)

    payload = {
        "total_completed_interviews": len(sessions),
        "technical_progression": tech_progression,
        "consistency": consistency,
        "category_progression": cat_progression,
        "difficulty_progression": diff_progression,
        "answer_quality_patterns": ans_quality,
        "communication_trends": comm_trends,
        "nonverbal_trends": nv_trends,
        "resume_claim_analytics": claim_analytics,
        "executive_summary": ""
    }

    payload["executive_summary"] = generate_insights_executive_summary(payload)
    return payload
