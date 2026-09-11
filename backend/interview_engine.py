import os
import json
from pathlib import Path
from typing import Literal

# Load .env if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass

try:
    from . import strategy_engine
except (ImportError, ValueError):
    import strategy_engine

try:
    from . import interviewer
except (ImportError, ValueError):
    import interviewer

try:
    from .question_bank import CANONICAL_CATEGORIES
except (ImportError, ValueError):
    from question_bank import CANONICAL_CATEGORIES


def select_next_bank_question(connection, session_id: int, category: str | None = None, difficulty: str | None = None):
    """
    Selects a bank question that has NOT already been asked in this session.
    Prioritizes the session's category and difficulty deterministically.
    """
    norm_diff = strategy_engine.normalize_difficulty(difficulty) if difficulty else None

    base_query = """
        SELECT id, category, difficulty, question
        FROM questions
        WHERE id NOT IN (
            SELECT question_id FROM session_turns
            WHERE session_id = ? AND question_id IS NOT NULL
        )
    """

    # 1. Try matching both category and difficulty
    if category and norm_diff:
        if norm_diff == "easy":
            diff_clause = "AND category = ? AND difficulty IN ('easy', 'beginner')"
            row = connection.execute(
                base_query + f" {diff_clause} ORDER BY id ASC LIMIT 1",
                (session_id, category)
            ).fetchone()
        else:
            row = connection.execute(
                base_query + " AND category = ? AND difficulty = ? ORDER BY id ASC LIMIT 1",
                (session_id, category, norm_diff)
            ).fetchone()
        if row:
            res = dict(row)
            res["difficulty"] = strategy_engine.normalize_difficulty(res["difficulty"])
            return res

    # 2. Try matching category
    if category:
        row = connection.execute(
            base_query + " AND category = ? ORDER BY id ASC LIMIT 1",
            (session_id, category)
        ).fetchone()
        if row:
            res = dict(row)
            res["difficulty"] = strategy_engine.normalize_difficulty(res["difficulty"])
            return res

    # 3. Try matching difficulty
    if norm_diff:
        if norm_diff == "easy":
            row = connection.execute(
                base_query + " AND difficulty IN ('easy', 'beginner') ORDER BY id ASC LIMIT 1",
                (session_id,)
            ).fetchone()
        else:
            row = connection.execute(
                base_query + " AND difficulty = ? ORDER BY id ASC LIMIT 1",
                (session_id, norm_diff)
            ).fetchone()
        if row:
            res = dict(row)
            res["difficulty"] = strategy_engine.normalize_difficulty(res["difficulty"])
            return res

    # 4. Fallback: Any unasked question (deterministic lowest id)
    row = connection.execute(
        base_query + " ORDER BY id ASC LIMIT 1",
        (session_id,)
    ).fetchone()

    if row:
        res = dict(row)
        res["difficulty"] = strategy_engine.normalize_difficulty(res["difficulty"])
        return res
    return None


def generate_follow_up_question(
    original_question: str,
    candidate_answer: str,
    evaluation_feedback: str,
    missing_points: list[str],
    category: str = "Technical",
    difficulty: str = "medium"
) -> str:
    """
    Generates an adaptive follow-up question probing identified candidate weaknesses.
    Uses Gemini 2.5 Flash if GEMINI_API_KEY is configured; otherwise uses a structured fallback.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            prompt = f"""
You are an expert, conversational technical interviewer conducting a mock interview.

INTERVIEW CONTEXT:
- Category: {category}
- Difficulty: {difficulty}
- Original Question Asked: {original_question}

CANDIDATE'S ANSWER:
\"\"\"{candidate_answer}\"\"\"

EVALUATION ASSESSMENT:
- Feedback: {evaluation_feedback}
- Identified Gaps / Missing Points: {", ".join(missing_points) if missing_points else "Needs deeper technical explanation"}

TASK:
Formulate a single, conversational follow-up question (1 to 2 sentences max) that directly asks the candidate to address or clarify one of the missing points above.
Rules:
1. Do NOT answer the question for the candidate or provide the solution.
2. Make it flow naturally from what they just answered.
3. Keep it professional, direct, and encouraging.
Return ONLY the follow-up question text with no preface or quotes.
"""
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            text = response.text.strip() if response.text else ""
            if text:
                # Remove surrounding quotes if model added them
                if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
                    text = text[1:-1].strip()
                return text
        except Exception:
            pass

    # Structured fallback when offline or no API key
    if missing_points:
        first_gap = missing_points[0].rstrip(".")
        return f"Building on your explanation, could you elaborate on how you would address {first_gap}?"
    else:
        return f"Could you provide a concrete production example or discuss the performance trade-offs of your approach?"


def normalize_session_configuration(
    category: str | None = None,
    categories: list[str] | None = None,
    target_role: str | None = None,
    experience_level: str | None = "mid",
    interviewer_style: str | None = "professional"
) -> tuple[str | None, list[str], str | None, str, str]:
    """
    Normalizes Phase 11 interview session configuration parameters.
    Returns: (stored_category, normalized_selected_categories, clean_target_role, clean_experience_level, clean_interviewer_style)
    """
    # 1. Target Role
    if target_role is not None:
        r = str(target_role).strip()
        if len(r) > 100:
            raise ValueError("target_role cannot exceed 100 characters")
        clean_role = r if r else None
    else:
        clean_role = None

    # 2. Experience Level
    if experience_level is None:
        clean_exp = "mid"
    else:
        exp = str(experience_level).strip().lower()
        if exp not in ("junior", "mid", "senior"):
            raise ValueError(f"Invalid experience_level '{experience_level}'. Must be 'junior', 'mid', or 'senior'")
        clean_exp = exp

    # 3. Interviewer Style
    if interviewer_style is None:
        clean_style = "professional"
    else:
        style = str(interviewer_style).strip().lower()
        if style not in ("professional", "conversational", "strict"):
            raise ValueError(f"Invalid interviewer_style '{interviewer_style}'. Must be 'professional', 'conversational', or 'strict'")
        clean_style = style

    # 4. Category Normalization
    if categories is not None:
        if not isinstance(categories, list):
            raise ValueError("categories must be a list of strings")
        if len(categories) == 0:
            raise ValueError("categories list cannot be empty. Specify at least one category or use 'All'.")

        cleaned = [c.strip() for c in categories if isinstance(c, str)]
        if not cleaned:
            raise ValueError("categories list cannot be empty. Specify at least one category or use 'All'.")

        has_all = any(c.lower() == "all" for c in cleaned)
        if has_all:
            if len(cleaned) > 1:
                raise ValueError("Cannot combine 'All' with specific categories in categories list.")
            normalized_selected = list(CANONICAL_CATEGORIES)
            stored_category = "All"
        else:
            # Check for invalid categories
            for c in cleaned:
                if c not in CANONICAL_CATEGORIES:
                    raise ValueError(f"Invalid category '{c}'. Must be one of {CANONICAL_CATEGORIES}")

            # Deduplicate preserving canonical order
            deduped = [c for c in CANONICAL_CATEGORIES if c in cleaned]
            if len(deduped) == 1:
                normalized_selected = deduped
                stored_category = deduped[0]
            else:
                normalized_selected = deduped
                stored_category = None  # Multiple custom categories: category = NULL

        # Check for conflicting legacy category and new categories inputs
        if category is not None and category.strip():
            cat_c = category.strip()
            if cat_c.lower() == "all":
                if not has_all:
                    raise ValueError("Conflicting category inputs: category='All' conflicts with specific categories.")
            else:
                if normalized_selected != [cat_c]:
                    raise ValueError(f"Conflicting category inputs: category='{cat_c}' conflicts with categories={categories}.")
    else:
        if category is None or category.strip() in ("", "All", "all"):
            normalized_selected = list(CANONICAL_CATEGORIES)
            stored_category = "All"
        else:
            cat_clean = category.strip()
            if cat_clean in ("Custom", "Multi-Category"):
                raise ValueError(f"Invalid category configuration: '{cat_clean}' cannot be used as a runtime category.")
            if cat_clean not in CANONICAL_CATEGORIES and cat_clean not in ("SQL", "FastAPI", "CatA", "CatB", "CatC", "CatD"):
                raise ValueError(f"Invalid category '{cat_clean}'. Must be one of {CANONICAL_CATEGORIES} or 'All'")
            normalized_selected = [cat_clean]
            stored_category = cat_clean

    return stored_category, normalized_selected, clean_role, clean_exp, clean_style


def start_session(
    connection,
    category: str | None = None,
    difficulty: str | None = None,
    max_turns: int = 5,
    categories: list[str] | None = None,
    target_role: str | None = None,
    experience_level: str | None = "mid",
    interviewer_style: str | None = "professional",
    candidate_profile: dict | None = None,
    job_context: dict | None = None
) -> dict:
    """
    Initializes a new interview session and selects the first question deterministically via strategy_engine.
    """
    canonical_diff = strategy_engine.normalize_difficulty(difficulty) if difficulty else None

    # Target role fallback: If target_role is omitted/blank, default to job_context.title if present
    effective_role = target_role
    if (effective_role is None or not str(effective_role).strip()) and job_context:
        j_title = job_context.get("title") if isinstance(job_context, dict) else getattr(job_context, "title", None)
        if j_title and str(j_title).strip():
            effective_role = str(j_title).strip()[:100]

    stored_category, normalized_selected, clean_role, clean_exp, clean_style = normalize_session_configuration(
        category=category,
        categories=categories,
        target_role=effective_role,
        experience_level=experience_level,
        interviewer_style=interviewer_style
    )

    profile_json = json.dumps(candidate_profile) if candidate_profile is not None else None
    job_json = json.dumps(job_context) if job_context is not None else None

    cols = {row["name"] for row in connection.execute("PRAGMA table_info(interview_sessions)").fetchall()}
    if "candidate_profile" in cols and "job_context" in cols:
        cursor = connection.execute(
            """
            INSERT INTO interview_sessions (
                category, difficulty, max_turns, status, current_turn,
                target_role, experience_level, selected_categories, interviewer_style,
                candidate_profile, job_context
            )
            VALUES (?, ?, ?, 'active', 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored_category,
                canonical_diff,
                max_turns,
                clean_role,
                clean_exp,
                json.dumps(normalized_selected),
                clean_style,
                profile_json,
                job_json
            )
        )
    elif "selected_categories" in cols:
        cursor = connection.execute(
            """
            INSERT INTO interview_sessions (
                category, difficulty, max_turns, status, current_turn,
                target_role, experience_level, selected_categories, interviewer_style
            )
            VALUES (?, ?, ?, 'active', 1, ?, ?, ?, ?)
            """,
            (
                stored_category,
                canonical_diff,
                max_turns,
                clean_role,
                clean_exp,
                json.dumps(normalized_selected),
                clean_style
            )
        )
    else:
        cursor = connection.execute(
            """
            INSERT INTO interview_sessions (category, difficulty, max_turns, status, current_turn)
            VALUES (?, ?, ?, 'active', 1)
            """,
            (stored_category, canonical_diff, max_turns)
        )
    session_id = cursor.lastrowid

    # Select first bank question via deterministic strategy engine
    decision = strategy_engine.decide_next_turn(connection, session_id)
    if decision.get("action") != "new_bank_question" or not decision.get("question"):
        raise ValueError("No questions available to start the interview session.")

    first_q = decision["question"]

    # Create Turn 1
    turn_cursor = connection.execute(
        """
        INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, status)
        VALUES (?, 1, ?, ?, 0, 'pending')
        """,
        (session_id, first_q["id"], first_q["question"])
    )

    connection.commit()

    return {
        "session_id": session_id,
        "category": stored_category,
        "difficulty": difficulty,
        "max_turns": max_turns,
        "status": "active",
        "current_turn": 1,
        "target_role": clean_role,
        "experience_level": clean_exp,
        "selected_categories": normalized_selected,
        "interviewer_style": clean_style,
        "candidate_profile": candidate_profile,
        "job_context": job_context,
        "question": {
            "turn_id": turn_cursor.lastrowid,
            "turn_number": 1,
            "question_id": first_q["id"],
            "category": first_q["category"],
            "difficulty": first_q["difficulty"],
            "question": first_q["question"],
            "is_follow_up": False
        }
    }


def get_session_details(connection, session_id: int) -> dict | None:
    """
    Retrieves the full session state, active question, and turn history.
    """
    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        return None

    # Fetch all turns in sequence
    turn_rows = connection.execute(
        """
        SELECT st.id AS turn_id, st.turn_number, st.question_id, st.question_text,
               st.is_follow_up, st.status, st.answer_id,
               q.category AS question_category, q.difficulty AS question_difficulty,
               a.answer,
               e.score, e.feedback, e.technical_accuracy, e.strengths, e.missing_points
        FROM session_turns st
        LEFT JOIN questions q ON q.id = st.question_id
        LEFT JOIN answers a ON a.id = st.answer_id
        LEFT JOIN evaluations e ON e.answer_id = a.id
        WHERE st.session_id = ?
        ORDER BY st.turn_number ASC
        """,
        (session_id,)
    ).fetchall()

    turns = []
    active_turn = None

    for r in turn_rows:
        turn_data = {
            "turn_id": r["turn_id"],
            "turn_number": r["turn_number"],
            "question_id": r["question_id"],
            "question_text": r["question_text"],
            "is_follow_up": bool(r["is_follow_up"]),
            "status": r["status"]
        }

        if r["status"] == "pending":
            active_turn = turn_data

        if r["answer"] is not None:
            turn_data["answer"] = r["answer"]
            turn_data["evaluation"] = {
                "score": r["score"],
                "feedback": r["feedback"],
                "technical_accuracy": r["technical_accuracy"],
                "strengths": json.loads(r["strengths"]) if r["strengths"] else [],
                "missing_points": json.loads(r["missing_points"]) if r["missing_points"] else []
            }

            sa_row = connection.execute(
                """
                SELECT audio_duration_seconds, speaking_duration_seconds,
                       pause_duration_seconds, pause_count, average_pause_duration,
                       long_pause_count, phonation_ratio, speaking_rate_wpm,
                       articulation_rate_wpm, filler_word_count, filler_rate,
                       filler_breakdown, repeated_words_count, delivery_score,
                       delivery_feedback
                FROM speech_analytics
                WHERE answer_id = ?
                """,
                (r["answer_id"],)
            ).fetchone()

            if sa_row is not None:
                turn_data["speech_analytics"] = {
                    "audio_duration_seconds": sa_row["audio_duration_seconds"],
                    "speaking_duration_seconds": sa_row["speaking_duration_seconds"],
                    "pause_duration_seconds": sa_row["pause_duration_seconds"],
                    "pause_count": sa_row["pause_count"],
                    "average_pause_duration": sa_row["average_pause_duration"],
                    "long_pause_count": sa_row["long_pause_count"],
                    "phonation_ratio": sa_row["phonation_ratio"],
                    "speaking_rate_wpm": sa_row["speaking_rate_wpm"],
                    "articulation_rate_wpm": sa_row["articulation_rate_wpm"],
                    "filler_word_count": sa_row["filler_word_count"],
                    "filler_rate": sa_row["filler_rate"],
                    "filler_breakdown": json.loads(sa_row["filler_breakdown"]) if sa_row["filler_breakdown"] else {},
                    "repeated_words_count": sa_row["repeated_words_count"],
                    "delivery_score": sa_row["delivery_score"],
                    "delivery_feedback": sa_row["delivery_feedback"]
                }
            else:
                turn_data["speech_analytics"] = None

            nv_row = connection.execute(
                """
                SELECT video_duration_seconds, frames_analyzed, face_detected_ratio,
                       centering_offset, gaze_deviation_ratio, avg_yaw_degrees,
                       avg_pitch_degrees, avg_roll_degrees, yaw_variance,
                       pitch_variance, roll_variance, head_motion_frequency_hz,
                       motion_energy, camera_quality_flags, nonverbal_telemetry_score,
                       nonverbal_feedback, vision_backend
                FROM nonverbal_analytics
                WHERE answer_id = ?
                """,
                (r["answer_id"],)
            ).fetchone()

            if nv_row is not None:
                turn_data["nonverbal_analytics"] = {
                    "video_duration_seconds": nv_row["video_duration_seconds"],
                    "frames_analyzed": nv_row["frames_analyzed"],
                    "face_detected_ratio": nv_row["face_detected_ratio"],
                    "centering_offset": nv_row["centering_offset"],
                    "gaze_deviation_ratio": nv_row["gaze_deviation_ratio"],
                    "avg_yaw_degrees": nv_row["avg_yaw_degrees"],
                    "avg_pitch_degrees": nv_row["avg_pitch_degrees"],
                    "avg_roll_degrees": nv_row["avg_roll_degrees"],
                    "yaw_variance": nv_row["yaw_variance"],
                    "pitch_variance": nv_row["pitch_variance"],
                    "roll_variance": nv_row["roll_variance"],
                    "head_motion_frequency_hz": nv_row["head_motion_frequency_hz"],
                    "motion_energy": nv_row["motion_energy"],
                    "camera_quality_flags": json.loads(nv_row["camera_quality_flags"]) if nv_row["camera_quality_flags"] else [],
                    "nonverbal_telemetry_score": nv_row["nonverbal_telemetry_score"],
                    "nonverbal_feedback": nv_row["nonverbal_feedback"],
                    "vision_backend": nv_row["vision_backend"]
                }
            else:
                turn_data["nonverbal_analytics"] = None

        turns.append(turn_data)

    return {
        "session_id": session_row["id"],
        "status": session_row["status"],
        "category": session_row["category"],
        "difficulty": session_row["difficulty"],
        "current_turn": session_row["current_turn"],
        "max_turns": session_row["max_turns"],
        "created_at": session_row["created_at"],
        "completed_at": session_row["completed_at"],
        "target_role": session_row["target_role"] if ("target_role" in session_row.keys() and session_row["target_role"]) else None,
        "experience_level": session_row["experience_level"] if ("experience_level" in session_row.keys() and session_row["experience_level"]) else "mid",
        "selected_categories": json.loads(session_row["selected_categories"]) if ("selected_categories" in session_row.keys() and session_row["selected_categories"]) else None,
        "interviewer_style": session_row["interviewer_style"] if ("interviewer_style" in session_row.keys() and session_row["interviewer_style"]) else "professional",
        "candidate_profile": json.loads(session_row["candidate_profile"]) if ("candidate_profile" in session_row.keys() and session_row["candidate_profile"]) else None,
        "job_context": json.loads(session_row["job_context"]) if ("job_context" in session_row.keys() and session_row["job_context"]) else None,
        "active_question": active_turn,
        "turns": turns
    }


def record_answer_and_advance(
    connection,
    session_id: int,
    answer_text: str,
    evaluation,
    speech_metrics: dict | None = None,
    nonverbal_metrics: dict | None = None,
    interviewer_style: str | None = None
) -> dict:
    """
    Records the candidate's answer for the active turn, persists the evaluation,
    applies follow-up decision logic, calls interviewer conversational layer, and advances the session.
    """
    # 1. Retrieve session and active pending turn
    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        raise ValueError("Interview session not found.")

    if session_row["status"] != "active":
        raise ValueError("This interview session is already completed or inactive.")

    sess_style = session_row["interviewer_style"] if ("interviewer_style" in session_row.keys() and session_row["interviewer_style"]) else "professional"
    effective_style = interviewer_style or sess_style or "professional"

    pending_turn = connection.execute(
        """
        SELECT st.*,
               q.category as question_category,
               q.difficulty as question_difficulty,
               parent_q.category as parent_category,
               parent_q.difficulty as parent_difficulty
        FROM session_turns st
        LEFT JOIN questions q ON st.question_id = q.id
        LEFT JOIN session_turns parent_st ON st.parent_turn_id = parent_st.id
        LEFT JOIN questions parent_q ON parent_st.question_id = parent_q.id
        WHERE st.session_id = ? AND st.status = 'pending'
        ORDER BY st.turn_number ASC LIMIT 1
        """,
        (session_id,)
    ).fetchone()

    if pending_turn is None:
        raise ValueError("No active question pending an answer in this session.")

    # 2. Insert answer into answers table
    # Modification 1: For generated follow-ups, question_id is NULL.
    cursor = connection.execute(
        "INSERT INTO answers (question_id, answer) VALUES (?, ?)",
        (pending_turn["question_id"], answer_text)
    )
    answer_id = cursor.lastrowid

    # 3. Persist evaluation into evaluations table
    strengths_json = json.dumps(evaluation.strengths)
    missing_json = json.dumps(evaluation.missing_points)

    connection.execute(
        """
        INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy, strengths, missing_points)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            answer_id,
            evaluation.score,
            evaluation.feedback,
            evaluation.technical_accuracy,
            strengths_json,
            missing_json
        )
    )

    # 3b. Persist speech analytics if audio answer was provided
    if speech_metrics is not None:
        filler_json = json.dumps(speech_metrics.get("filler_breakdown", {}))
        connection.execute(
            """
            INSERT INTO speech_analytics (
                answer_id, audio_duration_seconds, speaking_duration_seconds,
                pause_duration_seconds, pause_count, average_pause_duration,
                long_pause_count, phonation_ratio, speaking_rate_wpm,
                articulation_rate_wpm, filler_word_count, filler_rate,
                filler_breakdown, repeated_words_count, delivery_score,
                delivery_feedback
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                speech_metrics.get("audio_duration_seconds", 0.0),
                speech_metrics.get("speaking_duration_seconds", 0.0),
                speech_metrics.get("pause_duration_seconds", 0.0),
                speech_metrics.get("pause_count", 0),
                speech_metrics.get("average_pause_duration", 0.0),
                speech_metrics.get("long_pause_count", 0),
                speech_metrics.get("phonation_ratio", 0.0),
                speech_metrics.get("speaking_rate_wpm", 0.0),
                speech_metrics.get("articulation_rate_wpm", 0.0),
                speech_metrics.get("filler_word_count", 0),
                speech_metrics.get("filler_rate", 0.0),
                filler_json,
                speech_metrics.get("repeated_words_count", 0),
                speech_metrics.get("delivery_score", 10),
                speech_metrics.get("delivery_feedback", "")
            )
        )

    # 3c. Persist nonverbal analytics if video telemetry was provided
    if nonverbal_metrics is not None:
        quality_flags_json = json.dumps(nonverbal_metrics.get("camera_quality_flags", []))
        connection.execute(
            """
            INSERT INTO nonverbal_analytics (
                answer_id, video_duration_seconds, frames_analyzed,
                face_detected_ratio, centering_offset, gaze_deviation_ratio,
                avg_yaw_degrees, avg_pitch_degrees, avg_roll_degrees,
                yaw_variance, pitch_variance, roll_variance,
                head_motion_frequency_hz, motion_energy, camera_quality_flags,
                nonverbal_telemetry_score, nonverbal_feedback, vision_backend
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id,
                nonverbal_metrics.get("video_duration_seconds", 0.0),
                nonverbal_metrics.get("frames_analyzed", 0),
                nonverbal_metrics.get("face_detected_ratio", 0.0),
                nonverbal_metrics.get("centering_offset", 0.0),
                nonverbal_metrics.get("gaze_deviation_ratio"),
                nonverbal_metrics.get("avg_yaw_degrees"),
                nonverbal_metrics.get("avg_pitch_degrees"),
                nonverbal_metrics.get("avg_roll_degrees"),
                nonverbal_metrics.get("yaw_variance"),
                nonverbal_metrics.get("pitch_variance"),
                nonverbal_metrics.get("roll_variance"),
                nonverbal_metrics.get("head_motion_frequency_hz"),
                nonverbal_metrics.get("motion_energy", 0.0),
                quality_flags_json,
                nonverbal_metrics.get("nonverbal_telemetry_score", 10),
                nonverbal_metrics.get("nonverbal_feedback", ""),
                nonverbal_metrics.get("vision_backend", "mediapipe")
            )
        )

    # 4. Mark pending turn as evaluated
    connection.execute(
        """
        UPDATE session_turns
        SET answer_id = ?, status = 'evaluated'
        WHERE id = ?
        """,
        (answer_id, pending_turn["id"])
    )

    current_turn_num = pending_turn["turn_number"]
    max_turns = session_row["max_turns"]

    evaluated_summary = {
        "turn_id": pending_turn["id"],
        "turn_number": current_turn_num,
        "question_id": pending_turn["question_id"],
        "question_text": pending_turn["question_text"],
        "is_follow_up": bool(pending_turn["is_follow_up"]),
        "answer_id": answer_id,
        "answer": answer_text,
        "score": evaluation.score,
        "feedback": evaluation.feedback,
        "technical_accuracy": evaluation.technical_accuracy,
        "strengths": evaluation.strengths,
        "missing_points": evaluation.missing_points,
        "evaluator": getattr(evaluation, "evaluator", "ai-evaluator"),
        "speech_analytics": speech_metrics,
        "nonverbal_analytics": nonverbal_metrics
    }

    # 5. Check if session reached max turns (Modification 2)
    if current_turn_num >= max_turns:
        connection.execute(
            """
            UPDATE interview_sessions
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (session_id,)
        )
        connection.commit()
        return {
            "session_id": session_id,
            "status": "completed",
            "current_turn": current_turn_num,
            "max_turns": max_turns,
            "evaluated_turn": evaluated_summary,
            "decision": "completed",
            "next_question": None,
            "interviewer_response": None,
            "interviewer_response_type": None,
            "interviewer_style": effective_style
        }

    # Bounded prior turns for interviewer context (recent 2 turns)
    prev_turns_rows = connection.execute(
        """
        SELECT st.turn_number, st.question_text, a.answer, q.category
        FROM session_turns st
        LEFT JOIN answers a ON st.answer_id = a.id
        LEFT JOIN questions q ON st.question_id = q.id
        WHERE st.session_id = ? AND st.turn_number < ?
        ORDER BY st.turn_number ASC
        """,
        (session_id, current_turn_num)
    ).fetchall()
    recent_turns = [dict(r) for r in prev_turns_rows]

    current_cat = (
        pending_turn["question_category"]
        or pending_turn["parent_category"]
        or session_row["category"]
        or "Technical"
    )
    current_diff = (
        pending_turn["question_difficulty"]
        or pending_turn["parent_difficulty"]
        or session_row["difficulty"]
        or "medium"
    )

    # 6. Apply Follow-Up Decision Rules:
    # Rule A: Circuit Breaker - At most 1 consecutive follow-up
    # If the current turn was already a follow-up, move to a new bank question.
    is_consecutive_follow_up = bool(pending_turn["is_follow_up"])

    # Rule B: Score-based decision
    score = evaluation.score
    has_missing_points = bool(evaluation.missing_points and len(evaluation.missing_points) > 0)

    should_ask_follow_up = (
        not is_consecutive_follow_up and
        (3 <= score <= 6) and
        has_missing_points
    )

    next_turn_num = current_turn_num + 1

    if should_ask_follow_up:
        # Determine category and difficulty for context:
        # Follow-up MUST inherit the canonical category of the question being probed!
        follow_up_cat = (
            pending_turn["question_category"]
            or pending_turn["parent_category"]
            or session_row["category"]
            or "Technical"
        )
        diff = strategy_engine.normalize_difficulty(current_diff)

        follow_up_text = generate_follow_up_question(
            original_question=pending_turn["question_text"],
            candidate_answer=answer_text,
            evaluation_feedback=evaluation.feedback,
            missing_points=evaluation.missing_points,
            category=follow_up_cat,
            difficulty=diff
        )

        # Modification 1: Store generated question_text on turn with question_id = NULL
        turn_cursor = connection.execute(
            """
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, status)
            VALUES (?, ?, NULL, ?, 1, ?, 'pending')
            """,
            (session_id, next_turn_num, follow_up_text, pending_turn["id"])
        )

        connection.execute(
            "UPDATE interview_sessions SET current_turn = ? WHERE id = ?",
            (next_turn_num, session_id)
        )

        connection.commit()

        profile_dict = json.loads(session_row["candidate_profile"]) if ("candidate_profile" in session_row.keys() and session_row["candidate_profile"]) else None
        job_dict = json.loads(session_row["job_context"]) if ("job_context" in session_row.keys() and session_row["job_context"]) else None

        # Phase 8: Conversational wording for follow-up
        interviewer_ctx = interviewer.build_interviewer_context(
            current_category=current_cat,
            current_difficulty=current_diff,
            current_question=pending_turn["question_text"],
            candidate_answer=answer_text,
            evaluation_feedback=evaluation.feedback,
            missing_points=evaluation.missing_points,
            strategy_action="follow_up",
            next_category=follow_up_cat,
            next_difficulty=diff,
            next_question_text=follow_up_text,
            recent_turns=recent_turns,
            target_role=session_row["target_role"] if "target_role" in session_row.keys() else None,
            experience_level=session_row["experience_level"] if "experience_level" in session_row.keys() else "mid",
            candidate_profile=profile_dict,
            job_context=job_dict
        )
        try:
            interviewer_out = interviewer.generate_interviewer_response(
                context=interviewer_ctx,
                action="follow_up",
                is_same_category=True,
                style=effective_style
            )
        except Exception:
            interviewer_out = interviewer.get_deterministic_fallback(
                action="follow_up",
                is_same_category=True,
                style=effective_style,
                next_category=follow_up_cat,
                missing_points=evaluation.missing_points
            )

        return {
            "session_id": session_id,
            "status": "active",
            "current_turn": next_turn_num,
            "max_turns": max_turns,
            "evaluated_turn": evaluated_summary,
            "decision": "follow_up",
            "interviewer_response": interviewer_out.get("interviewer_response"),
            "interviewer_response_type": interviewer_out.get("response_type"),
            "interviewer_style": effective_style,
            "next_question": {
                "turn_id": turn_cursor.lastrowid,
                "turn_number": next_turn_num,
                "question_id": None,
                "question": follow_up_text,
                "is_follow_up": True
            }
        }
    else:
        # Move to deterministic strategy engine decision
        strategy_decision = strategy_engine.decide_next_turn(connection, session_id)

        if strategy_decision.get("action") == "new_bank_question" and strategy_decision.get("question"):
            next_bank_q = strategy_decision["question"]
            turn_cursor = connection.execute(
                """
                INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, status)
                VALUES (?, ?, ?, ?, 0, 'pending')
                """,
                (session_id, next_turn_num, next_bank_q["id"], next_bank_q["question"])
            )

            connection.execute(
                "UPDATE interview_sessions SET current_turn = ? WHERE id = ?",
                (next_turn_num, session_id)
            )

            connection.commit()

            # Phase 8: Conversational wording for new bank question
            next_cat = next_bank_q["category"]
            is_same_cat = bool(current_cat and next_cat and current_cat.strip().lower() == next_cat.strip().lower())

            profile_dict = json.loads(session_row["candidate_profile"]) if ("candidate_profile" in session_row.keys() and session_row["candidate_profile"]) else None
            job_dict = json.loads(session_row["job_context"]) if ("job_context" in session_row.keys() and session_row["job_context"]) else None

            interviewer_ctx = interviewer.build_interviewer_context(
                current_category=current_cat,
                current_difficulty=current_diff,
                current_question=pending_turn["question_text"],
                candidate_answer=answer_text,
                evaluation_feedback=evaluation.feedback,
                missing_points=evaluation.missing_points,
                strategy_action="new_bank_question",
                next_category=next_cat,
                next_difficulty=next_bank_q["difficulty"],
                next_question_text=next_bank_q["question"],
                recent_turns=recent_turns,
                target_role=session_row["target_role"] if "target_role" in session_row.keys() else None,
                experience_level=session_row["experience_level"] if "experience_level" in session_row.keys() else "mid",
                candidate_profile=profile_dict,
                job_context=job_dict
            )
            try:
                interviewer_out = interviewer.generate_interviewer_response(
                    context=interviewer_ctx,
                    action="new_bank_question",
                    is_same_category=is_same_cat,
                    style=effective_style
                )
            except Exception:
                interviewer_out = interviewer.get_deterministic_fallback(
                    action="new_bank_question",
                    is_same_category=is_same_cat,
                    style=effective_style,
                    next_category=next_cat
                )

            return {
                "session_id": session_id,
                "status": "active",
                "current_turn": next_turn_num,
                "max_turns": max_turns,
                "evaluated_turn": evaluated_summary,
                "decision": "new_question",
                "strategy": strategy_decision,
                "interviewer_response": interviewer_out.get("interviewer_response"),
                "interviewer_response_type": interviewer_out.get("response_type"),
                "interviewer_style": effective_style,
                "next_question": {
                    "turn_id": turn_cursor.lastrowid,
                    "turn_number": next_turn_num,
                    "question_id": next_bank_q["id"],
                    "category": next_bank_q["category"],
                    "difficulty": next_bank_q["difficulty"],
                    "question": next_bank_q["question"],
                    "is_follow_up": False
                }
            }
        else:
            # Action is "bank_exhausted" or "completed"
            connection.execute(
                """
                UPDATE interview_sessions
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (session_id,)
            )
            connection.commit()

            return {
                "session_id": session_id,
                "status": "completed",
                "current_turn": current_turn_num,
                "max_turns": max_turns,
                "evaluated_turn": evaluated_summary,
                "decision": "completed",
                "strategy": strategy_decision,
                "interviewer_response": None,
                "interviewer_response_type": None,
                "interviewer_style": interviewer_style or "professional",
                "next_question": None
            }


def get_session_summary(connection, session_id: int) -> dict | None:
    """
    Computes aggregate analytics and an overall review for a completed or active session.
    """
    session = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session is None:
        return None

    evaluated_turns = connection.execute(
        """
        SELECT st.turn_number, st.question_text, st.is_follow_up,
               e.score, e.feedback, e.technical_accuracy, e.strengths, e.missing_points
        FROM session_turns st
        JOIN answers a ON a.id = st.answer_id
        JOIN evaluations e ON e.answer_id = a.id
        WHERE st.session_id = ?
        ORDER BY st.turn_number ASC
        """,
        (session_id,)
    ).fetchall()

    if not evaluated_turns:
        state = strategy_engine.build_interview_state(connection, session_id)
        return {
            "session_id": session_id,
            "status": session["status"],
            "category": session["category"],
            "difficulty": session["difficulty"],
            "target_role": session["target_role"] if ("target_role" in session.keys() and session["target_role"]) else None,
            "experience_level": session["experience_level"] if ("experience_level" in session.keys() and session["experience_level"]) else "mid",
            "selected_categories": json.loads(session["selected_categories"]) if ("selected_categories" in session.keys() and session["selected_categories"]) else None,
            "interviewer_style": session["interviewer_style"] if ("interviewer_style" in session.keys() and session["interviewer_style"]) else "professional",
            "total_turns": 0,
            "average_score": 0.0,
            "categories_covered": state["categories_covered"],
            "coverage_target": state["coverage_target"],
            "difficulty_progression": {},
            "adaptive_summary": {
                "categories_covered": state["categories_covered"],
                "coverage_target": state["coverage_target"],
                "adaptive_follow_ups": 0,
                "difficulty_progression": {},
                "category_breakdown": []
            },
            "message": "No evaluated turns in this session yet."
        }

    scores = [r["score"] for r in evaluated_turns]
    avg_score = round(sum(scores) / len(scores), 1)

    all_strengths = []
    all_improvements = []

    for r in evaluated_turns:
        if r["strengths"]:
            try:
                all_strengths.extend(json.loads(r["strengths"]))
            except Exception:
                pass
        if r["missing_points"]:
            try:
                all_improvements.extend(json.loads(r["missing_points"]))
            except Exception:
                pass

    follow_up_count = sum(1 for r in evaluated_turns if r["is_follow_up"])
    bank_count = len(evaluated_turns) - follow_up_count

    if avg_score >= 8.0:
        recommendation = "Outstanding performance! You demonstrated strong depth, accuracy, and clear communication across technical questions."
    elif avg_score >= 6.0:
        recommendation = "Solid performance. You grasp the fundamentals well; focus on explaining production trade-offs and edge cases."
    else:
        recommendation = "Needs improvement. Review the core concepts highlighted in the feedback below and practice explaining technical mechanisms."

    # Phase 7 Adaptive Strategy Summary
    state = strategy_engine.build_interview_state(connection, session_id)
    categories_covered = state["categories_covered"]
    coverage_target = state["coverage_target"]

    difficulty_progression = {}
    category_breakdown = []
    for cat_name, cat_state in state["categories"].items():
        if cat_state["bank_questions_asked"] > 0:
            prog_str = " -> ".join(cat_state["difficulty_history"]) if cat_state["difficulty_history"] else ""
            difficulty_progression[cat_name] = prog_str
            category_breakdown.append({
                "category": cat_name,
                "bank_questions_asked": cat_state["bank_questions_asked"],
                "evaluated_answers_count": cat_state["evaluated_bank_answers_count"],
                "average_score": cat_state["average_score"],
                "state": cat_state["state"],
                "difficulty_progression": prog_str
            })

    adaptive_summary = {
        "categories_covered": categories_covered,
        "coverage_target": coverage_target,
        "adaptive_follow_ups": follow_up_count,
        "difficulty_progression": difficulty_progression,
        "category_breakdown": category_breakdown
    }

    # Check if speech analytics exist for turns in this session
    sa_rows = connection.execute(
        """
        SELECT sa.*
        FROM speech_analytics sa
        JOIN session_turns st ON st.answer_id = sa.answer_id
        WHERE st.session_id = ?
        """,
        (session_id,)
    ).fetchall()

    speech_summary = None
    if sa_rows:
        deliv_scores = [r["delivery_score"] for r in sa_rows]
        avg_deliv = round(sum(deliv_scores) / len(deliv_scores), 1)
        tot_speaking = round(sum(r["speaking_duration_seconds"] for r in sa_rows), 1)
        tot_audio = round(sum(r["audio_duration_seconds"] for r in sa_rows), 1)
        avg_wpm = round(sum(r["speaking_rate_wpm"] for r in sa_rows) / len(sa_rows), 1)
        tot_fillers = sum(r["filler_word_count"] for r in sa_rows)
        speech_summary = {
            "turns_with_audio": len(sa_rows),
            "average_delivery_score": avg_deliv,
            "total_speaking_duration_seconds": tot_speaking,
            "total_audio_duration_seconds": tot_audio,
            "average_speaking_rate_wpm": avg_wpm,
            "total_filler_words": tot_fillers
        }

    # Check if nonverbal analytics exist for turns in this session
    nv_rows = connection.execute(
        """
        SELECT nv.*
        FROM nonverbal_analytics nv
        JOIN session_turns st ON st.answer_id = nv.answer_id
        WHERE st.session_id = ?
        """,
        (session_id,)
    ).fetchall()

    nonverbal_summary = None
    if nv_rows:
        nv_scores = [r["nonverbal_telemetry_score"] for r in nv_rows]
        avg_nv_score = round(sum(nv_scores) / len(nv_scores), 1)

        gaze_vals = [r["gaze_deviation_ratio"] for r in nv_rows if r["gaze_deviation_ratio"] is not None]
        avg_gaze = round(sum(gaze_vals) / len(gaze_vals), 2) if gaze_vals else None

        motion_vals = [r["head_motion_frequency_hz"] for r in nv_rows if r["head_motion_frequency_hz"] is not None]
        avg_motion_freq = round(sum(motion_vals) / len(motion_vals), 2) if motion_vals else None

        flags_count = 0
        for r in nv_rows:
            if r["camera_quality_flags"]:
                try:
                    fl = json.loads(r["camera_quality_flags"])
                    if fl:
                        flags_count += 1
                except Exception:
                    pass

        nonverbal_summary = {
            "turns_with_video": len(nv_rows),
            "average_nonverbal_score": avg_nv_score,
            "average_gaze_deviation_ratio": avg_gaze,
            "average_head_motion_frequency_hz": avg_motion_freq,
            "turns_with_camera_quality_flags": flags_count
        }

    return {
        "session_id": session_id,
        "status": session["status"],
        "category": session["category"],
        "difficulty": session["difficulty"],
        "target_role": session["target_role"] if ("target_role" in session.keys() and session["target_role"]) else None,
        "experience_level": session["experience_level"] if ("experience_level" in session.keys() and session["experience_level"]) else "mid",
        "selected_categories": json.loads(session["selected_categories"]) if ("selected_categories" in session.keys() and session["selected_categories"]) else None,
        "interviewer_style": session["interviewer_style"] if ("interviewer_style" in session.keys() and session["interviewer_style"]) else "professional",
        "candidate_profile": json.loads(session["candidate_profile"]) if ("candidate_profile" in session.keys() and session["candidate_profile"]) else None,
        "job_context": json.loads(session["job_context"]) if ("job_context" in session.keys() and session["job_context"]) else None,
        "total_turns_evaluated": len(evaluated_turns),
        "bank_questions_count": bank_count,
        "follow_up_questions_count": follow_up_count,
        "average_score": avg_score,
        "categories_covered": categories_covered,
        "coverage_target": coverage_target,
        "difficulty_progression": difficulty_progression,
        "adaptive_summary": adaptive_summary,
        "speech_summary": speech_summary,
        "nonverbal_summary": nonverbal_summary,
        "score_breakdown": [
            {
                "turn_number": r["turn_number"],
                "question": r["question_text"],
                "score": r["score"],
                "is_follow_up": bool(r["is_follow_up"])
            }
            for r in evaluated_turns
        ],
        "top_strengths": list(dict.fromkeys(all_strengths))[:5],
        "key_areas_for_improvement": list(dict.fromkeys(all_improvements))[:5],
        "overall_recommendation": recommendation
    }
