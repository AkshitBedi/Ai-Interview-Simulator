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


def select_next_bank_question(connection, session_id: int, category: str | None = None, difficulty: str | None = None):
    """
    Selects a bank question that has NOT already been asked in this session.
    Prioritizes the session's category and difficulty if available.
    """
    base_query = """
        SELECT id, category, difficulty, question
        FROM questions
        WHERE id NOT IN (
            SELECT question_id FROM session_turns
            WHERE session_id = ? AND question_id IS NOT NULL
        )
    """

    # 1. Try matching both category and difficulty
    if category and difficulty:
        row = connection.execute(
            base_query + " AND category = ? AND difficulty = ? ORDER BY RANDOM() LIMIT 1",
            (session_id, category, difficulty)
        ).fetchone()
        if row:
            return dict(row)

    # 2. Try matching category
    if category:
        row = connection.execute(
            base_query + " AND category = ? ORDER BY RANDOM() LIMIT 1",
            (session_id, category)
        ).fetchone()
        if row:
            return dict(row)

    # 3. Try matching difficulty
    if difficulty:
        row = connection.execute(
            base_query + " AND difficulty = ? ORDER BY RANDOM() LIMIT 1",
            (session_id, difficulty)
        ).fetchone()
        if row:
            return dict(row)

    # 4. Fallback: Any unasked question
    row = connection.execute(
        base_query + " ORDER BY RANDOM() LIMIT 1",
        (session_id,)
    ).fetchone()

    return dict(row) if row else None


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


def start_session(
    connection,
    category: str | None = None,
    difficulty: str | None = None,
    max_turns: int = 5
) -> dict:
    """
    Initializes a new interview session and selects the first question.
    """
    cursor = connection.execute(
        """
        INSERT INTO interview_sessions (category, difficulty, max_turns, status, current_turn)
        VALUES (?, ?, ?, 'active', 1)
        """,
        (category, difficulty, max_turns)
    )
    session_id = cursor.lastrowid

    # Select first bank question
    first_q = select_next_bank_question(connection, session_id, category, difficulty)
    if not first_q:
        raise ValueError("No questions available to start the interview session.")

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
        "category": category,
        "difficulty": difficulty,
        "max_turns": max_turns,
        "status": "active",
        "current_turn": 1,
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


def get_session_details(connection, session_id: int) -> dict:
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
        "active_question": active_turn,
        "turns": turns
    }


def record_answer_and_advance(
    connection,
    session_id: int,
    answer_text: str,
    evaluation,
    speech_metrics: dict | None = None,
    nonverbal_metrics: dict | None = None
) -> dict:
    """
    Records the candidate's answer for the active turn, persists the evaluation,
    applies follow-up decision logic, and advances the session.
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

    pending_turn = connection.execute(
        """
        SELECT * FROM session_turns
        WHERE session_id = ? AND status = 'pending'
        ORDER BY turn_number ASC LIMIT 1
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
            "next_question": None
        }

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
        # Determine category and difficulty for context
        cat = session_row["category"] or "Technical"
        diff = session_row["difficulty"] or "medium"

        follow_up_text = generate_follow_up_question(
            original_question=pending_turn["question_text"],
            candidate_answer=answer_text,
            evaluation_feedback=evaluation.feedback,
            missing_points=evaluation.missing_points,
            category=cat,
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

        return {
            "session_id": session_id,
            "status": "active",
            "current_turn": next_turn_num,
            "max_turns": max_turns,
            "evaluated_turn": evaluated_summary,
            "decision": "follow_up",
            "next_question": {
                "turn_id": turn_cursor.lastrowid,
                "turn_number": next_turn_num,
                "question_id": None,
                "question": follow_up_text,
                "is_follow_up": True
            }
        }
    else:
        # Move to a new bank question (excluding previously asked questions)
        next_bank_q = select_next_bank_question(
            connection,
            session_id,
            category=session_row["category"],
            difficulty=session_row["difficulty"]
        )

        if next_bank_q:
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

            return {
                "session_id": session_id,
                "status": "active",
                "current_turn": next_turn_num,
                "max_turns": max_turns,
                "evaluated_turn": evaluated_summary,
                "decision": "new_question",
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
            # Bank exhausted
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
                "next_question": None
            }


def get_session_summary(connection, session_id: int) -> dict:
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
        return {
            "session_id": session_id,
            "status": session["status"],
            "total_turns": 0,
            "average_score": 0.0,
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
        "total_turns_evaluated": len(evaluated_turns),
        "bank_questions_count": bank_count,
        "follow_up_questions_count": follow_up_count,
        "average_score": avg_score,
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
