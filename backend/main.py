import json
try:
    # Works when started from the repository root: uvicorn backend.main:app
    from .database import create_tables, get_db
    from .evaluator import evaluate_interview_answer
    from .interview_engine import (
        start_session,
        get_session_details,
        record_answer_and_advance,
        get_session_summary
    )
except ImportError:
    # Works when started inside backend: uvicorn main:app
    from database import create_tables, get_db
    from evaluator import evaluate_interview_answer
    from interview_engine import (
        start_session,
        get_session_details,
        record_answer_and_advance,
        get_session_summary
    )
from typing import Literal
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query
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
    difficulty: Literal["beginner", "medium", "hard"]
    question: str = Field(min_length=10)

@app.post("/questions")
def create_question(interview_question: InterviewQuestion):
    connection = get_db()

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
    difficulty: Literal["beginner", "medium", "hard"]
    question: str = Field(min_length=10)

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
    difficulty: Literal["beginner", "medium", "hard"] | None = None
    max_turns: int = Field(default=5, ge=1, le=20)


class SessionAnswerSubmission(BaseModel):
    answer: str = Field(min_length=10)


@app.post("/sessions", status_code=201)
def create_session(session_data: SessionCreate):
    connection = get_db()
    try:
        result = start_session(
            connection=connection,
            category=session_data.category,
            difficulty=session_data.difficulty,
            max_turns=session_data.max_turns
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
        SELECT st.*, q.category AS q_cat, q.difficulty AS q_diff
        FROM session_turns st
        LEFT JOIN questions q ON q.id = st.question_id
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
    cat = pending_turn["q_cat"] or session_row["category"] or "Technical"
    diff = pending_turn["q_diff"] or session_row["difficulty"] or "medium"

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
            evaluation=evaluation
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
