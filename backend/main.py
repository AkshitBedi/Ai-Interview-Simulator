import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

# Ensure repo root and backend directory are in sys.path so modules can be imported
# consistently whether launched from repository root or from inside backend/
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

for _dir in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

try:
    # Works when started from the repository root: uvicorn backend.main:app
    from .database import create_tables, get_db
    from .evaluator import evaluate_interview_answer
    from .interview_engine import (
        start_session,
        get_session_details,
        record_answer_and_advance,
        get_session_summary,
        normalize_session_configuration
    )
    from .document_processor import extract_documents_concurrently
    from .speech_engine import transcribe_audio, TranscriptionError, is_stt_available
    from .audio_analyzer import (
        parse_wav_samples,
        analyze_audio_waveform,
        analyze_transcript_delivery,
        calculate_delivery_score,
        process_audio_and_transcript
    )
    from .vision_analyzer import (
        process_video,
        get_vision_status,
        VisionProcessingError
    )
    from .analytics import get_analytics_overview, get_analytics_history
    from .insights_engine import get_analytics_insights
    from .coaching import (
        build_coaching_signals,
        generate_coaching_report,
        SessionNotFoundError,
        IncompleteSessionError
    )
    from .question_bank import (
        normalize_difficulty,
        serialize_string_list,
        parse_string_list,
        parse_question_row,
    )
except (ImportError, ValueError):
    # Works when started inside backend: uvicorn main:app
    from database import create_tables, get_db
    from evaluator import evaluate_interview_answer
    from interview_engine import (
        start_session,
        get_session_details,
        record_answer_and_advance,
        get_session_summary,
        normalize_session_configuration
    )
    from document_processor import extract_documents_concurrently
    from speech_engine import transcribe_audio, TranscriptionError, is_stt_available
    from audio_analyzer import (
        parse_wav_samples,
        analyze_audio_waveform,
        analyze_transcript_delivery,
        calculate_delivery_score,
        process_audio_and_transcript
    )
    from vision_analyzer import (
        process_video,
        get_vision_status,
        VisionProcessingError
    )
    from analytics import get_analytics_overview, get_analytics_history
    from insights_engine import get_analytics_insights
    from coaching import (
        build_coaching_signals,
        generate_coaching_report,
        SessionNotFoundError,
        IncompleteSessionError
    )
    from question_bank import (
        normalize_difficulty,
        serialize_string_list,
        parse_string_list,
        parse_question_row,
    )
from typing import Literal, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
create_tables()

@app.get("/")
def home():
    return {"message": "Hello, FastAPI!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/hello/{name}")
def say_hello(name: str):
    return {"message": f"Hello, {name}!"}

class InterviewAnswer(BaseModel):
    question_id: int
    answer: str = Field(min_length=10)


@app.post("/answers")
def submit_answer(interview_answer: InterviewAnswer):
    connection = get_db()

    question_row = connection.execute(
        "SELECT question FROM questions WHERE id = ?",
        (interview_answer.question_id,)
    ).fetchone()

    if question_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Question not found")

    cursor = connection.execute(
        "INSERT INTO answers (question_id, answer) VALUES (?, ?)",
        (interview_answer.question_id, interview_answer.answer)
    )

    connection.commit()

    new_answer = {
        "id": cursor.lastrowid,
        "question_id": interview_answer.question_id,
        "question": question_row["question"],
        "answer": interview_answer.answer
    }

    connection.close()

    return {
        "message": "Answer saved to database!",
        "answer": new_answer
    }

@app.get("/answers")
def get_answers():
    connection = get_db()

    rows = connection.execute(
        """
        SELECT answers.id, answers.question_id, questions.question, answers.answer
        FROM answers
        JOIN questions ON questions.id = answers.question_id
        ORDER BY answers.id DESC
        """
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]

@app.get("/answers/{answer_id}")
def get_answer(answer_id: int):
    connection = get_db()

    row = connection.execute(
        """
        SELECT answers.id, answers.question_id, questions.question, answers.answer
        FROM answers
        JOIN questions ON questions.id = answers.question_id
        WHERE answers.id = ?
        """,
        (answer_id,)
    ).fetchone()

    connection.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Answer not found")

    return dict(row)

@app.delete("/answers/{answer_id}")
def delete_answer(answer_id: int):
    connection = get_db()

    cursor = connection.execute(
        "DELETE FROM answers WHERE id = ?",
        (answer_id,)
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Answer not found")

    return {"message": "Answer deleted"}

@app.put("/answers/{answer_id}")
def update_answer(answer_id: int, updated_answer: InterviewAnswer):
    connection = get_db()

    question_row = connection.execute(
        "SELECT question FROM questions WHERE id = ?",
        (updated_answer.question_id,)
    ).fetchone()

    if question_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Question not found")

    cursor = connection.execute(
        """
        UPDATE answers
        SET question_id = ?, answer = ?
        WHERE id = ?
        """,
        (
            updated_answer.question_id,
            updated_answer.answer,
            answer_id,
        )
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Answer not found")

    return {
        "message": "Answer updated!",
        "answer": {
            "id": answer_id,
            "question_id": updated_answer.question_id,
            "question": question_row["question"],
            "answer": updated_answer.answer
        }
    }
class AnswerSubmission(BaseModel):
    answer: str = Field(min_length=10)
    interviewer_style: str | None = Field(default="professional")

@app.get("/questions/random")
def get_random_question(
    category: str | None = None,
    difficulty: str | None = None
):
    connection = get_db()

    query = """
        SELECT id, category, difficulty, question
        FROM questions
    """
    values = []

    if category is not None:
        query += " WHERE category = ?"
        values.append(category)

    if difficulty is not None:
        query += " AND difficulty = ?" if category is not None else " WHERE difficulty = ?"
        values.append(difficulty)

    query += " ORDER BY RANDOM() LIMIT 1"

    row = connection.execute(query, values).fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No matching questions available"
        )

    return {"question": dict(row)}

@app.get("/questions/{question_id}")
def get_question(question_id: int):
    connection = get_db()

    row = connection.execute(
        """
        SELECT id, category, difficulty, question
        FROM questions
        WHERE id = ?
        """,
        (question_id,)
    ).fetchone()

    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Question not found"
        )

    return {"question": dict(row)}

class InterviewQuestion(BaseModel):
    category: str = Field(min_length=2)
    difficulty: Literal["beginner", "easy", "medium", "hard"]
    question: str = Field(min_length=10)
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    question_type: Optional[str] = None
    skill_type: Optional[str] = None
    quality_tier: Optional[str] = "core"
    expected_concepts: Optional[list[str]] = None
    common_mistakes: Optional[list[str]] = None
    ideal_answer_points: Optional[list[str]] = None
    prerequisites: Optional[list[str]] = None

@app.post("/questions")
def create_question(interview_question: InterviewQuestion):
    """
    Creates a new question in the question bank.

    QUALITY_VALIDATION_POLICY: AUDIT_ONLY
    Question metadata validation and duplicate detection are authoring/CI/audit safeguards;
    runtime question insertion is not currently gated by them.
    """
    connection = get_db()
    cols = {row["name"] for row in connection.execute("PRAGMA table_info(questions)").fetchall()}

    if "topic" in cols:
        cursor = connection.execute(
            """
            INSERT INTO questions (
                category, difficulty, question,
                topic, subtopic, question_type, skill_type, quality_tier,
                expected_concepts, common_mistakes, ideal_answer_points, prerequisites
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interview_question.category,
                interview_question.difficulty,
                interview_question.question,
                interview_question.topic,
                interview_question.subtopic,
                interview_question.question_type,
                interview_question.skill_type,
                interview_question.quality_tier or "core",
                json.dumps(interview_question.expected_concepts or []),
                json.dumps(interview_question.common_mistakes or []),
                json.dumps(interview_question.ideal_answer_points or []),
                json.dumps(interview_question.prerequisites or []),
            )
        )
    else:
        cursor = connection.execute(
            """
            INSERT INTO questions (category, difficulty, question)
            VALUES (?, ?, ?)
            """,
            (
                interview_question.category,
                interview_question.difficulty,
                interview_question.question
            )
        )

    connection.commit()

    new_question = {
        "id": cursor.lastrowid,
        "category": interview_question.category,
        "difficulty": interview_question.difficulty,
        "question": interview_question.question
    }
    if interview_question.topic is not None:
        new_question["topic"] = interview_question.topic

    connection.close()

    return {
        "message": "Question created!",
        "question": new_question
    }


@app.get("/questions")
def get_questions(
    category: str | None = None,
    difficulty: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    connection = get_db()

    query = """
        SELECT id, category, difficulty, question
        FROM questions
    """
    values = []

    if category is not None:
        query += " WHERE category = ?"
        values.append(category)

    if difficulty is not None:
        query += " AND difficulty = ?" if category is not None else " WHERE difficulty = ?"
        values.append(difficulty)

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    values.extend([limit, offset])

    rows = connection.execute(query, values).fetchall()
    connection.close()

    return {"questions": [dict(row) for row in rows]}


class InterviewQuestionUpdate(BaseModel):
    category: str = Field(min_length=2)
    difficulty: Literal["beginner", "easy", "medium", "hard"]
    question: str = Field(min_length=10)
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    question_type: Optional[str] = None
    skill_type: Optional[str] = None
    quality_tier: Optional[str] = "core"
    expected_concepts: Optional[list[str]] = None
    common_mistakes: Optional[list[str]] = None
    ideal_answer_points: Optional[list[str]] = None
    prerequisites: Optional[list[str]] = None

@app.put("/questions/{question_id}")
def update_question(question_id: int, updated_question: InterviewQuestionUpdate):
    connection = get_db()

    cursor = connection.execute(
        """
        UPDATE questions
        SET category = ?, difficulty = ?, question = ?
        WHERE id = ?
        """,
        (
            updated_question.category,
            updated_question.difficulty,
            updated_question.question,
            question_id
        )
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Question not found")

    return {"message": "Question updated!"}

@app.delete("/questions/{question_id}")
def delete_question(question_id: int):
    connection = get_db()

    # Supports both new databases (which use ON DELETE CASCADE) and databases
    # migrated from the earlier text-based answers table.
    connection.execute(
        "DELETE FROM answers WHERE question_id = ?",
        (question_id,)
    )

    cursor = connection.execute(
        "DELETE FROM questions WHERE id = ?",
        (question_id,)
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Question not found")

    return {"message": "Question deleted"}

@app.get("/stats")
def get_stats():
    connection = get_db()

    question_count = connection.execute(
        "SELECT COUNT(*) FROM questions"
    ).fetchone()[0]

    answer_count = connection.execute(
        "SELECT COUNT(*) FROM answers"
    ).fetchone()[0]

    connection.close()

    return {
        "total_questions": question_count,
        "total_answers": answer_count
    }
@app.post("/questions/{question_id}/answers")
def answer_question(question_id: int, submission: AnswerSubmission):
    connection = get_db()

    question_row = connection.execute(
        "SELECT question FROM questions WHERE id = ?",
        (question_id,)
    ).fetchone()

    if question_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Question not found")

    cursor = connection.execute(
        "INSERT INTO answers (question_id, answer) VALUES (?, ?)",
        (question_id, submission.answer)
    )

    connection.commit()
    connection.close()

    return {
        "message": "Answer submitted!",
        "answer_id": cursor.lastrowid,
        "question_id": question_id
    }

@app.get("/questions/{question_id}/answers")
def get_question_answers(question_id: int):
    connection = get_db()

    question_row = connection.execute(
        "SELECT question FROM questions WHERE id = ?",
        (question_id,)
    ).fetchone()

    if question_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Question not found")

    answer_rows = connection.execute(
        """
        SELECT id, question_id, answer
        FROM answers
        WHERE question_id = ?
        ORDER BY id DESC
        """,
        (question_id,)
    ).fetchall()

    connection.close()

    return {
        "question_id": question_id,
        "question": question_row["question"],
        "answers": [dict(row) for row in answer_rows]
    }

@app.get("/answers/{answer_id}/feedback")
def get_answer_feedback(answer_id: int):
    connection = get_db()

    row = connection.execute(
        """
        SELECT answers.id AS answer_id, answers.answer,
               questions.id AS question_id, questions.question,
               questions.category, questions.difficulty
        FROM answers
        JOIN questions ON questions.id = answers.question_id
        WHERE answers.id = ?
        """,
        (answer_id,)
    ).fetchone()

    if row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Answer not found")

    # Check if this answer was already evaluated and cached
    cached_eval = connection.execute(
        """
        SELECT score, feedback, technical_accuracy, strengths, missing_points
        FROM evaluations
        WHERE answer_id = ?
        """,
        (answer_id,)
    ).fetchone()

    if cached_eval is not None:
        connection.close()
        strengths = json.loads(cached_eval["strengths"]) if cached_eval["strengths"] else []
        missing_points = json.loads(cached_eval["missing_points"]) if cached_eval["missing_points"] else []
        return {
            "answer_id": answer_id,
            "question_id": row["question_id"],
            "question": row["question"],
            "word_count": len(row["answer"].split()),
            "score": cached_eval["score"],
            "feedback": cached_eval["feedback"],
            "technical_accuracy": cached_eval["technical_accuracy"],
            "strengths": strengths,
            "missing_points": missing_points,
            "cached": True
        }

    # Evaluate the answer in the specific context of the question
    evaluation = evaluate_interview_answer(
        question=row["question"],
        category=row["category"],
        difficulty=row["difficulty"],
        answer=row["answer"]
    )

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

    connection.commit()
    connection.close()

    return {
        "answer_id": answer_id,
        "question_id": row["question_id"],
        "question": row["question"],
        "word_count": len(row["answer"].split()),
        "score": evaluation.score,
        "feedback": evaluation.feedback,
        "technical_accuracy": evaluation.technical_accuracy,
        "strengths": evaluation.strengths,
        "missing_points": evaluation.missing_points,
        "evaluator": getattr(evaluation, "evaluator", "ai-evaluator"),
        "cached": False
    }


class SessionCreate(BaseModel):
    category: str | None = None
    categories: list[str] | None = None
    difficulty: Literal["beginner", "medium", "hard"] | None = None
    max_turns: int = Field(default=5, ge=1, le=20)
    target_role: str | None = None
    experience_level: Literal["junior", "mid", "senior"] | None = "mid"
    interviewer_style: Literal["professional", "conversational", "strict"] | None = "professional"
    resume_text: str | None = Field(default=None, max_length=15000)
    job_description: str | None = Field(default=None, max_length=10000)


class SessionAnswerSubmission(BaseModel):
    answer: str = Field(min_length=10)
    interviewer_style: Literal["professional", "conversational", "strict"] | None = None


@app.post("/sessions", status_code=201)
async def create_session(session_data: SessionCreate):
    # STEP 1-4: Configuration pre-validation BEFORE any Gemini call (Correction #4)
    try:
        normalize_session_configuration(
            category=session_data.category,
            categories=session_data.categories,
            target_role=session_data.target_role,
            experience_level=session_data.experience_level,
            interviewer_style=session_data.interviewer_style
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Normalize inputs
    clean_resume = session_data.resume_text.strip() if session_data.resume_text and session_data.resume_text.strip() else None
    clean_jd = session_data.job_description.strip() if session_data.job_description and session_data.job_description.strip() else None

    # Length checks
    if clean_resume and len(clean_resume) > 15000:
        raise HTTPException(status_code=400, detail="resume_text exceeds 15,000 characters.")
    if clean_jd and len(clean_jd) > 10000:
        raise HTTPException(status_code=400, detail="job_description exceeds 10,000 characters.")

    # STEP 5: Concurrent document extraction (Correction #3)
    candidate_profile = None
    job_context = None
    if clean_resume or clean_jd:
        profile_obj, job_obj = await extract_documents_concurrently(clean_resume, clean_jd)
        candidate_profile = profile_obj.model_dump() if profile_obj else None
        job_context = job_obj.model_dump() if job_obj else None

    connection = get_db()
    try:
        result = start_session(
            connection=connection,
            category=session_data.category,
            categories=session_data.categories,
            difficulty=session_data.difficulty,
            max_turns=session_data.max_turns,
            target_role=session_data.target_role,
            experience_level=session_data.experience_level,
            interviewer_style=session_data.interviewer_style,
            candidate_profile=candidate_profile,
            job_context=job_context
        )
    except ValueError as e:
        connection.close()
        raise HTTPException(status_code=400, detail=str(e))

    connection.close()
    return result


@app.get("/sessions/{session_id}")
def get_session(session_id: int):
    connection = get_db()
    data = get_session_details(connection, session_id)
    connection.close()

    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return data


@app.post("/sessions/{session_id}/answer")
def submit_session_answer(session_id: int, submission: SessionAnswerSubmission):
    connection = get_db()

    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Session not found")

    if session_row["status"] != "active":
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="Interview session is already completed or inactive."
        )

    pending_turn = connection.execute(
        """
        SELECT st.*,
               q.category AS q_cat,
               q.difficulty AS q_diff,
               parent_q.category AS parent_category,
               parent_q.difficulty AS parent_difficulty
        FROM session_turns st
        LEFT JOIN questions q ON q.id = st.question_id
        LEFT JOIN session_turns parent_st ON st.parent_turn_id = parent_st.id
        LEFT JOIN questions parent_q ON parent_st.question_id = parent_q.id
        WHERE st.session_id = ? AND st.status = 'pending'
        ORDER BY st.turn_number ASC LIMIT 1
        """,
        (session_id,)
    ).fetchone()

    if pending_turn is None:
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="No active question pending an answer in this session."
        )

    # Determine topic & difficulty for evaluation context
    cat = pending_turn["q_cat"] or pending_turn["parent_category"] or session_row["category"] or "Technical"
    diff = pending_turn["q_diff"] or pending_turn["parent_difficulty"] or session_row["difficulty"] or "medium"

    # Context-aware evaluation: Evaluates both question and answer!
    evaluation = evaluate_interview_answer(
        question=pending_turn["question_text"],
        category=cat,
        difficulty=diff,
        answer=submission.answer
    )

    try:
        result = record_answer_and_advance(
            connection=connection,
            session_id=session_id,
            answer_text=submission.answer,
            evaluation=evaluation,
            interviewer_style=submission.interviewer_style
        )
    except Exception as e:
        connection.close()
        raise HTTPException(status_code=500, detail=str(e))

    connection.close()
    return result


@app.get("/sessions/{session_id}/summary")
def get_session_summary_endpoint(session_id: int):
    connection = get_db()
    summary = get_session_summary(connection, session_id)
    connection.close()

    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return summary


@app.get("/sessions/{session_id}/coaching")
def get_session_coaching_endpoint(session_id: int):
    """
    Phase 9: Advanced Performance Coaching for completed sessions.
    Returns deterministic signals + Gemini coaching explanation (or deterministic fallback).
    """
    connection = get_db()
    try:
        signals = build_coaching_signals(connection, session_id)
    except SessionNotFoundError as e:
        connection.close()
        raise HTTPException(status_code=404, detail=str(e))
    except IncompleteSessionError as e:
        connection.close()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        connection.close()
        raise HTTPException(status_code=500, detail=f"Error analyzing coaching signals: {str(e)}")

    connection.close()

    try:
        report, source = generate_coaching_report(signals)
    except Exception:
        from .coaching import generate_fallback_coaching_report
        report = generate_fallback_coaching_report(signals)
        source = "deterministic"

    return {
        "session_id": session_id,
        "report": report,
        "signals": signals,
        "source": source
    }


@app.post("/sessions/{session_id}/answer-audio")
async def submit_session_audio_answer(
    session_id: int,
    file: UploadFile = File(...),
    interviewer_style: str | None = Form(None)
):
    """
    Submits a spoken audio answer (PCM WAV) to the active turn of an interview session.
    Performs signal processing, speech-to-text, delivery analysis, and technical AI evaluation.
    """
    connection = get_db()

    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Session not found")

    if session_row["status"] != "active":
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="Interview session is already completed or inactive."
        )

    pending_turn = connection.execute(
        """
        SELECT st.*,
               q.category AS q_cat,
               q.difficulty AS q_diff,
               parent_q.category AS parent_category,
               parent_q.difficulty AS parent_difficulty
        FROM session_turns st
        LEFT JOIN questions q ON q.id = st.question_id
        LEFT JOIN session_turns parent_st ON st.parent_turn_id = parent_st.id
        LEFT JOIN questions parent_q ON parent_st.question_id = parent_q.id
        WHERE st.session_id = ? AND st.status = 'pending'
        ORDER BY st.turn_number ASC LIMIT 1
        """,
        (session_id,)
    ).fetchone()

    if pending_turn is None:
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="No active question pending an answer in this session."
        )

    try:
        audio_bytes = await file.read()
    except Exception as e:
        connection.close()
        raise HTTPException(status_code=400, detail=f"Failed to read audio upload: {e}")

    if not audio_bytes or len(audio_bytes) < 44:
        connection.close()
        raise HTTPException(status_code=422, detail="Audio file is empty or corrupted.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(audio_bytes)

    try:
        # 1. Acoustic waveform signal analysis
        try:
            samples, sample_rate = parse_wav_samples(tmp_path)
            sig_metrics = analyze_audio_waveform(samples, sample_rate)
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Unable to parse audio as PCM WAV: {e}"
            )

        # 2. Speech-to-Text transcription via faster-whisper
        try:
            stt_result = transcribe_audio(tmp_path)
        except TranscriptionError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Speech transcription engine error: {e}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during transcription: {e}"
            )

        transcript_text = stt_result.get("text", "").strip()

        if not transcript_text or len(transcript_text.split()) < 2:
            raise HTTPException(
                status_code=422,
                detail="No intelligible speech detected in the audio. Please check your microphone and speak clearly."
            )

        # 3. Linguistic delivery metrics & deterministic delivery scoring
        trn_metrics = analyze_transcript_delivery(
            transcript=transcript_text,
            audio_duration_seconds=sig_metrics.audio_duration_seconds,
            speaking_duration_seconds=sig_metrics.speaking_duration_seconds
        )

        delivery_score, delivery_feedback = calculate_delivery_score(
            speaking_rate_wpm=trn_metrics.speaking_rate_wpm,
            filler_rate=trn_metrics.filler_rate,
            long_pause_count=sig_metrics.long_pause_count,
            phonation_ratio=sig_metrics.phonation_ratio,
            repeated_words_count=trn_metrics.repeated_words_count,
            word_count=trn_metrics.word_count
        )

        speech_metrics = {
            "audio_duration_seconds": sig_metrics.audio_duration_seconds,
            "speaking_duration_seconds": sig_metrics.speaking_duration_seconds,
            "pause_duration_seconds": sig_metrics.pause_duration_seconds,
            "pause_count": sig_metrics.pause_count,
            "average_pause_duration": sig_metrics.average_pause_duration,
            "long_pause_count": sig_metrics.long_pause_count,
            "phonation_ratio": sig_metrics.phonation_ratio,
            "speaking_rate_wpm": trn_metrics.speaking_rate_wpm,
            "articulation_rate_wpm": trn_metrics.articulation_rate_wpm,
            "filler_word_count": trn_metrics.filler_word_count,
            "filler_rate": trn_metrics.filler_rate,
            "filler_breakdown": trn_metrics.filler_breakdown,
            "repeated_words_count": trn_metrics.repeated_words_count,
            "delivery_score": delivery_score,
            "delivery_feedback": delivery_feedback
        }

        # 4. Context-aware technical evaluation on the transcript
        cat = pending_turn["q_cat"] or pending_turn["parent_category"] or session_row["category"] or "Technical"
        diff = pending_turn["q_diff"] or pending_turn["parent_difficulty"] or session_row["difficulty"] or "medium"

        evaluation = evaluate_interview_answer(
            question=pending_turn["question_text"],
            category=cat,
            difficulty=diff,
            answer=transcript_text
        )

        # 5. Advance session with answer, evaluation, and speech metrics
        result = record_answer_and_advance(
            connection=connection,
            session_id=session_id,
            answer_text=transcript_text,
            evaluation=evaluation,
            speech_metrics=speech_metrics,
            interviewer_style=interviewer_style
        )

        return result
    finally:
        connection.close()
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.post("/speech/analyze")
async def analyze_speech_endpoint(
    file: UploadFile = File(...),
    expected_transcript: str | None = Form(default=None)
):
    """
    Standalone endpoint to transcribe audio and compute signal + delivery metrics.
    Useful for testing, debugging, and independent communication practice.
    """
    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 44:
        raise HTTPException(status_code=422, detail="Audio file is empty or corrupted.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(audio_bytes)

    try:
        samples, sample_rate = parse_wav_samples(tmp_path)
        sig = analyze_audio_waveform(samples, sample_rate)

        if expected_transcript and expected_transcript.strip():
            transcript = expected_transcript.strip()
            stt_data = {"text": transcript, "method": "provided"}
        else:
            try:
                stt_data = transcribe_audio(tmp_path)
                transcript = stt_data.get("text", "").strip()
            except TranscriptionError as e:
                raise HTTPException(status_code=503, detail=str(e))

        trn = analyze_transcript_delivery(
            transcript,
            audio_duration_seconds=sig.audio_duration_seconds,
            speaking_duration_seconds=sig.speaking_duration_seconds
        )

        score, feedback = calculate_delivery_score(
            speaking_rate_wpm=trn.speaking_rate_wpm,
            filler_rate=trn.filler_rate,
            long_pause_count=sig.long_pause_count,
            phonation_ratio=sig.phonation_ratio,
            repeated_words_count=trn.repeated_words_count,
            word_count=trn.word_count
        )

        return {
            "transcript": transcript,
            "stt_info": stt_data,
            "acoustic_signal": {
                "audio_duration_seconds": sig.audio_duration_seconds,
                "speaking_duration_seconds": sig.speaking_duration_seconds,
                "pause_duration_seconds": sig.pause_duration_seconds,
                "pause_count": sig.pause_count,
                "average_pause_duration": sig.average_pause_duration,
                "long_pause_count": sig.long_pause_count,
                "phonation_ratio": sig.phonation_ratio
            },
            "transcript_delivery": {
                "word_count": trn.word_count,
                "speaking_rate_wpm": trn.speaking_rate_wpm,
                "articulation_rate_wpm": trn.articulation_rate_wpm,
                "filler_word_count": trn.filler_word_count,
                "filler_rate": trn.filler_rate,
                "filler_breakdown": trn.filler_breakdown,
                "repeated_words_count": trn.repeated_words_count
            },
            "delivery_score": score,
            "delivery_feedback": feedback
        }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.get("/speech/status")
def get_speech_engine_status():
    return {
        "stt_available": is_stt_available(),
        "engine": "faster-whisper",
        "model": os.getenv("WHISPER_MODEL_SIZE", "base.en")
    }


# ===========================================================================
# Phase 5: Multimodal (Video + Voice) Endpoints
# ===========================================================================

@app.post("/sessions/{session_id}/answer-multimodal")
async def submit_session_multimodal_answer(
    session_id: int,
    audio_file: UploadFile = File(...),
    video_file: UploadFile = File(...),
    interviewer_style: str | None = Form(None)
):
    """
    Submits a multimodal answer (16kHz PCM WAV audio + WebM/MP4 video) to the active turn.
    Executes independent audio signal processing, speech transcription, computer vision telemetry,
    and technical AI evaluation. Guarantees raw media cleanup in a per-request temporary directory.
    """
    connection = get_db()

    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Session not found")

    if session_row["status"] != "active":
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="Interview session is already completed or inactive."
        )

    pending_turn = connection.execute(
        """
        SELECT st.*,
               q.category AS q_cat,
               q.difficulty AS q_diff,
               parent_q.category AS parent_category,
               parent_q.difficulty AS parent_difficulty
        FROM session_turns st
        LEFT JOIN questions q ON q.id = st.question_id
        LEFT JOIN session_turns parent_st ON st.parent_turn_id = parent_st.id
        LEFT JOIN questions parent_q ON parent_st.question_id = parent_q.id
        WHERE st.session_id = ? AND st.status = 'pending'
        ORDER BY st.turn_number ASC LIMIT 1
        """,
        (session_id,)
    ).fetchone()

    if pending_turn is None:
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="No active question pending an answer in this session."
        )

    # Read uploaded media bytes
    try:
        audio_bytes = await audio_file.read()
    except Exception as e:
        connection.close()
        raise HTTPException(status_code=400, detail=f"Failed to read audio upload: {e}")

    try:
        video_bytes = await video_file.read()
    except Exception as e:
        connection.close()
        raise HTTPException(status_code=400, detail=f"Failed to read video upload: {e}")

    if not audio_bytes or len(audio_bytes) < 44:
        connection.close()
        raise HTTPException(status_code=422, detail="Audio file is empty or corrupted.")

    if not video_bytes or len(video_bytes) < 100:
        connection.close()
        raise HTTPException(status_code=422, detail="Video file is empty or corrupted.")

    # Create isolated per-request directory with guaranteed cleanup
    temp_dir = tempfile.mkdtemp(prefix="interview_multimodal_")
    audio_path = os.path.join(temp_dir, "audio.wav")
    video_path = os.path.join(temp_dir, "video.webm")

    with open(audio_path, "wb") as f_a:
        f_a.write(audio_bytes)

    with open(video_path, "wb") as f_v:
        f_v.write(video_bytes)

    try:
        # 1. Acoustic waveform signal analysis
        try:
            samples, sample_rate = parse_wav_samples(audio_path)
            sig_metrics = analyze_audio_waveform(samples, sample_rate)
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Unable to parse audio as PCM WAV: {e}"
            )

        # 2. Speech-to-Text transcription via faster-whisper
        try:
            stt_result = transcribe_audio(audio_path)
        except TranscriptionError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Speech transcription engine error: {e}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during transcription: {e}"
            )

        transcript_text = stt_result.get("text", "").strip()

        if not transcript_text or len(transcript_text.split()) < 2:
            raise HTTPException(
                status_code=422,
                detail="No intelligible speech detected in the audio. Please check your microphone and speak clearly."
            )

        # 3. Linguistic delivery metrics & deterministic delivery scoring
        trn_metrics = analyze_transcript_delivery(
            transcript=transcript_text,
            audio_duration_seconds=sig_metrics.audio_duration_seconds,
            speaking_duration_seconds=sig_metrics.speaking_duration_seconds
        )

        delivery_score, delivery_feedback = calculate_delivery_score(
            speaking_rate_wpm=trn_metrics.speaking_rate_wpm,
            filler_rate=trn_metrics.filler_rate,
            long_pause_count=sig_metrics.long_pause_count,
            phonation_ratio=sig_metrics.phonation_ratio,
            repeated_words_count=trn_metrics.repeated_words_count,
            word_count=trn_metrics.word_count
        )

        speech_metrics = {
            "audio_duration_seconds": sig_metrics.audio_duration_seconds,
            "speaking_duration_seconds": sig_metrics.speaking_duration_seconds,
            "pause_duration_seconds": sig_metrics.pause_duration_seconds,
            "pause_count": sig_metrics.pause_count,
            "average_pause_duration": sig_metrics.average_pause_duration,
            "long_pause_count": sig_metrics.long_pause_count,
            "phonation_ratio": sig_metrics.phonation_ratio,
            "speaking_rate_wpm": trn_metrics.speaking_rate_wpm,
            "articulation_rate_wpm": trn_metrics.articulation_rate_wpm,
            "filler_word_count": trn_metrics.filler_word_count,
            "filler_rate": trn_metrics.filler_rate,
            "filler_breakdown": trn_metrics.filler_breakdown,
            "repeated_words_count": trn_metrics.repeated_words_count,
            "delivery_score": delivery_score,
            "delivery_feedback": delivery_feedback
        }

        # 4. Computer vision & nonverbal telemetry analysis
        try:
            nv_result = process_video(video_path)
            nonverbal_metrics = nv_result.to_dict()
        except VisionProcessingError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Unable to process video frames: {e}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during video analysis: {e}"
            )

        # 5. Technical AI evaluation on transcript text
        cat = pending_turn["q_cat"] or pending_turn["parent_category"] or session_row["category"] or "Technical"
        diff = pending_turn["q_diff"] or pending_turn["parent_difficulty"] or session_row["difficulty"] or "medium"

        evaluation = evaluate_interview_answer(
            question=pending_turn["question_text"],
            category=cat,
            difficulty=diff,
            answer=transcript_text
        )

        # 6. Advance session with evaluation, speech, and nonverbal metrics
        result = record_answer_and_advance(
            connection=connection,
            session_id=session_id,
            answer_text=transcript_text,
            evaluation=evaluation,
            speech_metrics=speech_metrics,
            nonverbal_metrics=nonverbal_metrics,
            interviewer_style=interviewer_style
        )

        return result
    finally:
        connection.close()
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/vision/analyze")
async def analyze_vision_endpoint(video_file: UploadFile = File(...)):
    """
    Standalone diagnostic endpoint to analyze nonverbal telemetry from an uploaded video clip.
    """
    video_bytes = await video_file.read()
    if not video_bytes or len(video_bytes) < 100:
        raise HTTPException(status_code=422, detail="Video file is empty or corrupted.")

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(video_bytes)

    try:
        res = process_video(tmp_path)
        return res.to_dict()
    except VisionProcessingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during vision analysis: {e}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.get("/vision/status")
def get_vision_engine_status():
    """
    Returns the current computer vision backend status, capabilities, and health.
    """
    return get_vision_status()


@app.get("/analytics/overview")
def get_analytics_overview_endpoint():
    """
    Retrieves global deterministic analytics across all completed interview sessions.
    """
    connection = get_db()
    try:
        return get_analytics_overview(connection)
    finally:
        connection.close()


@app.get("/analytics/history")
def get_analytics_history_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """
    Retrieves paginated interview history for completed sessions.
    """
    connection = get_db()
    try:
        return get_analytics_history(connection, limit=limit, offset=offset)
    finally:
        connection.close()


@app.get("/analytics/insights")
def get_analytics_insights_endpoint():
    """
    Retrieves deterministic longitudinal performance insights across completed interview sessions.
    """
    connection = get_db()
    try:
        return get_analytics_insights(connection)
    finally:
        connection.close()
