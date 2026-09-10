"""
tests/test_analytics.py

Comprehensive test suite for Phase 6: Interview Analytics & Progress Tracking.
Validates exact numerical calculations, database joins, edge cases, and API endpoints.
"""

import sys
import tempfile
import sqlite3
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
import backend.main as main
from backend.analytics import (
    get_analytics_overview,
    get_analytics_history,
    _resolve_effective_category,
    _compute_category_status,
    _calculate_dimension_change
)


def create_test_schema(conn: sqlite3.Connection):
    """Initializes the complete database schema in a test database."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            question TEXT NOT NULL
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
            completed_at TIMESTAMP
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE nonverbal_analytics (
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
    conn.commit()


class TestAnalyticsMathAndHelpers(unittest.TestCase):
    """Unit tests for standalone helper functions."""

    def test_resolve_effective_category(self):
        self.assertEqual(_resolve_effective_category("Python", "Databases", "System Design"), "Python")
        self.assertEqual(_resolve_effective_category(None, "Databases", "System Design"), "Databases")
        self.assertEqual(_resolve_effective_category("", "Databases", "System Design"), "Databases")
        self.assertEqual(_resolve_effective_category(None, None, "System Design"), "System Design")
        self.assertEqual(_resolve_effective_category(None, None, None), "General")

    def test_compute_category_status(self):
        self.assertEqual(_compute_category_status(8.5), "strong")
        self.assertEqual(_compute_category_status(7.0), "strong")
        self.assertEqual(_compute_category_status(6.9), "moderate")
        self.assertEqual(_compute_category_status(6.0), "moderate")
        self.assertEqual(_compute_category_status(5.9), "needs_focus")
        self.assertEqual(_compute_category_status(1.0), "needs_focus")

    def test_calculate_dimension_change(self):
        sessions = [{"session_id": 1, "technical_score": 6.0}]
        delta, first_id, last_id = _calculate_dimension_change(sessions, "technical_score")
        self.assertIsNone(delta)
        self.assertEqual(first_id, 1)
        self.assertEqual(last_id, 1)

        sessions = [
            {"session_id": 1, "technical_score": 6.0},
            {"session_id": 2, "technical_score": 9.0}
        ]
        delta, first_id, last_id = _calculate_dimension_change(sessions, "technical_score")
        self.assertEqual(delta, 50.0)
        self.assertEqual(first_id, 1)
        self.assertEqual(last_id, 2)

        sessions = [
            {"session_id": 1, "technical_score": 8.0},
            {"session_id": 2, "technical_score": 6.0}
        ]
        delta, first_id, last_id = _calculate_dimension_change(sessions, "technical_score")
        self.assertEqual(delta, -25.0)

        sessions = [
            {"session_id": 1, "technical_score": 0.0},
            {"session_id": 2, "technical_score": 8.0}
        ]
        delta, first_id, last_id = _calculate_dimension_change(sessions, "technical_score")
        self.assertIsNone(delta)

        sessions = [
            {"session_id": 1, "delivery_score": 6.0},
            {"session_id": 2, "delivery_score": None},
            {"session_id": 3, "delivery_score": 7.5}
        ]
        delta, first_id, last_id = _calculate_dimension_change(sessions, "delivery_score")
        self.assertEqual(delta, 25.0)
        self.assertEqual(first_id, 1)
        self.assertEqual(last_id, 3)


class TestAnalyticsEngine(unittest.TestCase):
    """Integration and edge-case tests against SQLite."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_empty_database(self):
        overview = get_analytics_overview(self.conn)
        self.assertEqual(overview["total_completed_interviews"], 0)
        self.assertEqual(overview["total_turns"], 0)
        self.assertEqual(overview["total_evaluated_answers"], 0)
        self.assertEqual(overview["total_bank_questions"], 0)
        self.assertEqual(overview["total_follow_ups"], 0)
        self.assertIsNone(overview["technical_average"])
        self.assertIsNone(overview["delivery_average"])
        self.assertIsNone(overview["nonverbal_average"])
        self.assertFalse(overview["modality_availability"]["has_audio"])
        self.assertFalse(overview["modality_availability"]["has_video"])
        self.assertIsNone(overview["change"]["technical_percent"])
        self.assertEqual(overview["categories"], [])
        self.assertEqual(overview["strongest_categories"], [])
        self.assertEqual(overview["categories_needing_focus"], [])
        self.assertEqual(overview["trends"]["sessions"], [])

        history = get_analytics_history(self.conn, limit=20, offset=0)
        self.assertEqual(history["total_completed"], 0)
        self.assertEqual(history["sessions"], [])

    def test_active_and_incomplete_sessions_excluded(self):
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Python', 'medium', 'Q1')")
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (1, 1, 'A1')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 2, 'Bad')")
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (2, 1, 'A2')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (2, 8, 'Great')")

        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (1, 'Python', 'medium', 'active', NULL)
        """)
        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (2, 'Python', 'medium', 'completed', '2026-09-10 10:00:00')
        """)

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id)
            VALUES (1, 1, 1, 'Q1', 0, 1)
        """)
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id)
            VALUES (2, 1, 1, 'Q1', 0, 2)
        """)
        self.conn.commit()

        overview = get_analytics_overview(self.conn)
        self.assertEqual(overview["total_completed_interviews"], 1)
        self.assertEqual(overview["total_turns"], 1)
        self.assertEqual(overview["total_evaluated_answers"], 1)
        self.assertEqual(overview["technical_average"], 8.0)

        history = get_analytics_history(self.conn)
        self.assertEqual(history["total_completed"], 1)
        self.assertEqual(history["sessions"][0]["session_id"], 2)

    def test_missing_modalities_are_null_not_zero(self):
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Python', 'medium', 'Q1')")
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (1, 1, 'A1')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 7, 'Good')")
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (2, 1, 'A2')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (2, 9, 'Excellent')")
        self.conn.execute("""
            INSERT INTO speech_analytics (answer_id, audio_duration_seconds, speaking_duration_seconds, pause_duration_seconds, pause_count, average_pause_duration, long_pause_count, speaking_rate_wpm, articulation_rate_wpm, filler_word_count, filler_rate, repeated_words_count, phonation_ratio, delivery_score, delivery_feedback)
            VALUES (2, 10.0, 8.0, 2.0, 2, 1.0, 0, 130.0, 140.0, 1, 0.02, 0, 0.8, 8, 'Clear')
        """)

        # Session 1: Text only
        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (1, 'Python', 'medium', 'completed', '2026-09-08 10:00:00')
        """)
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id) VALUES (1, 1, 1, 'Q1', 0, 1)")

        # Session 2: Audio only (no video)
        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (2, 'Python', 'medium', 'completed', '2026-09-09 10:00:00')
        """)
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id) VALUES (2, 1, 1, 'Q1', 0, 2)")
        self.conn.commit()

        overview = get_analytics_overview(self.conn)
        self.assertEqual(overview["total_completed_interviews"], 2)
        self.assertEqual(overview["technical_average"], 8.0) # (7 + 9) / 2
        self.assertEqual(overview["delivery_average"], 8.0) # only session 2
        self.assertIsNone(overview["nonverbal_average"]) # no video at all -> None
        self.assertTrue(overview["modality_availability"]["has_audio"])
        self.assertFalse(overview["modality_availability"]["has_video"])

        history = get_analytics_history(self.conn)
        s2 = history["sessions"][0]
        self.assertEqual(s2["session_id"], 2)
        self.assertEqual(s2["technical_score"], 9.0)
        self.assertEqual(s2["delivery_score"], 8.0)
        self.assertIsNone(s2["nonverbal_score"])
        self.assertTrue(s2["has_audio"])
        self.assertFalse(s2["has_video"])

        s1 = history["sessions"][1]
        self.assertEqual(s1["session_id"], 1)
        self.assertEqual(s1["technical_score"], 7.0)
        self.assertIsNone(s1["delivery_score"])
        self.assertIsNone(s1["nonverbal_score"])
        self.assertFalse(s1["has_audio"])
        self.assertFalse(s1["has_video"])

    def test_follow_up_category_attribution(self):
        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (1, 'Mixed', 'medium', 'completed', '2026-09-10 10:00:00')
        """)
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Databases', 'medium', 'What is normalization?')")
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (100, 1, 'Ans 1')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (100, 6, 'Partial')")
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (101, NULL, 'Ans 2')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (101, 8, 'Good')")

        self.conn.execute("""
            INSERT INTO session_turns (id, session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, answer_id)
            VALUES (10, 1, 1, 1, 'What is normalization?', 0, NULL, 100)
        """)
        self.conn.execute("""
            INSERT INTO session_turns (id, session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, answer_id)
            VALUES (11, 1, 2, NULL, 'Can you explain 3NF?', 1, 10, 101)
        """)
        self.conn.commit()

        overview = get_analytics_overview(self.conn)
        self.assertEqual(overview["total_turns"], 2)
        self.assertEqual(overview["total_evaluated_answers"], 2)
        self.assertEqual(overview["total_bank_questions"], 1)
        self.assertEqual(overview["total_follow_ups"], 1)

        self.assertEqual(len(overview["categories"]), 1)
        db_cat = overview["categories"][0]
        self.assertEqual(db_cat["category"], "Databases")
        self.assertEqual(db_cat["evaluated_answers_count"], 2)
        self.assertEqual(db_cat["average_score"], 7.0) # (6 + 8) / 2
        self.assertEqual(db_cat["best_score"], 8)
        self.assertEqual(db_cat["worst_score"], 6)
        self.assertEqual(db_cat["status"], "strong")

    def test_category_tie_breaking_and_ordering(self):
        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (1, 'General', 'medium', 'completed', '2026-09-10 10:00:00')
        """)
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Beta', 'medium', 'Q')")
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (2, 'Alpha', 'medium', 'Q')")
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (3, 'Delta', 'medium', 'Q')")
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (4, 'Gamma', 'medium', 'Q')")

        for i in range(1, 7):
            self.conn.execute(f"INSERT INTO answers (id, question_id, answer) VALUES ({i}, NULL, 'A')")

        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 8, 'F')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (2, 8, 'F')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (3, 8, 'F')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (4, 5, 'F')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (5, 5, 'F')")
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (6, 5, 'F')")

        # Beta: count 2, avg 8.0
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 1, 1, 'Q', 1)")
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 2, 1, 'Q', 2)")
        # Alpha: count 1, avg 8.0
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 3, 2, 'Q', 3)")
        # Delta: count 2, avg 5.0
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 4, 3, 'Q', 4)")
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 5, 3, 'Q', 5)")
        # Gamma: count 1, avg 5.0
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 6, 4, 'Q', 6)")
        self.conn.commit()

        overview = get_analytics_overview(self.conn)

        strongest = overview["strongest_categories"]
        self.assertEqual(len(strongest), 2)
        self.assertEqual(strongest[0]["category"], "Beta")
        self.assertEqual(strongest[0]["evaluated_answers_count"], 2)
        self.assertEqual(strongest[1]["category"], "Alpha")
        self.assertEqual(strongest[1]["evaluated_answers_count"], 1)

        weakest = overview["categories_needing_focus"]
        self.assertEqual(len(weakest), 2)
        self.assertEqual(weakest[0]["category"], "Delta")
        self.assertEqual(weakest[0]["evaluated_answers_count"], 2)
        self.assertEqual(weakest[1]["category"], "Gamma")
        self.assertEqual(weakest[1]["evaluated_answers_count"], 1)

    def test_session_without_evaluable_technical_answers(self):
        self.conn.execute("""
            INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
            VALUES (1, 'Python', 'medium', 'completed', '2026-09-10 10:00:00')
        """)
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 1, NULL, 'Pending Q', NULL)")
        self.conn.commit()

        history = get_analytics_history(self.conn)
        self.assertEqual(history["total_completed"], 1)
        s = history["sessions"][0]
        self.assertEqual(s["turns_count"], 1)
        self.assertEqual(s["evaluated_answers_count"], 0)
        self.assertIsNone(s["technical_score"])

        overview = get_analytics_overview(self.conn)
        self.assertEqual(overview["total_turns"], 1)
        self.assertEqual(overview["total_evaluated_answers"], 0)
        self.assertIsNone(overview["technical_average"])

    def test_pagination(self):
        for i in range(1, 6):
            self.conn.execute(f"""
                INSERT INTO interview_sessions (id, category, difficulty, status, completed_at)
                VALUES ({i}, 'Python', 'medium', 'completed', '2026-09-0{i} 10:00:00')
            """)
        self.conn.commit()

        p1 = get_analytics_history(self.conn, limit=2, offset=0)
        self.assertEqual(p1["total_completed"], 5)
        self.assertEqual(len(p1["sessions"]), 2)
        self.assertEqual(p1["sessions"][0]["session_id"], 5)
        self.assertEqual(p1["sessions"][1]["session_id"], 4)

        p2 = get_analytics_history(self.conn, limit=2, offset=2)
        self.assertEqual(p2["total_completed"], 5)
        self.assertEqual(len(p2["sessions"]), 2)
        self.assertEqual(p2["sessions"][0]["session_id"], 3)
        self.assertEqual(p2["sessions"][1]["session_id"], 2)

        p3 = get_analytics_history(self.conn, limit=2, offset=4)
        self.assertEqual(len(p3["sessions"]), 1)
        self.assertEqual(p3["sessions"][0]["session_id"], 1)

        p4 = get_analytics_history(self.conn, limit=2, offset=6)
        self.assertEqual(len(p4["sessions"]), 0)


class TestAnalyticsAPIEndpoints(unittest.TestCase):
    """End-to-end API tests via FastAPI TestClient."""

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name

        def test_get_db():
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            return c

        self.orig_get_db = main.get_db
        main.get_db = test_get_db

        conn = test_get_db()
        create_test_schema(conn)
        conn.close()

        self.client = TestClient(main.app)

    def tearDown(self):
        main.get_db = self.orig_get_db
        self.client.close()
        try:
            Path(self.db_path).unlink(missing_ok=True)
        except Exception:
            pass

    def test_overview_and_history_endpoints_e2e(self):
        conn = main.get_db()
        conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Python', 'medium', 'Q1')")
        conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (2, 'Databases', 'hard', 'Q2')")
        conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (1, 1, 'Ans 1')")
        conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 6, 'Ok')")
        conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (2, 2, 'Ans 2')")
        conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (2, 8, 'Great')")
        conn.execute("""
            INSERT INTO speech_analytics (answer_id, audio_duration_seconds, speaking_duration_seconds, pause_duration_seconds, pause_count, average_pause_duration, long_pause_count, speaking_rate_wpm, articulation_rate_wpm, filler_word_count, filler_rate, repeated_words_count, phonation_ratio, delivery_score, delivery_feedback)
            VALUES (2, 12.0, 10.0, 2.0, 1, 2.0, 0, 140.0, 145.0, 0, 0.0, 0, 0.83, 9, 'Flawless')
        """)

        conn.execute("INSERT INTO interview_sessions (id, category, difficulty, status, completed_at) VALUES (1, 'Python', 'medium', 'completed', '2026-09-08 12:00:00')")
        conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (1, 1, 1, 'Q1', 1)")

        conn.execute("INSERT INTO interview_sessions (id, category, difficulty, status, completed_at) VALUES (2, 'Databases', 'hard', 'completed', '2026-09-09 12:00:00')")
        conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (2, 1, 2, 'Q2', 2)")

        conn.commit()
        conn.close()

        res_ov = self.client.get("/analytics/overview")
        self.assertEqual(res_ov.status_code, 200)
        data_ov = res_ov.json()
        self.assertEqual(data_ov["total_completed_interviews"], 2)
        self.assertEqual(data_ov["total_turns"], 2)
        self.assertEqual(data_ov["total_evaluated_answers"], 2)
        self.assertEqual(data_ov["technical_average"], 7.0)
        self.assertEqual(data_ov["delivery_average"], 9.0)
        self.assertIsNone(data_ov["nonverbal_average"])
        self.assertTrue(data_ov["modality_availability"]["has_audio"])
        self.assertFalse(data_ov["modality_availability"]["has_video"])
        self.assertEqual(data_ov["change"]["technical_percent"], 33.3)
        self.assertEqual(data_ov["change"]["technical_first_session_id"], 1)
        self.assertEqual(data_ov["change"]["technical_latest_session_id"], 2)
        self.assertEqual(len(data_ov["categories"]), 2)
        self.assertEqual(data_ov["categories"][0]["category"], "Databases")
        self.assertEqual(data_ov["strongest_categories"][0]["category"], "Databases")
        self.assertEqual(data_ov["categories_needing_focus"][0]["category"], "Python")

        res_hist = self.client.get("/analytics/history?limit=10&offset=0")
        self.assertEqual(res_hist.status_code, 200)
        data_hist = res_hist.json()
        self.assertEqual(data_hist["total_completed"], 2)
        self.assertEqual(len(data_hist["sessions"]), 2)
        self.assertEqual(data_hist["sessions"][0]["session_id"], 2)
        self.assertEqual(data_hist["sessions"][1]["session_id"], 1)


if __name__ == "__main__":
    unittest.main()
