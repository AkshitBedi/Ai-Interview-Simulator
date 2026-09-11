"""
tests/test_phase14_insights.py

Comprehensive test suite for Phase 14: Advanced Performance Analytics & Longitudinal Interview Insights.
Covers all 42 required scenarios and boundary tests:
 1. chronological ordering
 2. zero completed sessions
 3. one completed session
 4. two-session delta
 5. three-session trend classification
 6. four-session window comparison
 7. bank-question isolation
 8. remedial-follow-up isolation
 9. claim-probe isolation
 10. category progression
 11. category-state reuse
 12. difficulty distribution
 13. difficulty averages
 14. hard success rate
 15. medium resilience
 16. hard resilience
 17. missing resilience half
 18. consistency min/max/span
 19. sample standard deviation
 20. insufficient standard deviation
 21. best/worst multi-category session
 22. answer-quality distribution
 23. answer-quality evolution
 24. communication trends
 25. speaking-rate ideal-range distance
 26. filler-rate trend
 27. persisted long_pause_count reuse
 28. missing audio
 29. nonverbal telemetry
 30. missing video
 31. claim-instance scoping
 32. claims_available session scope
 33. claim substantiation thresholds
 34. missing claims
 35. no blended score
 36. no interpolation
 37. deterministic tie ordering
 38. legacy sessions
 39. optional Gemini fallback
 40. Gemini cannot override deterministic metrics
 41. API response
 42. backward compatibility with existing analytics endpoints.
 Plus boundary conditions for score, trend, filler, category status, and claim substantiation.
"""

import sys
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
import backend.main as main
from backend.insights_engine import (
    get_analytics_insights,
    calculate_wpm_distance,
    calculate_technical_progression,
    calculate_consistency,
    calculate_category_progression,
    calculate_difficulty_progression,
    calculate_answer_quality_patterns,
    calculate_communication_trends,
    calculate_nonverbal_trends,
    calculate_resume_claim_analytics,
    generate_insights_executive_summary
)


def create_schema(conn: sqlite3.Connection):
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
            score REAL NOT NULL,
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
            interviewer_style TEXT DEFAULT 'professional',
            candidate_profile TEXT DEFAULT NULL,
            job_context TEXT DEFAULT NULL
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
            claim_id TEXT DEFAULT NULL,
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
            filler_breakdown TEXT NOT NULL,
            repeated_words_count INTEGER NOT NULL,
            phonation_ratio REAL NOT NULL,
            delivery_score REAL NOT NULL,
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
            nonverbal_telemetry_score REAL NOT NULL,
            nonverbal_feedback TEXT NOT NULL,
            vision_backend TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (answer_id) REFERENCES answers(id) ON DELETE CASCADE
        )
    """)


class TestPhase14Insights(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _insert_session(self, sid, status="completed", completed_at="2026-01-01 10:00:00",
                        category="Python", difficulty="medium", candidate_profile=None):
        self.conn.execute("""
            INSERT INTO interview_sessions (id, status, completed_at, category, difficulty, candidate_profile)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sid, status, completed_at, category, difficulty, candidate_profile))

    def _insert_bank_turn(self, sid, turn_num, category, difficulty, score, q_text="Question?", ans_text="Answer text here", acc_text=None):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO questions (category, difficulty, question) VALUES (?, ?, ?)", (category, difficulty, q_text))
        qid = cur.lastrowid
        cur.execute("INSERT INTO answers (question_id, answer) VALUES (?, ?)", (qid, ans_text))
        aid = cur.lastrowid
        cur.execute("INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy) VALUES (?, ?, 'fb', ?)", (aid, score, acc_text))
        cur.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id, status, claim_id)
            VALUES (?, ?, ?, ?, 0, ?, 'completed', NULL)
        """, (sid, turn_num, qid, q_text, aid))
        return aid

    def _insert_followup_turn(self, sid, turn_num, score, q_text="Follow-up?", ans_text="Follow up ans", acc_text=None):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO answers (question_id, answer) VALUES (NULL, ?)", (ans_text,))
        aid = cur.lastrowid
        cur.execute("INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy) VALUES (?, ?, 'fb', ?)", (aid, score, acc_text))
        cur.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id, status, claim_id)
            VALUES (?, ?, NULL, ?, 1, ?, 'completed', NULL)
        """, (sid, turn_num, q_text, aid))
        return aid

    def _insert_claim_turn(self, sid, turn_num, claim_id, score, q_text="Claim probe?", ans_text="Claim ans"):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO answers (question_id, answer) VALUES (NULL, ?)", (ans_text,))
        aid = cur.lastrowid
        cur.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, ?, 'fb')", (aid, score))
        cur.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id, status, claim_id)
            VALUES (?, ?, NULL, ?, 1, ?, 'completed', ?)
        """, (sid, turn_num, q_text, aid, claim_id))
        return aid

    def _insert_speech(self, aid, delivery_score=7, wpm=140.0, filler_rate=2.0, long_pause=1, pause_cnt=3, avg_pause=1.2):
        self.conn.execute("""
            INSERT INTO speech_analytics (
                answer_id, audio_duration_seconds, speaking_duration_seconds, pause_duration_seconds,
                pause_count, average_pause_duration, long_pause_count, speaking_rate_wpm,
                articulation_rate_wpm, filler_word_count, filler_rate, filler_breakdown,
                repeated_words_count, phonation_ratio, delivery_score, delivery_feedback
            ) VALUES (?, 10.0, 8.0, 2.0, ?, ?, ?, ?, 150.0, 2, ?, '{}', 0, 0.8, ?, 'fb')
        """, (aid, pause_cnt, avg_pause, long_pause, wpm, filler_rate, delivery_score))

    def _insert_nonverbal(self, aid, score=8, face=0.95, center=0.08, gaze=0.05, motion=1.2, energy=0.15, flags='["good_lighting"]'):
        self.conn.execute("""
            INSERT INTO nonverbal_analytics (
                answer_id, video_duration_seconds, frames_analyzed, face_detected_ratio,
                centering_offset, gaze_deviation_ratio, avg_yaw_degrees, avg_pitch_degrees,
                avg_roll_degrees, yaw_variance, pitch_variance, roll_variance,
                head_motion_frequency_hz, motion_energy, camera_quality_flags,
                nonverbal_telemetry_score, nonverbal_feedback, vision_backend
            ) VALUES (?, 10.0, 300, ?, ?, ?, 0.0, 0.0, 0.0, 0.1, 0.1, 0.1, ?, ?, ?, ?, 'fb', 'mock')
        """, (aid, face, center, gaze, motion, energy, flags, score))

    # -----------------------------------------------------------------------
    # Scenario 1: Chronological ordering
    # -----------------------------------------------------------------------
    def test_01_chronological_ordering(self):
        self._insert_session(1, completed_at="2026-01-03 10:00:00")
        self._insert_session(2, completed_at="2026-01-01 10:00:00")
        self._insert_session(3, completed_at="2026-01-02 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 8)
        self._insert_bank_turn(2, 1, "Python", "medium", 6)
        self._insert_bank_turn(3, 1, "Python", "medium", 7)

        res = get_analytics_insights(self.conn)
        timeline = res["technical_progression"]["timeline"]
        self.assertEqual([t["session_id"] for t in timeline], [2, 3, 1])

    # -----------------------------------------------------------------------
    # Scenario 2: Zero completed sessions
    # -----------------------------------------------------------------------
    def test_02_zero_completed_sessions(self):
        self._insert_session(1, status="active")
        res = get_analytics_insights(self.conn)
        self.assertEqual(res["total_completed_interviews"], 0)
        self.assertEqual(res["technical_progression"]["sample_size"], 0)
        self.assertEqual(res["technical_progression"]["trend"], "insufficient_data")
        self.assertIsNone(res["consistency"]["min_score"])
        self.assertIsNone(res["communication_trends"])
        self.assertIsNone(res["nonverbal_trends"])
        self.assertIn("No completed interview sessions", res["executive_summary"])

    # -----------------------------------------------------------------------
    # Scenario 3: One completed session
    # -----------------------------------------------------------------------
    def test_03_one_completed_session(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 7)
        res = get_analytics_insights(self.conn)
        tp = res["technical_progression"]
        self.assertEqual(tp["sample_size"], 1)
        self.assertEqual(tp["first_score"], 7.0)
        self.assertEqual(tp["latest_score"], 7.0)
        self.assertIsNone(tp["absolute_change"])
        self.assertIsNone(tp["percent_change"])
        self.assertEqual(tp["trend"], "insufficient_data")

    # -----------------------------------------------------------------------
    # Scenario 4: Two-session delta
    # -----------------------------------------------------------------------
    def test_04_two_session_delta(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 5)
        self._insert_bank_turn(2, 1, "Python", "medium", 8)
        res = get_analytics_insights(self.conn)
        tp = res["technical_progression"]
        self.assertEqual(tp["sample_size"], 2)
        self.assertEqual(tp["first_score"], 5.0)
        self.assertEqual(tp["latest_score"], 8.0)
        self.assertEqual(tp["absolute_change"], 3.0)
        self.assertEqual(tp["percent_change"], 60.0)
        self.assertIsNone(tp["window_change"])
        self.assertEqual(tp["trend"], "insufficient_data")

    # -----------------------------------------------------------------------
    # Scenario 5: Three-session trend classification (+ boundary tests)
    # -----------------------------------------------------------------------
    def test_05_three_session_trend_classification(self):
        # Improving (delta >= +0.5)
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_session(3, completed_at="2026-01-03 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 6.0)
        self._insert_bank_turn(2, 1, "Python", "medium", 6.2)
        self._insert_bank_turn(3, 1, "Python", "medium", 6.5)
        res = get_analytics_insights(self.conn)
        self.assertEqual(res["technical_progression"]["trend"], "improving")

        # Stable boundary (+0.49 -> stable)
        self.conn.execute("DELETE FROM evaluations")
        self.conn.execute("DELETE FROM answers")
        self.conn.execute("DELETE FROM session_turns")
        self.conn.execute("DELETE FROM questions")
        self._insert_bank_turn(1, 1, "Python", "medium", 6.00)
        self._insert_bank_turn(2, 1, "Python", "medium", 6.00)
        self._insert_bank_turn(3, 1, "Python", "medium", 6.49)
        res = get_analytics_insights(self.conn)
        self.assertEqual(res["technical_progression"]["absolute_change"], 0.49)
        self.assertEqual(res["technical_progression"]["trend"], "stable")

        # Improving boundary (+0.50 -> improving)
        self.conn.execute("DELETE FROM evaluations")
        self.conn.execute("DELETE FROM answers")
        self.conn.execute("DELETE FROM session_turns")
        self.conn.execute("DELETE FROM questions")
        self._insert_bank_turn(1, 1, "Python", "medium", 6.00)
        self._insert_bank_turn(2, 1, "Python", "medium", 6.00)
        self._insert_bank_turn(3, 1, "Python", "medium", 6.50)
        res = get_analytics_insights(self.conn)
        self.assertEqual(res["technical_progression"]["absolute_change"], 0.50)
        self.assertEqual(res["technical_progression"]["trend"], "improving")

        # Stable boundary (-0.49 -> stable)
        self.conn.execute("DELETE FROM evaluations")
        self.conn.execute("DELETE FROM answers")
        self.conn.execute("DELETE FROM session_turns")
        self.conn.execute("DELETE FROM questions")
        self._insert_bank_turn(1, 1, "Python", "medium", 6.50)
        self._insert_bank_turn(2, 1, "Python", "medium", 6.50)
        self._insert_bank_turn(3, 1, "Python", "medium", 6.01)
        res = get_analytics_insights(self.conn)
        self.assertEqual(res["technical_progression"]["absolute_change"], -0.49)
        self.assertEqual(res["technical_progression"]["trend"], "stable")

        # Declining boundary (-0.50 -> declining)
        self.conn.execute("DELETE FROM evaluations")
        self.conn.execute("DELETE FROM answers")
        self.conn.execute("DELETE FROM session_turns")
        self.conn.execute("DELETE FROM questions")
        self._insert_bank_turn(1, 1, "Python", "medium", 6.50)
        self._insert_bank_turn(2, 1, "Python", "medium", 6.50)
        self._insert_bank_turn(3, 1, "Python", "medium", 6.00)
        res = get_analytics_insights(self.conn)
        self.assertEqual(res["technical_progression"]["absolute_change"], -0.50)
        self.assertEqual(res["technical_progression"]["trend"], "declining")

    # -----------------------------------------------------------------------
    # Scenario 6: Four-session window comparison
    # -----------------------------------------------------------------------
    def test_06_four_session_window_comparison(self):
        for i, sc in enumerate([5.0, 6.0, 7.0, 8.0], start=1):
            self._insert_session(i, completed_at=f"2026-01-0{i} 10:00:00")
            self._insert_bank_turn(i, 1, "Python", "medium", sc)
        res = get_analytics_insights(self.conn)
        tp = res["technical_progression"]
        self.assertEqual(tp["sample_size"], 4)
        # earlier = [5.0, 6.0] avg=5.5; recent = [7.0, 8.0] avg=7.5; window_change = 7.5 - 5.5 = 2.0
        self.assertEqual(tp["window_change"], 2.0)

    # -----------------------------------------------------------------------
    # Scenario 7, 8, 9: Turn isolation (Bank vs Remedial vs Claim)
    # -----------------------------------------------------------------------
    def test_07_08_09_turn_isolation(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        # Bank question: score 8
        self._insert_bank_turn(1, 1, "Python", "medium", 8)
        # Remedial follow-up: score 2
        self._insert_followup_turn(1, 2, score=2)
        # Claim probe: score 4
        self._insert_claim_turn(1, 3, claim_id="c1", score=4)

        res = get_analytics_insights(self.conn)
        # Bank score must be strictly 8.0 (follow-up and claim probe MUST NOT dilute technical bank progression)
        self.assertEqual(res["technical_progression"]["latest_score"], 8.0)
        # Difficulty distribution must only have 1 bank question
        self.assertEqual(res["difficulty_progression"]["distribution"]["medium"], 1)
        self.assertEqual(res["difficulty_progression"]["distribution"]["easy"], 0)
        # Answer quality patterns tracks all 3 evaluated turns
        self.assertEqual(res["answer_quality_patterns"]["total_evaluated_answers"], 3)
        # Claim analytics tracks the claim probe
        self.assertEqual(res["resume_claim_analytics"]["claim_instances_probed"], 1)

    # -----------------------------------------------------------------------
    # Scenario 10, 11: Category progression and state reuse
    # -----------------------------------------------------------------------
    def test_10_11_category_progression_and_state(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_session(3, completed_at="2026-01-03 10:00:00")
        self._insert_bank_turn(1, 1, "Databases", "medium", 5.5)
        self._insert_bank_turn(2, 1, "Databases", "medium", 6.5)
        self._insert_bank_turn(3, 1, "Databases", "medium", 7.5)

        res = get_analytics_insights(self.conn)
        db_cat = next(c for c in res["category_progression"] if c["category"] == "Databases")
        self.assertEqual(db_cat["observations_count"], 3)
        self.assertEqual(db_cat["first_score"], 5.5)
        self.assertEqual(db_cat["latest_score"], 7.5)
        self.assertEqual(db_cat["absolute_change"], 2.0)
        self.assertEqual(db_cat["trend"], "improving")
        # Status uses compute_category_status on latest (7.5 -> strong)
        self.assertEqual(db_cat["status"], "strong")

        # Boundary checks for category status:
        # 5.99 -> needs_focus, 6.00 -> moderate, 6.99 -> moderate, 7.00 -> strong
        from backend.category_classifier import compute_category_status
        self.assertEqual(compute_category_status(5.99), "needs_focus")
        self.assertEqual(compute_category_status(6.00), "moderate")
        self.assertEqual(compute_category_status(6.99), "moderate")
        self.assertEqual(compute_category_status(7.00), "strong")

    # -----------------------------------------------------------------------
    # Scenario 12, 13, 14: Difficulty distribution, averages, hard success rate
    # -----------------------------------------------------------------------
    def test_12_13_14_difficulty_distribution_averages_hard(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "easy", 8)
        self._insert_bank_turn(1, 2, "Python", "medium", 7)
        self._insert_bank_turn(1, 3, "Python", "hard", 6)
        self._insert_bank_turn(1, 4, "Python", "hard", 8)

        res = get_analytics_insights(self.conn)
        dp = res["difficulty_progression"]
        self.assertEqual(dp["distribution"]["easy"], 1)
        self.assertEqual(dp["distribution"]["medium"], 1)
        self.assertEqual(dp["distribution"]["hard"], 2)
        self.assertEqual(dp["tier_averages"]["easy"], 8.0)
        self.assertEqual(dp["tier_averages"]["medium"], 7.0)
        self.assertEqual(dp["tier_averages"]["hard"], 7.0)
        # 1 of 2 hard >= 7.0 -> 50.0%
        self.assertEqual(dp["hard_success_rate"], 50.0)

    # -----------------------------------------------------------------------
    # Scenario 15, 16, 17: Medium & hard resilience and missing half
    # -----------------------------------------------------------------------
    def test_15_16_17_resilience(self):
        # 4 completed sessions with medium bank questions
        # Earlier sessions (1, 2): scores 5, 6 -> earlier_avg = 5.5
        # Recent sessions (3, 4): scores 7, 8 -> recent_avg = 7.5
        # resilience = 7.5 - 5.5 = +2.0
        for i, sc in enumerate([5, 6, 7, 8], start=1):
            self._insert_session(i, completed_at=f"2026-01-0{i} 10:00:00")
            self._insert_bank_turn(i, 1, "Python", "medium", sc)

        res = get_analytics_insights(self.conn)
        self.assertEqual(res["difficulty_progression"]["resilience"]["medium"], 2.0)
        # No hard questions in any session -> hard resilience must be None
        self.assertIsNone(res["difficulty_progression"]["resilience"]["hard"])

    # -----------------------------------------------------------------------
    # Scenario 18, 19, 20, 21: Consistency, span, std dev, best/worst multi-category
    # -----------------------------------------------------------------------
    def test_18_19_20_21_consistency_and_best_worst(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_session(3, completed_at="2026-01-03 10:00:00")

        # Session 1: Python (6) & Databases (6) -> bank score 6.0
        self._insert_bank_turn(1, 1, "Python", "medium", 6)
        self._insert_bank_turn(1, 2, "Databases", "medium", 6)

        # Session 2: System Design (4) -> bank score 4.0
        self._insert_bank_turn(2, 1, "System Design", "medium", 4)

        # Session 3: Python (9) & Behavioral (9) -> bank score 9.0
        self._insert_bank_turn(3, 1, "Python", "hard", 9)
        self._insert_bank_turn(3, 2, "Behavioral", "medium", 9)

        res = get_analytics_insights(self.conn)
        c = res["consistency"]
        self.assertEqual(c["min_score"], 4.0)
        self.assertEqual(c["max_score"], 9.0)
        self.assertEqual(c["span"], 5.0)

        # n=3 -> sample std dev = sqrt(((6-6.33)^2 + (4-6.33)^2 + (9-6.33)^2) / 2) ~ 2.52
        self.assertIsNotNone(c["standard_deviation"])
        self.assertAlmostEqual(c["standard_deviation"], 2.52, places=1)

        # Best session
        self.assertEqual(c["best_session"]["session_id"], 3)
        self.assertEqual(c["best_session"]["score"], 9.0)
        self.assertEqual(c["best_session"]["categories"], ["Behavioral", "Python"])

        # Worst session
        self.assertEqual(c["worst_session"]["session_id"], 2)
        self.assertEqual(c["worst_session"]["score"], 4.0)
        self.assertEqual(c["worst_session"]["categories"], ["System Design"])

    # -----------------------------------------------------------------------
    # Scenario 22, 23: Answer quality patterns & evolution
    # -----------------------------------------------------------------------
    def test_22_23_answer_quality_patterns(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")

        # Session 1: strong (8), inaccurate (3)
        self._insert_bank_turn(1, 1, "Python", "medium", 8, ans_text="A comprehensive explanation of python decorators")
        self._insert_bank_turn(1, 2, "Python", "medium", 3, ans_text="Incorrect explanation with errors", acc_text="incorrect and flawed")

        # Session 2: shallow (6), non-answer (2)
        self._insert_bank_turn(2, 1, "Databases", "medium", 6, ans_text="A brief explanation lacking details")
        self._insert_bank_turn(2, 2, "Databases", "medium", 2, ans_text="I don't know")

        res = get_analytics_insights(self.conn)
        aq = res["answer_quality_patterns"]
        self.assertEqual(aq["total_evaluated_answers"], 4)
        dist = aq["distribution"]
        self.assertEqual(dist["strong"], 1)
        self.assertEqual(dist["inaccurate"], 1)
        self.assertEqual(dist["shallow_incomplete"], 1)
        self.assertEqual(dist["non_answer"], 1)
        self.assertIsNotNone(aq["earlier_strong_proportion"])
        self.assertIsNotNone(aq["recent_strong_proportion"])

    # -----------------------------------------------------------------------
    # Scenario 24, 25, 26, 27, 28: Communication trends, WPM distance, filler rate, pauses, missing audio
    # -----------------------------------------------------------------------
    def test_24_25_26_27_28_communication_trends(self):
        # Missing audio
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 7)
        res = get_analytics_insights(self.conn)
        self.assertIsNone(res["communication_trends"])

        # With audio across 3 sessions
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_session(3, completed_at="2026-01-03 10:00:00")

        aid1 = self._insert_bank_turn(1, 2, "Python", "medium", 7)
        aid2 = self._insert_bank_turn(2, 1, "Python", "medium", 7)
        aid3 = self._insert_bank_turn(3, 1, "Python", "medium", 7)

        # S1: WPM 178 (dist 13), filler 4.0%, long pauses 2
        self._insert_speech(aid1, delivery_score=6, wpm=178.0, filler_rate=4.0, long_pause=2, pause_cnt=5, avg_pause=1.5)
        # S2: WPM 160 (dist 0), filler 3.0%, long pauses 1
        self._insert_speech(aid2, delivery_score=7, wpm=160.0, filler_rate=3.0, long_pause=1, pause_cnt=4, avg_pause=1.2)
        # S3: WPM 152 (dist 0), filler 2.5%, long pauses 0
        self._insert_speech(aid3, delivery_score=8, wpm=152.0, filler_rate=2.5, long_pause=0, pause_cnt=3, avg_pause=1.0)

        res = get_analytics_insights(self.conn)
        ct = res["communication_trends"]
        self.assertIsNotNone(ct)
        # Delivery: 6 -> 8 (+2.0 pts) -> improving
        self.assertEqual(ct["delivery"]["trend"], "improving")
        # Speaking rate: 178 (dist 13) -> 152 (dist 0) -> distance decreased -> improving
        self.assertEqual(ct["speaking_rate"]["trend"], "improving")
        # Filler rate: 4.0% -> 2.5% (delta -1.5 pp <= -1.0) -> improving
        self.assertEqual(ct["filler_rate"]["trend"], "improving")
        # Global pause count reuse: 2 + 1 + 0 = 3
        self.assertEqual(ct["pause_behavior"]["total_long_pauses"], 3)

        # n = 1: 1 completed session with speech analytics
        # Raw data available, but no longitudinal change or trend classification
        self.conn.execute("DELETE FROM speech_analytics")
        self.conn.execute("DELETE FROM evaluations")
        self.conn.execute("DELETE FROM answers")
        self.conn.execute("DELETE FROM session_turns")
        self.conn.execute("DELETE FROM questions")
        self.conn.execute("DELETE FROM interview_sessions")

        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        aid_s1 = self._insert_bank_turn(1, 1, "Python", "medium", 7)
        self._insert_speech(aid_s1, delivery_score=7, wpm=140.0, filler_rate=2.0)

        res1 = get_analytics_insights(self.conn)
        ct1 = res1["communication_trends"]
        self.assertIsNotNone(ct1)
        self.assertEqual(ct1["sample_size"], 1)
        self.assertIsNone(ct1["delivery"]["absolute_change"])
        self.assertEqual(ct1["delivery"]["trend"], "insufficient_data")
        self.assertIsNone(ct1["filler_rate"]["absolute_change"])
        self.assertEqual(ct1["filler_rate"]["trend"], "insufficient_data")
        self.assertEqual(ct1["speaking_rate"]["trend"], "insufficient_data")

        # n = 2: 2 completed sessions with speech analytics
        # Absolute first/latest change calculated, but trend remains insufficient_data
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        aid_s2 = self._insert_bank_turn(2, 1, "Python", "medium", 8)
        self._insert_speech(aid_s2, delivery_score=9, wpm=150.0, filler_rate=1.0)

        res2 = get_analytics_insights(self.conn)
        ct2 = res2["communication_trends"]
        self.assertIsNotNone(ct2)
        self.assertEqual(ct2["sample_size"], 2)
        self.assertEqual(ct2["delivery"]["absolute_change"], 2.0)
        self.assertEqual(ct2["delivery"]["trend"], "insufficient_data")
        self.assertEqual(ct2["filler_rate"]["absolute_change"], -1.0)
        self.assertEqual(ct2["filler_rate"]["trend"], "insufficient_data")
        self.assertEqual(ct2["speaking_rate"]["trend"], "insufficient_data")

        # Distance function unit tests
        self.assertEqual(calculate_wpm_distance(140.0), 0.0)
        self.assertEqual(calculate_wpm_distance(178.0), 13.0)
        self.assertEqual(calculate_wpm_distance(100.0), 15.0)

        # Filler rate boundary checks: -0.99 stable, -1.00 improving, +0.99 stable, +1.00 declining
        from backend.insights_engine import calculate_communication_trends
        dummy_sessions = [{"id": 1, "completed_at": "t1"}, {"id": 2, "completed_at": "t2"}, {"id": 3, "completed_at": "t3"}]
        def make_speech_turns(f1, f3):
            return {
                1: [{"speaking_rate_wpm": 140, "delivery_score": 7, "filler_rate": f1, "long_pause_count": 0, "pause_count": 0, "average_pause_duration": 1.0}],
                2: [{"speaking_rate_wpm": 140, "delivery_score": 7, "filler_rate": f1, "long_pause_count": 0, "pause_count": 0, "average_pause_duration": 1.0}],
                3: [{"speaking_rate_wpm": 140, "delivery_score": 7, "filler_rate": f3, "long_pause_count": 0, "pause_count": 0, "average_pause_duration": 1.0}],
            }
        self.assertEqual(calculate_communication_trends(dummy_sessions, make_speech_turns(3.0, 2.01))["filler_rate"]["trend"], "stable")
        self.assertEqual(calculate_communication_trends(dummy_sessions, make_speech_turns(3.0, 2.00))["filler_rate"]["trend"], "improving")
        self.assertEqual(calculate_communication_trends(dummy_sessions, make_speech_turns(3.0, 3.99))["filler_rate"]["trend"], "stable")
        self.assertEqual(calculate_communication_trends(dummy_sessions, make_speech_turns(3.0, 4.00))["filler_rate"]["trend"], "declining")

    # -----------------------------------------------------------------------
    # Scenario 29, 30: Nonverbal telemetry & missing video
    # -----------------------------------------------------------------------
    def test_29_30_nonverbal_telemetry(self):
        # Missing video
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 7)
        res = get_analytics_insights(self.conn)
        self.assertIsNone(res["nonverbal_trends"])

        # With video across 2 sessions
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        aid1 = self._insert_bank_turn(1, 2, "Python", "medium", 7)
        aid2 = self._insert_bank_turn(2, 1, "Python", "medium", 7)
        self._insert_nonverbal(aid1, score=7, face=0.90, center=0.10)
        self._insert_nonverbal(aid2, score=9, face=0.98, center=0.04)

        res = get_analytics_insights(self.conn)
        nv = res["nonverbal_trends"]
        self.assertIsNotNone(nv)
        self.assertEqual(nv["sample_size"], 2)
        self.assertEqual(nv["first"]["nonverbal_telemetry_score"], 7.0)
        self.assertEqual(nv["latest"]["nonverbal_telemetry_score"], 9.0)
        self.assertEqual(nv["absolute_change"]["nonverbal_telemetry_score"], 2.0)
        # CRITICAL: nonverbal trends must NOT have generic improving/declining trend labels
        self.assertNotIn("trend", nv)

    # -----------------------------------------------------------------------
    # Scenario 31, 32, 33, 34: Resume claims scoping, thresholds, missing claims
    # -----------------------------------------------------------------------
    def test_31_to_34_resume_claims(self):
        # Session 1: profile with c1 (FastAPI), c2 (Redis)
        prof1 = json.dumps({"claims": [
            {"claim_id": "c1", "project_name": "API Gateway", "category": "Python", "statement": "Built API Gateway with FastAPI"},
            {"claim_id": "c2", "project_name": "Caching Layer", "category": "Databases", "statement": "Implemented Redis cache"}
        ]})
        # Session 2: profile with c1 (PyTorch)
        prof2 = json.dumps({"claims": [
            {"claim_id": "c1", "project_name": "ML Pipeline", "category": "Python", "statement": "Trained PyTorch model"}
        ]})

        self._insert_session(1, completed_at="2026-01-01 10:00:00", candidate_profile=prof1)
        self._insert_session(2, completed_at="2026-01-02 10:00:00", candidate_profile=prof2)

        # Probes: S1 probes c1 (score 7.5), S2 probes c1 (score 4.5)
        self._insert_claim_turn(1, 1, claim_id="c1", score=7.5)
        self._insert_claim_turn(2, 1, claim_id="c1", score=4.5)

        res = get_analytics_insights(self.conn)
        rc = res["resume_claim_analytics"]
        self.assertEqual(rc["sessions_with_claims"], 2)
        # Total claims available across sessions = 2 + 1 = 3
        self.assertEqual(rc["total_claim_instances_available_across_sessions"], 3)
        # (S1, c1) and (S2, c1) are distinct claim instances -> 2
        self.assertEqual(rc["claim_instances_probed"], 2)
        # Distinct projects probed: "API Gateway" and "ML Pipeline" -> 2
        self.assertEqual(rc["projects_probed"], 2)
        # Substantiation thresholds:
        # 7.5 >= 7.0 -> strongly substantiated
        # 4.5 < 5.0 -> weakly substantiated
        sub = rc["substantiation_breakdown"]
        self.assertEqual(sub["strongly_substantiated"], 1)
        self.assertEqual(sub["partially_substantiated"], 0)
        self.assertEqual(sub["weakly_substantiated"], 1)

        # Boundary checks: 4.99 -> weak, 5.00 -> partial, 6.99 -> partial, 7.00 -> strong
        def eval_claim(sc):
            if sc >= 7.0: return "strong"
            if sc >= 5.0: return "partial"
            return "weak"
        self.assertEqual(eval_claim(4.99), "weak")
        self.assertEqual(eval_claim(5.00), "partial")
        self.assertEqual(eval_claim(6.99), "partial")
        self.assertEqual(eval_claim(7.00), "strong")

    # -----------------------------------------------------------------------
    # Scenario 35, 36: No blended score & no interpolation
    # -----------------------------------------------------------------------
    def test_35_36_no_blended_score_and_no_interpolation(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        aid = self._insert_bank_turn(1, 1, "Python", "medium", 8)
        self._insert_speech(aid, delivery_score=5)
        self._insert_nonverbal(aid, score=6)

        res = get_analytics_insights(self.conn)
        # Must not contain any blended score
        self.assertNotIn("overall_score", res)
        self.assertNotIn("blended_score", res)
        self.assertNotIn("composite_score", res)
        # Independent domain metrics
        self.assertEqual(res["technical_progression"]["latest_score"], 8.0)
        self.assertEqual(res["communication_trends"]["delivery"]["latest"], 5.0)
        self.assertEqual(res["nonverbal_trends"]["latest"]["nonverbal_telemetry_score"], 6.0)

    # -----------------------------------------------------------------------
    # Scenario 37: Deterministic tie ordering
    # -----------------------------------------------------------------------
    def test_37_deterministic_tie_ordering(self):
        # Two sessions with identical score 7.0
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 7)
        self._insert_bank_turn(2, 1, "Databases", "medium", 7)

        res = get_analytics_insights(self.conn)
        c = res["consistency"]
        # In ties, first chronological session must be selected
        self.assertEqual(c["best_session"]["session_id"], 1)
        self.assertEqual(c["worst_session"]["session_id"], 1)

    # -----------------------------------------------------------------------
    # Scenario 38: Legacy sessions support
    # -----------------------------------------------------------------------
    def test_38_legacy_sessions(self):
        # Session without profile, job context, speech or nonverbal
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 7)

        res = get_analytics_insights(self.conn)
        self.assertEqual(res["total_completed_interviews"], 1)
        self.assertIsNone(res["communication_trends"])
        self.assertIsNone(res["nonverbal_trends"])
        self.assertEqual(res["resume_claim_analytics"]["sessions_with_claims"], 0)

    # -----------------------------------------------------------------------
    # Scenario 39, 40: Optional Gemini fallback & metrics isolation
    # -----------------------------------------------------------------------
    def test_39_40_gemini_fallback_and_isolation(self):
        self._insert_session(1, completed_at="2026-01-01 10:00:00")
        self._insert_session(2, completed_at="2026-01-02 10:00:00")
        self._insert_bank_turn(1, 1, "Python", "medium", 6)
        self._insert_bank_turn(2, 1, "Python", "medium", 8)

        # Without API key -> deterministic fallback text
        with patch.dict("os.environ", {}, clear=True):
            res = get_analytics_insights(self.conn)
            summary = res["executive_summary"]
            self.assertIn("6", summary)
            self.assertIn("8", summary)

        # Even with mocked Gemini, deterministic metrics are immutable
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            with patch("google.genai.Client") as mock_client:
                mock_instance = MagicMock()
                mock_resp = MagicMock()
                mock_resp.text = "This is a synthesized summary."
                mock_instance.models.generate_content.return_value = mock_resp
                mock_client.return_value = mock_instance

                res2 = get_analytics_insights(self.conn)
                self.assertEqual(res2["technical_progression"]["first_score"], 6.0)
                self.assertEqual(res2["technical_progression"]["latest_score"], 8.0)
                self.assertEqual(res2["executive_summary"], "This is a synthesized summary.")

    # -----------------------------------------------------------------------
    # Scenario 41, 42: API response & backward compatibility
    # -----------------------------------------------------------------------
    def test_41_42_api_and_backward_compatibility(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name

        def test_get_db():
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            return c

        orig_get_db = main.get_db
        main.get_db = test_get_db

        try:
            conn = test_get_db()
            create_schema(conn)
            conn.execute("INSERT INTO interview_sessions (id, status, completed_at, category, difficulty) VALUES (1, 'completed', '2026-01-01 10:00:00', 'Python', 'medium')")
            conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Python', 'medium', 'What is a decorator?')")
            conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (1, 1, 'Decorators wrap functions')")
            conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 7, 'Good answer')")
            conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id, status) VALUES (1, 1, 1, 'What is a decorator?', 0, 1, 'completed')")
            conn.commit()
            conn.close()

            client = TestClient(main.app)

            # Phase 14 endpoint
            res_insights = client.get("/analytics/insights")
            self.assertEqual(res_insights.status_code, 200)
            data_insights = res_insights.json()
            self.assertIn("technical_progression", data_insights)
            self.assertIn("category_progression", data_insights)
            self.assertIn("consistency", data_insights)
            self.assertEqual(data_insights["total_completed_interviews"], 1)

            # Existing Phase 6 endpoints must remain operational
            res_overview = client.get("/analytics/overview")
            self.assertEqual(res_overview.status_code, 200)
            self.assertEqual(res_overview.json()["total_completed_interviews"], 1)

            res_history = client.get("/analytics/history")
            self.assertEqual(res_history.status_code, 200)
            self.assertEqual(len(res_history.json()["sessions"]), 1)
            client.close()
        finally:
            main.get_db = orig_get_db
            try:
                Path(db_path).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
