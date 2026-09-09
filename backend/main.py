from database import create_tables, get_db
from typing import Literal
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query

app = FastAPI()
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
    question: str = Field(min_length=5)
    answer: str = Field(min_length=10)


@app.post("/answers")
def submit_answer(interview_answer: InterviewAnswer):
    connection = get_db()

    cursor = connection.execute(
        "INSERT INTO answers (question, answer) VALUES (?, ?)",
        (interview_answer.question, interview_answer.answer)
    )

    connection.commit()

    new_answer = {
        "id": cursor.lastrowid,
        "question": interview_answer.question,
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
        "SELECT id, question, answer FROM answers"
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]

@app.get("/answers/{answer_id}")
def get_answer(answer_id: int):
    connection = get_db()

    row = connection.execute(
        "SELECT id, question, answer FROM answers WHERE id = ?",
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

    cursor = connection.execute(
        """
        UPDATE answers
        SET question = ?, answer = ?
        WHERE id = ?
        """,
        (updated_answer.question, updated_answer.answer, answer_id)
    )

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Answer not found")

    return {
        "message": "Answer updated!",
        "answer": {
            "id": answer_id,
            "question": updated_answer.question,
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
        "INSERT INTO answers (question, answer) VALUES (?, ?)",
        (question_row["question"], submission.answer)
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
        SELECT id, question, answer
        FROM answers
        WHERE question = ?
        ORDER BY id DESC
        """,
        (question_row["question"],)
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
        "SELECT answer FROM answers WHERE id = ?",
        (answer_id,)
    ).fetchone()

    connection.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Answer not found")

    word_count = len(row["answer"].split())

    if word_count < 15:
        feedback = "Your answer is too short. Add more explanation and an example."
    elif word_count < 40:
        feedback = "Good start. Add a specific example to make your answer stronger."
    else:
        feedback = "Strong detailed answer. Keep your explanation structured and clear."

    return {
        "answer_id": answer_id,
        "word_count": word_count,
        "feedback": feedback
    }
