from database import create_tables, get_db
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException

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