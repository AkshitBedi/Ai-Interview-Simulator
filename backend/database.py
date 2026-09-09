import sqlite3
from pathlib import Path

DATABASE_NAME = Path(__file__).resolve().parent / "interview.db"


def get_db():
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            question TEXT NOT NULL
        )
    """)

    answers_exists = connection.execute("""
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'answers'
    """).fetchone()

    if answers_exists is None:
        connection.execute("""
            CREATE TABLE answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                answer TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            )
        """)
    else:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(answers)").fetchall()
        }

        # Migrate the earlier text-based design before rebuilding the table.
        if "question_id" not in columns:
            connection.execute(
                "ALTER TABLE answers ADD COLUMN question_id INTEGER REFERENCES questions(id)"
            )
            connection.execute("""
                UPDATE answers
                SET question_id = (
                    SELECT questions.id
                    FROM questions
                    WHERE questions.question = answers.question
                )
                WHERE question_id IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM questions
                    WHERE questions.question = answers.question
                )
            """)
            columns.add("question_id")

        # The old question text is no longer part of active answer storage.
        # Keep its rows as an archive so no historical data is discarded.
        if "question" in columns:
            connection.execute("ALTER TABLE answers RENAME TO answers_legacy")
            connection.execute("""
                CREATE TABLE answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    answer TEXT NOT NULL,
                    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
                )
            """)
            connection.execute("""
                INSERT INTO answers (id, question_id, answer)
                SELECT id, question_id, answer
                FROM answers_legacy
                WHERE question_id IS NOT NULL
            """)

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers(question_id)"
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
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

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_evaluations_answer_id ON evaluations(answer_id)"
    )

    connection.commit()
    connection.close()
