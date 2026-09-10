import sys
import tempfile
import sqlite3
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path.cwd()))

from fastapi.testclient import TestClient
import backend.main as main
from backend.evaluator import evaluate_interview_answer, EvaluationResult
from backend.database import create_tables, get_db

def test_phase2():
    print("=== TEST 1: Database Migration & Schema ===")
    create_tables()
    conn = get_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "evaluations" in tables, f"'evaluations' table not found in: {tables}"
    eval_cols = {r["name"]: r["type"] for r in conn.execute("PRAGMA table_info(evaluations)").fetchall()}
    assert "answer_id" in eval_cols and "score" in eval_cols and "technical_accuracy" in eval_cols
    fks = [dict(r) for r in conn.execute("PRAGMA foreign_key_list(evaluations)").fetchall()]
    assert any(fk["table"] == "answers" and fk["from"] == "answer_id" and fk["to"] == "id" for fk in fks)
    conn.close()
    print("PASS: evaluations table exists with proper foreign key to answers(id)")

    print("\n=== TEST 2: Context-Aware Evaluator Verification ===")
    # Identical answer text tested against two completely different questions
    answer_sample = "It manages memory by locking execution so that only one native thread runs bytecode at a time."

    eval_relevant = evaluate_interview_answer(
        question="Explain the Global Interpreter Lock (GIL) in Python.",
        category="Python",
        difficulty="medium",
        answer=answer_sample
    )
    print("Relevant context evaluation:", eval_relevant.score, eval_relevant.feedback)

    eval_irrelevant = evaluate_interview_answer(
        question="What is the difference between TCP and UDP networking protocols?",
        category="Networking",
        difficulty="medium",
        answer=answer_sample
    )
    print("Irrelevant context evaluation:", eval_irrelevant.score, eval_irrelevant.feedback)

    assert eval_relevant.score > eval_irrelevant.score, "Relevant answer must score higher than irrelevant answer!"
    print("PASS: Evaluator scores answers based on question context, NOT answer text alone.")

    print("\n=== TEST 3: API End-to-End & Persistent Caching ===")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        temp_db = tmp.name

    try:
        def test_get_db():
            c = sqlite3.connect(temp_db)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            return c

        main.get_db = test_get_db

        # Initialize schema in temp DB
        init_conn = test_get_db()
        init_conn.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, difficulty TEXT NOT NULL, question TEXT NOT NULL)")
        init_conn.execute("CREATE TABLE answers (id INTEGER PRIMARY KEY AUTOINCREMENT, question_id INTEGER NOT NULL, answer TEXT NOT NULL, FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE)")
        init_conn.execute("""
            CREATE TABLE evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id INTEGER NOT NULL UNIQUE,
                score INTEGER NOT NULL,
                feedback TEXT NOT NULL,
                technical_accuracy TEXT,
                strengths TEXT,
                missing_points TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
            )
        """)
        init_conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Python', 'medium', 'What is the purpose of Python virtual environments?')")
        init_conn.commit()
        init_conn.close()

        client = TestClient(main.app)

        # Submit answer
        sub = client.post("/questions/1/answers", json={"answer": "Virtual environments isolate project dependencies and prevent package version conflicts across different Python projects."})
        assert sub.status_code == 200
        ans_id = sub.json()["answer_id"]

        # First request to feedback -> triggers evaluation and caches it
        fb1 = client.get(f"/answers/{ans_id}/feedback")
        assert fb1.status_code == 200
        data1 = fb1.json()
        assert data1["cached"] is False
        assert "score" in data1
        assert "technical_accuracy" in data1
        assert isinstance(data1["strengths"], list)
        assert isinstance(data1["missing_points"], list)
        print(f"First feedback call: score={data1['score']}, cached={data1['cached']}")

        # Verify record exists in evaluations table
        verify_conn = test_get_db()
        row = verify_conn.execute("SELECT * FROM evaluations WHERE answer_id = ?", (ans_id,)).fetchone()
        assert row is not None, "Evaluation record was not persisted to database"
        assert row["score"] == data1["score"]
        verify_conn.close()
        print("PASS: Evaluation result successfully persisted to database")

        # Second request to feedback -> returns cached result
        fb2 = client.get(f"/answers/{ans_id}/feedback")
        assert fb2.status_code == 200
        data2 = fb2.json()
        assert data2["cached"] is True
        assert data2["score"] == data1["score"]
        assert data2["feedback"] == data1["feedback"]
        print(f"Second feedback call: score={data2['score']}, cached={data2['cached']}")
        print("PASS: Subsequent feedback requests served from cache")

        # Test CASCADE delete on question
        del_res = client.delete("/questions/1")
        assert del_res.status_code == 200
        chk_conn = test_get_db()
        assert chk_conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 0
        assert chk_conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 0
        chk_conn.close()
        print("PASS: Question deletion cascades to delete both answers and evaluations")

    finally:
        try:
            Path(temp_db).unlink(missing_ok=True)
        except Exception:
            pass

    print("\nALL PHASE 2 TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_phase2()
