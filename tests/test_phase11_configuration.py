"""
tests/test_phase11_configuration.py

Comprehensive test suite for Phase 11: Interview Configuration & Personalization.
Validates:
A. Phase 7 Medium-Baseline Invariant Preservation (unseen category starts at medium regardless of role/exp/diff)
B. Category Normalization & Validation (all 8 canonical rules + edge cases)
C. Multi-Category Strategy & Intelligent Question Selection
D. Follow-Up Category Safety (parent turn category inheritance)
E. Desynchronization Defense (invalid category / missing selected_categories)
F. Interviewer Style Precedence (session style vs explicit per-turn override)
G. Target Role & Experience Level Personalization (persistence, normalization, validation, context)
H. Response Validation (start_session, get_session_details, get_session_summary)
I. Legacy Database Backward Compatibility (NULL columns receive safe defaults)
"""

import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.database import get_db, create_tables
from backend.main import app
import backend.interview_engine as interview_engine
import backend.strategy_engine as strategy_engine
import backend.interviewer as interviewer
from backend.evaluator import EvaluationResult
from backend.question_bank import CANONICAL_CATEGORIES


def create_test_schema(conn: sqlite3.Connection):
    """Initializes the complete database schema in a test database."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE questions (
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
    conn.execute("""
        CREATE TABLE answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            answer TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
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
    conn.execute("""
        CREATE TABLE interview_sessions (
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
            interviewer_style TEXT DEFAULT 'professional'
        )
    """)
    conn.execute("""
        CREATE TABLE session_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            turn_number INTEGER NOT NULL,
            question_id INTEGER,
            question_text TEXT NOT NULL,
            is_follow_up BOOLEAN NOT NULL DEFAULT 0,
            parent_turn_id INTEGER,
            answer_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_turn_id) REFERENCES session_turns(id) ON DELETE SET NULL,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE TABLE speech_analytics (
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
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE nonverbal_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL UNIQUE,
            video_duration_seconds REAL,
            frames_analyzed INTEGER,
            face_detected_ratio REAL,
            centering_offset REAL,
            gaze_deviation_ratio REAL,
            avg_yaw_degrees REAL,
            avg_pitch_degrees REAL,
            avg_roll_degrees REAL,
            yaw_variance REAL,
            pitch_variance REAL,
            roll_variance REAL,
            head_motion_frequency_hz REAL,
            motion_energy REAL,
            camera_quality_flags TEXT,
            nonverbal_telemetry_score REAL,
            nonverbal_feedback TEXT,
            vision_backend TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
        )
    """)


class TestPhase11MediumBaseline(unittest.TestCase):
    """
    Section 1: Invariant Preservation.
    A genuinely unseen category MUST always start at 'medium', regardless of:
    - session difficulty (hard/easy)
    - experience_level (junior/mid/senior)
    - target_role
    - interviewer_style
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

        # Seed questions across categories and difficulties
        for cat in CANONICAL_CATEGORIES:
            for diff in ("easy", "medium", "hard"):
                self.conn.execute(
                    "INSERT INTO questions (category, difficulty, question) VALUES (?, ?, ?)",
                    (cat, diff, f"Question for {cat} {diff}")
                )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_unseen_category_starts_medium_with_hard_and_junior(self):
        session = interview_engine.start_session(
            self.conn,
            category="Python",
            difficulty="hard",
            target_role="Junior Python Developer",
            experience_level="junior",
            interviewer_style="strict"
        )
        self.assertEqual(session["question"]["difficulty"], "medium")

    def test_unseen_category_starts_medium_with_hard_and_mid(self):
        session = interview_engine.start_session(
            self.conn,
            category="Databases",
            difficulty="hard",
            target_role="Database Administrator",
            experience_level="mid",
            interviewer_style="conversational"
        )
        self.assertEqual(session["question"]["difficulty"], "medium")

    def test_unseen_category_starts_medium_with_hard_and_senior(self):
        session = interview_engine.start_session(
            self.conn,
            category="System Design",
            difficulty="hard",
            target_role="Staff Infrastructure Architect",
            experience_level="senior",
            interviewer_style="professional"
        )
        self.assertEqual(session["question"]["difficulty"], "medium")

    def test_unseen_category_in_multicategory_session_always_starts_medium(self):
        session = interview_engine.start_session(
            self.conn,
            categories=["Python", "Databases"],
            difficulty="hard",
            experience_level="senior"
        )
        # First question selected must be medium
        self.assertEqual(session["question"]["difficulty"], "medium")


class TestCategoryNormalizationAndValidation(unittest.TestCase):
    """
    Section 3: Category Normalization & Validation Contract.
    Enforces the 8 normalization rules and error rejection.
    """

    def test_rule1_omitted_categories_and_legacy_none(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category=None, categories=None
        )
        self.assertEqual(stored_cat, "All")
        self.assertEqual(selected, list(CANONICAL_CATEGORIES))

    def test_rule1b_legacy_category_python(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category="Python", categories=None
        )
        self.assertEqual(stored_cat, "Python")
        self.assertEqual(selected, ["Python"])

    def test_rule1c_legacy_category_all(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category="All", categories=None
        )
        self.assertEqual(stored_cat, "All")
        self.assertEqual(selected, list(CANONICAL_CATEGORIES))

    def test_rule2_single_category_list(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category=None, categories=["Python"]
        )
        self.assertEqual(stored_cat, "Python")
        self.assertEqual(selected, ["Python"])

    def test_rule3_multi_category_list(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category=None, categories=["Python", "Databases"]
        )
        self.assertIsNone(stored_cat)
        self.assertEqual(selected, ["Python", "Databases"])

    def test_rule4_categories_all(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category=None, categories=["All"]
        )
        self.assertEqual(stored_cat, "All")
        self.assertEqual(selected, list(CANONICAL_CATEGORIES))

    def test_rule5_categories_deduplication(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category=None, categories=["Python", "Python"]
        )
        self.assertEqual(stored_cat, "Python")
        self.assertEqual(selected, ["Python"])

    def test_redundant_single_match(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            category="Python", categories=["Python"]
        )
        self.assertEqual(stored_cat, "Python")
        self.assertEqual(selected, ["Python"])

    def test_rule6_reject_conflicting_inputs(self):
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(
                category="Python", categories=["Databases"]
            )

    def test_rule6b_reject_combining_all_with_specific(self):
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(
                category=None, categories=["All", "Python"]
            )

    def test_rule7_reject_invalid_category_list(self):
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(
                category=None, categories=["InvalidCategory"]
            )

    def test_rule7b_reject_invalid_category_scalar(self):
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(
                category="InvalidCategory", categories=None
            )

    def test_rule8_reject_empty_categories_list(self):
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(
                category=None, categories=[]
            )

    def test_reject_multi_category_and_custom_as_scalar_category(self):
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(category="Multi-Category")
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(category="Custom")
        with self.assertRaises(ValueError):
            interview_engine.normalize_session_configuration(category="Python,Databases")

    def test_canonical_category_ordering_preserved(self):
        stored_cat, selected, _, _, _ = interview_engine.normalize_session_configuration(
            categories=["Databases", "Python"]
        )
        self.assertIsNone(stored_cat)
        self.assertEqual(selected, ["Python", "Databases"])


class TestMultiCategoryStrategy(unittest.TestCase):
    """
    Section 4: Multi-Category Strategy & Question Selection.
    Verifies available_categories, coverage_target, and question boundary restriction.
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

        # Seed 5 questions per category
        for cat in CANONICAL_CATEGORIES:
            for i in range(1, 6):
                self.conn.execute(
                    "INSERT INTO questions (category, difficulty, question) VALUES (?, ?, ?)",
                    (cat, "medium", f"{cat} Question #{i}")
                )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_multi_category_available_and_coverage_target(self):
        # 2 categories selected, max_turns=5
        # coverage target = min(2, max(3, ceil(5 * 0.5))) = min(2, 3) = 2
        session = interview_engine.start_session(
            self.conn,
            categories=["Python", "Databases"],
            max_turns=5
        )
        session_id = session["session_id"]
        state = strategy_engine.build_interview_state(self.conn, session_id)

        self.assertEqual(state["available_categories"], ["Python", "Databases"])
        self.assertEqual(state["coverage_target"], 2)

    def test_multi_category_restricts_questions_strictly_to_selected(self):
        session = interview_engine.start_session(
            self.conn,
            categories=["Python", "Databases"],
            max_turns=4
        )
        session_id = session["session_id"]
        first_q = session["question"]
        self.assertIn(first_q["category"], ["Python", "Databases"])

        # Advance turns and confirm every bank question is strictly Python or Databases
        for turn_idx in range(1, 4):
            eval_mock = EvaluationResult(
                score=8,
                feedback="Good answer.",
                technical_accuracy="Accurate",
                strengths=[],
                missing_points=[]
            )
            res = interview_engine.record_answer_and_advance(
                self.conn,
                session_id=session_id,
                answer_text="Solid technical answer demonstrating core principles.",
                evaluation=eval_mock
            )
            if res["decision"] == "completed":
                break
            next_q = res["next_question"]
            if not next_q.get("is_follow_up"):
                self.assertIn(next_q["category"], ["Python", "Databases"])
                self.assertNotIn(next_q["category"], ["System Design", "Behavioral"])

    def test_single_category_coverage_target_equals_one(self):
        session = interview_engine.start_session(
            self.conn,
            categories=["Python"],
            max_turns=5
        )
        session_id = session["session_id"]
        state = strategy_engine.build_interview_state(self.conn, session_id)
        self.assertEqual(state["available_categories"], ["Python"])
        self.assertEqual(state["coverage_target"], 1)


class TestFollowUpCategorySafety(unittest.TestCase):
    """
    Section 5: Follow-Up Category Safety.
    Follow-up turns MUST inherit the canonical category of the question being probed,
    never falling back to NULL, 'Custom', or comma-separated strings.
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

        self.conn.execute(
            "INSERT INTO questions (category, difficulty, question) VALUES ('Python', 'medium', 'Explain GIL.')"
        )
        self.conn.execute(
            "INSERT INTO questions (category, difficulty, question) VALUES ('Databases', 'medium', 'Explain ACID.')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_followup_inherits_parent_category_in_multicategory_session(self):
        # Session with category = NULL, selected_categories = ["Python", "Databases"]
        session = interview_engine.start_session(
            self.conn,
            categories=["Python", "Databases"],
            max_turns=3
        )
        session_id = session["session_id"]

        # Turn 1 belongs to one of the selected categories
        turn1 = session["question"]
        parent_cat = turn1["category"]
        self.assertIn(parent_cat, ["Python", "Databases"])

        # Answer triggering follow-up (score=5, missing points)
        eval_mock = EvaluationResult(
            score=5,
            feedback="Incomplete answer.",
            technical_accuracy="Partial",
            strengths=[],
            missing_points=["threading module behavior"]
        )

        with patch("backend.interview_engine.generate_follow_up_question", return_value="Can you elaborate further?") as mock_gen:
            res = interview_engine.record_answer_and_advance(
                self.conn,
                session_id=session_id,
                answer_text="GIL prevents multiple native threads.",
                evaluation=eval_mock
            )

            self.assertEqual(res["decision"], "follow_up")
            # Verify category passed to follow_up generator is strictly the parent's canonical category
            mock_gen.assert_called_once()
            _, kwargs = mock_gen.call_args
            self.assertEqual(kwargs["category"], parent_cat)

        # Verify strategy state attributes the follow-up to the parent category
        state = strategy_engine.build_interview_state(self.conn, session_id)
        self.assertEqual(state["categories"][parent_cat]["bank_questions_asked"], 1)


class TestDesynchronizationDefense(unittest.TestCase):
    """
    Section 6: Category / selected_categories Desynchronization Defense.
    Invalid configurations (e.g. category='Custom', selected_categories=NULL)
    must fail fast rather than silently creating a broken session.
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_desynchronization_custom_category_raises_value_error(self):
        # Manually insert a malformed session row
        cursor = self.conn.execute(
            """
            INSERT INTO interview_sessions (category, difficulty, status, current_turn, max_turns, selected_categories)
            VALUES ('Custom', 'medium', 'active', 1, 5, NULL)
            """
        )
        session_id = cursor.lastrowid
        self.conn.commit()

        # build_interview_state must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            strategy_engine.build_interview_state(self.conn, session_id)
        self.assertIn("Desynchronization error", str(ctx.exception))

    def test_desynchronization_multi_category_raises_value_error(self):
        # Manually insert a malformed session row
        cursor = self.conn.execute(
            """
            INSERT INTO interview_sessions (category, difficulty, status, current_turn, max_turns, selected_categories)
            VALUES ('Multi-Category', 'medium', 'active', 1, 5, NULL)
            """
        )
        session_id = cursor.lastrowid
        self.conn.commit()

        # build_interview_state must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            strategy_engine.build_interview_state(self.conn, session_id)
        self.assertIn("Desynchronization error", str(ctx.exception))


class TestInterviewerStylePrecedence(unittest.TestCase):
    """
    Section 9: Interviewer Style Precedence.
    explicit per-turn override > session interviewer_style > 'professional'
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_strict_session_no_per_turn_override_uses_strict(self):
        # 1. Create session with interviewer_style="strict"
        resp = self.client.post("/sessions", json={
            "categories": ["Python"],
            "interviewer_style": "strict",
            "max_turns": 3
        })
        self.assertEqual(resp.status_code, 201)
        session_id = resp.json()["session_id"]

        # 2. Submit turn with interviewer_style omitted (the default client payload)
        with patch.object(interviewer, "generate_interviewer_response") as mock_gen:
            mock_gen.return_value = {
                "interviewer_response": "Focus directly on the mechanism.",
                "response_type": "probe",
                "interviewer_style": "strict"
            }
            ans_resp = self.client.post(f"/sessions/{session_id}/answer", json={
                "answer": "A decorator is a callable that takes another function as an argument and returns a replacement."
            })
            self.assertEqual(ans_resp.status_code, 200)
            data = ans_resp.json()
            self.assertEqual(data["interviewer_style"], "strict")

    def test_strict_session_with_explicit_conversational_override(self):
        # 1. Create session with interviewer_style="strict"
        resp = self.client.post("/sessions", json={
            "categories": ["Python"],
            "interviewer_style": "strict",
            "max_turns": 3
        })
        self.assertEqual(resp.status_code, 201)
        session_id = resp.json()["session_id"]

        # 2. Submit turn with explicit interviewer_style="conversational"
        with patch.object(interviewer, "generate_interviewer_response") as mock_gen:
            mock_gen.return_value = {
                "interviewer_response": "Great start, tell me more!",
                "response_type": "acknowledgement",
                "interviewer_style": "conversational"
            }
            ans_resp = self.client.post(f"/sessions/{session_id}/answer", json={
                "answer": "A decorator wraps another function to extend its behavior without permanently modifying it.",
                "interviewer_style": "conversational"
            })
            self.assertEqual(ans_resp.status_code, 200)
            data = ans_resp.json()
            self.assertEqual(data["interviewer_style"], "conversational")

    def test_invalid_interviewer_style_rejected(self):
        resp = self.client.post("/sessions", json={
            "interviewer_style": "invalid_style"
        })
        self.assertEqual(resp.status_code, 422)


class TestTargetRoleAndExperienceLevel(unittest.TestCase):
    """
    Sections 7 & 8: Target Role & Experience Level Personalization.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_target_role_and_experience_persisted_and_returned(self):
        resp = self.client.post("/sessions", json={
            "target_role": "Backend Engineer, Python",
            "experience_level": "senior",
            "max_turns": 3
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["target_role"], "Backend Engineer, Python")
        self.assertEqual(data["experience_level"], "senior")
        session_id = data["session_id"]

        # Check get_session_details
        det_resp = self.client.get(f"/sessions/{session_id}")
        self.assertEqual(det_resp.status_code, 200)
        det_data = det_resp.json()
        self.assertEqual(det_data["target_role"], "Backend Engineer, Python")
        self.assertEqual(det_data["experience_level"], "senior")

        # Check get_session_summary
        sum_resp = self.client.get(f"/sessions/{session_id}/summary")
        self.assertEqual(sum_resp.status_code, 200)
        sum_data = sum_resp.json()
        self.assertEqual(sum_data["target_role"], "Backend Engineer, Python")
        self.assertEqual(sum_data["experience_level"], "senior")

    def test_whitespace_target_role_normalizes_to_null(self):
        resp = self.client.post("/sessions", json={
            "target_role": "    ",
            "max_turns": 3
        })
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()["target_role"])

    def test_target_role_over_100_chars_rejected(self):
        resp = self.client.post("/sessions", json={
            "target_role": "A" * 101
        })
        self.assertEqual(resp.status_code, 400)

    def test_invalid_experience_level_rejected(self):
        resp = self.client.post("/sessions", json={
            "experience_level": "lead"
        })
        self.assertEqual(resp.status_code, 422)


class TestResponseValidationAndLegacyCompatibility(unittest.TestCase):
    """
    Sections 13, 14, 15: DB Migration & Response Validation.
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

        # Seed question
        self.conn.execute(
            "INSERT INTO questions (category, difficulty, question) VALUES ('Python', 'medium', 'What is GIL?')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_legacy_session_row_backward_compatibility(self):
        # Insert a Phase 10 style row where new columns are NULL
        cursor = self.conn.execute(
            """
            INSERT INTO interview_sessions (category, difficulty, status, current_turn, max_turns, target_role, experience_level, selected_categories, interviewer_style)
            VALUES ('Python', 'medium', 'active', 1, 5, NULL, NULL, NULL, NULL)
            """
        )
        session_id = cursor.lastrowid
        self.conn.commit()

        # details must return safe defaults
        details = interview_engine.get_session_details(self.conn, session_id)
        self.assertIsNone(details["target_role"])
        self.assertEqual(details["experience_level"], "mid")
        self.assertIsNone(details["selected_categories"])
        self.assertEqual(details["interviewer_style"], "professional")

        # summary must return safe defaults
        summary = interview_engine.get_session_summary(self.conn, session_id)
        self.assertIsNone(summary["target_role"])
        self.assertEqual(summary["experience_level"], "mid")
        self.assertIsNone(summary["selected_categories"])
        self.assertEqual(summary["interviewer_style"], "professional")

    def test_all_response_endpoints_contain_configuration_fields(self):
        session = interview_engine.start_session(
            self.conn,
            category="Python",
            difficulty="medium",
            max_turns=3,
            target_role="Full Stack Engineer",
            experience_level="mid",
            interviewer_style="conversational"
        )
        session_id = session["session_id"]

        for resp in [session, interview_engine.get_session_details(self.conn, session_id), interview_engine.get_session_summary(self.conn, session_id)]:
            self.assertIn("category", resp)
            self.assertIn("difficulty", resp)
            self.assertIn("target_role", resp)
            self.assertIn("experience_level", resp)
            self.assertIn("selected_categories", resp)
            self.assertIn("interviewer_style", resp)


class TestSessionRepresentations(unittest.TestCase):
    """
    Verifies exact session representations for:
    A. Python: category = 'Python', selected_categories = ['Python']
    B. All: category = 'All', selected_categories = all four canonical categories
    C. Python + Databases: category = NULL, selected_categories = ['Python', 'Databases']
    D. Legacy Python: category = 'Python', selected_categories = NULL
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

        for cat in CANONICAL_CATEGORIES:
            self.conn.execute(
                "INSERT INTO questions (category, difficulty, question) VALUES (?, 'medium', ?)",
                (cat, f"{cat} sample question")
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_case_a_python_session_representation(self):
        session = interview_engine.start_session(self.conn, category="Python")
        session_id = session["session_id"]

        row = self.conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertEqual(row["category"], "Python")
        self.assertEqual(json.loads(row["selected_categories"]), ["Python"])

        details = interview_engine.get_session_details(self.conn, session_id)
        self.assertEqual(details["category"], "Python")
        self.assertEqual(details["selected_categories"], ["Python"])

        summary = interview_engine.get_session_summary(self.conn, session_id)
        self.assertEqual(summary["category"], "Python")
        self.assertEqual(summary["selected_categories"], ["Python"])

    def test_case_b_all_session_representation(self):
        session = interview_engine.start_session(self.conn, category="All")
        session_id = session["session_id"]

        row = self.conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertEqual(row["category"], "All")
        self.assertEqual(json.loads(row["selected_categories"]), list(CANONICAL_CATEGORIES))

        details = interview_engine.get_session_details(self.conn, session_id)
        self.assertEqual(details["category"], "All")
        self.assertEqual(details["selected_categories"], list(CANONICAL_CATEGORIES))

        summary = interview_engine.get_session_summary(self.conn, session_id)
        self.assertEqual(summary["category"], "All")
        self.assertEqual(summary["selected_categories"], list(CANONICAL_CATEGORIES))

    def test_case_c_python_and_databases_session_representation(self):
        session = interview_engine.start_session(self.conn, categories=["Databases", "Python"])
        session_id = session["session_id"]

        row = self.conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        # category must be NULL in database
        self.assertIsNone(row["category"])
        # selected_categories must be canonical order
        self.assertEqual(json.loads(row["selected_categories"]), ["Python", "Databases"])

        details = interview_engine.get_session_details(self.conn, session_id)
        self.assertIsNone(details["category"])
        self.assertEqual(details["selected_categories"], ["Python", "Databases"])

        summary = interview_engine.get_session_summary(self.conn, session_id)
        self.assertIsNone(summary["category"])
        self.assertEqual(summary["selected_categories"], ["Python", "Databases"])

    def test_case_d_legacy_python_session_representation(self):
        # Directly insert legacy row where selected_categories is NULL
        cursor = self.conn.execute(
            """
            INSERT INTO interview_sessions (category, difficulty, status, current_turn, max_turns, selected_categories)
            VALUES ('Python', 'medium', 'active', 1, 5, NULL)
            """
        )
        session_id = cursor.lastrowid
        self.conn.commit()

        row = self.conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertEqual(row["category"], "Python")
        self.assertIsNone(row["selected_categories"])

        state = strategy_engine.build_interview_state(self.conn, session_id)
        self.assertEqual(state["available_categories"], ["Python"])
        self.assertIsNone(state["selected_categories"])

        details = interview_engine.get_session_details(self.conn, session_id)
        self.assertEqual(details["category"], "Python")
        self.assertIsNone(details["selected_categories"])

        summary = interview_engine.get_session_summary(self.conn, session_id)
        self.assertEqual(summary["category"], "Python")
        self.assertIsNone(summary["selected_categories"])

    def test_no_forbidden_category_values_persisted(self):
        # Verify no newly-created session ever has category='Custom', 'Multi-Category', or comma-delimited
        for kwargs in [
            {"category": "Python"},
            {"category": "All"},
            {"categories": ["Python", "Databases"]},
            {"categories": ["System Design", "Behavioral", "Databases"]},
        ]:
            session = interview_engine.start_session(self.conn, **kwargs)
            row = self.conn.execute("SELECT category FROM interview_sessions WHERE id = ?", (session["session_id"],)).fetchone()
            cat = row["category"]
            self.assertNotIn(cat, ["Custom", "Multi-Category"])
            if cat is not None:
                self.assertNotIn(",", cat)


class TestInterviewLengthAndStyleSemantics(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_max_turns_allowed_boundaries(self):
        # 1 and 20 are accepted
        r1 = self.client.post("/sessions", json={"max_turns": 1})
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r1.json()["max_turns"], 1)

        r20 = self.client.post("/sessions", json={"max_turns": 20})
        self.assertEqual(r20.status_code, 201)
        self.assertEqual(r20.json()["max_turns"], 20)

        # 0 and 21 are rejected
        r0 = self.client.post("/sessions", json={"max_turns": 0})
        self.assertEqual(r0.status_code, 422)

        r21 = self.client.post("/sessions", json={"max_turns": 21})
        self.assertEqual(r21.status_code, 422)

    def test_interviewer_style_canonical_vocabulary_strictly_enforced(self):
        # Accepted styles
        for s in ("professional", "conversational", "strict"):
            r = self.client.post("/sessions", json={"interviewer_style": s})
            self.assertEqual(r.status_code, 201)
            self.assertEqual(r.json()["interviewer_style"], s)

        # Forbidden styles (supportive, challenging, etc.)
        for invalid in ("supportive", "challenging", "casual", "rude"):
            r = self.client.post("/sessions", json={"interviewer_style": invalid})
            self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
