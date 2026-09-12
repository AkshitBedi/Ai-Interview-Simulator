import os
import sqlite3
from pathlib import Path


DATABASE_DEFAULT_NAME = Path(__file__).resolve().parent / "interview.db"
DATABASE_NAME = DATABASE_DEFAULT_NAME


def get_database_path() -> Path | str:
    env_path = os.environ.get("DATABASE_PATH")
    if env_path and env_path.strip():
        clean_path = env_path.strip()
        if clean_path == ":memory:":
            return clean_path
        target = Path(clean_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    # Preserve backward compatibility with test suites patching backend.database.DATABASE_NAME
    if str(DATABASE_NAME) != str(DATABASE_DEFAULT_NAME):
        if str(DATABASE_NAME) == ":memory:":
            return ":memory:"
        target = Path(DATABASE_NAME).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    DATABASE_DEFAULT_NAME.parent.mkdir(parents=True, exist_ok=True)
    return DATABASE_DEFAULT_NAME


def get_db():
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection




def create_tables():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            question TEXT NOT NULL,
            topic TEXT DEFAULT NULL,
            subtopic TEXT DEFAULT NULL,
            question_type TEXT DEFAULT NULL,
            skill_type TEXT DEFAULT NULL,
            quality_tier TEXT DEFAULT 'core',
            expected_concepts TEXT DEFAULT '[]',
            common_mistakes TEXT DEFAULT '[]',
            ideal_answer_points TEXT DEFAULT '[]',
            prerequisites TEXT DEFAULT '[]'
        )
    """)

    # Migrate existing questions table to include Phase 10 rich metadata columns
    question_cols = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(questions)").fetchall()
    }
    metadata_cols = [
        ("topic", "TEXT DEFAULT NULL"),
        ("subtopic", "TEXT DEFAULT NULL"),
        ("question_type", "TEXT DEFAULT NULL"),
        ("skill_type", "TEXT DEFAULT NULL"),
        ("quality_tier", "TEXT DEFAULT 'core'"),
        ("expected_concepts", "TEXT DEFAULT '[]'"),
        ("common_mistakes", "TEXT DEFAULT '[]'"),
        ("ideal_answer_points", "TEXT DEFAULT '[]'"),
        ("prerequisites", "TEXT DEFAULT '[]'"),
    ]
    for col_name, col_def in metadata_cols:
        if col_name not in question_cols:
            connection.execute(f"ALTER TABLE questions ADD COLUMN {col_name} {col_def}")

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_questions_category_diff ON questions(category, difficulty)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic)"
    )

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

    # Migrate answers.question_id to be nullable so follow-up answers with question_id=NULL are supported
    answers_cols_info = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(answers)").fetchall()
    }
    if "question_id" in answers_cols_info and answers_cols_info["question_id"]["notnull"] == 1:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("ALTER TABLE answers RENAME TO _answers_old_nn")
        connection.execute("""
            CREATE TABLE answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                answer TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL
            )
        """)
        connection.execute("""
            INSERT INTO answers (id, question_id, answer)
            SELECT id, question_id, answer FROM _answers_old_nn
        """)
        connection.execute("DROP TABLE _answers_old_nn")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers(question_id)")
        connection.execute("PRAGMA foreign_keys = ON")

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

    # Repair any stale foreign key reference if answers was renamed
    eval_fks = [
        dict(r) for r in connection.execute("PRAGMA foreign_key_list(evaluations)").fetchall()
    ]
    if eval_fks and any(fk["table"] != "answers" for fk in eval_fks):
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("ALTER TABLE evaluations RENAME TO _eval_stale_fk")
        connection.execute("""
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
        connection.execute("""
            INSERT INTO evaluations (id, answer_id, score, feedback, technical_accuracy, strengths, missing_points, created_at)
            SELECT id, answer_id, score, feedback, technical_accuracy, strengths, missing_points, created_at FROM _eval_stale_fk
        """)
        connection.execute("DROP TABLE _eval_stale_fk")
        connection.execute("PRAGMA foreign_keys = ON")

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_evaluations_answer_id ON evaluations(answer_id)"
    )

    # Phase 16: Users table
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP DEFAULT NULL
        )
    """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
    )

    # Phase 3: Interview sessions and conversational turns
    connection.execute("""
        CREATE TABLE IF NOT EXISTS interview_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            difficulty TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            current_turn INTEGER NOT NULL DEFAULT 1,
            max_turns INTEGER NOT NULL DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            target_role TEXT DEFAULT NULL,
            experience_level TEXT DEFAULT 'mid',
            selected_categories TEXT DEFAULT NULL,
            interviewer_style TEXT DEFAULT 'professional',
            candidate_profile TEXT DEFAULT NULL,
            job_context TEXT DEFAULT NULL,
            user_id INTEGER DEFAULT NULL,
            guest_id TEXT DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    # Migrate existing interview_sessions table to include Phase 11, 12 & 16 columns
    session_cols = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(interview_sessions)").fetchall()
    }
    phase11_12_16_cols = [
        ("target_role", "TEXT DEFAULT NULL"),
        ("experience_level", "TEXT DEFAULT 'mid'"),
        ("selected_categories", "TEXT DEFAULT NULL"),
        ("interviewer_style", "TEXT DEFAULT 'professional'"),
        ("candidate_profile", "TEXT DEFAULT NULL"),
        ("job_context", "TEXT DEFAULT NULL"),
        ("user_id", "INTEGER DEFAULT NULL"),
        ("guest_id", "TEXT DEFAULT NULL"),
    ]
    for col_name, col_def in phase11_12_16_cols:
        if col_name not in session_cols:
            connection.execute(f"ALTER TABLE interview_sessions ADD COLUMN {col_name} {col_def}")

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_status ON interview_sessions(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON interview_sessions(user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_guest_id ON interview_sessions(guest_id)"
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS session_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            turn_number INTEGER NOT NULL,
            question_id INTEGER,
            question_text TEXT NOT NULL,
            is_follow_up BOOLEAN NOT NULL DEFAULT 0,
            parent_turn_id INTEGER,
            answer_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            claim_id TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_turn_id) REFERENCES session_turns(id) ON DELETE SET NULL,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE SET NULL
        )
    """)

    # Phase 13: Migrate existing session_turns table to include claim_id column
    turn_cols = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(session_turns)").fetchall()
    }
    if "claim_id" not in turn_cols:
        connection.execute("ALTER TABLE session_turns ADD COLUMN claim_id TEXT DEFAULT NULL")

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_turns_session ON session_turns(session_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_turns_question ON session_turns(question_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_turns_answer ON session_turns(answer_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_turns_claim ON session_turns(claim_id)"
    )

    # Phase 4: Speech Analytics and Communication Intelligence
    connection.execute("""
        CREATE TABLE IF NOT EXISTS speech_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL UNIQUE,
            audio_duration_seconds REAL NOT NULL,
            speaking_duration_seconds REAL NOT NULL,
            pause_duration_seconds REAL NOT NULL,
            pause_count INTEGER NOT NULL,
            average_pause_duration REAL NOT NULL,
            long_pause_count INTEGER NOT NULL,
            speaking_rate_wpm REAL NOT NULL,
            articulation_rate_wpm REAL NOT NULL,
            filler_word_count INTEGER NOT NULL,
            filler_rate REAL NOT NULL,
            filler_breakdown TEXT,
            repeated_words_count INTEGER NOT NULL,
            phonation_ratio REAL NOT NULL,
            delivery_score INTEGER NOT NULL,
            delivery_feedback TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
        )
    """)

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_speech_analytics_answer_id ON speech_analytics(answer_id)"
    )

    # Phase 5: Nonverbal Telemetry and Computer Vision Analytics
    connection.execute("""
        CREATE TABLE IF NOT EXISTS nonverbal_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL UNIQUE,
            video_duration_seconds REAL NOT NULL,
            frames_analyzed INTEGER NOT NULL,
            face_detected_ratio REAL NOT NULL,
            centering_offset REAL NOT NULL,
            gaze_deviation_ratio REAL,
            avg_yaw_degrees REAL,
            avg_pitch_degrees REAL,
            avg_roll_degrees REAL,
            yaw_variance REAL,
            pitch_variance REAL,
            roll_variance REAL,
            head_motion_frequency_hz REAL,
            motion_energy REAL NOT NULL,
            camera_quality_flags TEXT,
            nonverbal_telemetry_score INTEGER NOT NULL,
            nonverbal_feedback TEXT NOT NULL,
            vision_backend TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
        )
    """)

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_nonverbal_analytics_answer_id ON nonverbal_analytics(answer_id)"
    )

    # Seed or enrich question bank with Phase 10 expanded catalog
    seed_count = connection.execute(
        "SELECT COUNT(*) FROM questions WHERE question != 'stringstri'"
    ).fetchone()[0]

    if seed_count < 100:
        try:
            from backend.question_bank import seed_question_bank
        except (ImportError, ValueError):
            from question_bank import seed_question_bank
        seed_question_bank(connection)

    connection.commit()
    connection.close()
