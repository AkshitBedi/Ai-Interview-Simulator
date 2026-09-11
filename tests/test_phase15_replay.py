"""
tests/test_phase15_replay.py

Comprehensive test suite for Phase 15: Interview Replay & Detailed Session Review.
Covers all 22 approved test scenarios:
 1. Completed session returns HTTP 200 with full replay payload
 2. Incomplete/active session returns HTTP 400 Bad Request
 3. Nonexistent session returns HTTP 404 Not Found
 4. Strict chronological ordering (ORDER BY turn_number ASC, id ASC; never question_id)
 5. Bank question turn structure
 6. Remedial follow-up turn structure and parent linkage
 7. Resume claim probe structure and claim resolution
 8. Unresolved claim handling with safe fallback
 9. Defensive turn classification (handles malformed combinations)
 10. Answer and evaluation fidelity
 11. Speech analytics linkage
 12. Nonverbal analytics linkage
 13. Null missing modality guarantee (never zeroed)
 14. Sanitized CandidateProfile and JobContext exposure
 15. Privacy exclusions (no raw resume, raw JD, raw media, or prompts)
 16. Session summary fidelity (exact match with get_session_summary)
 17. No secondary scoring (direct Phase 2 evaluation score reuse)
 18. Zero Gemini / LLM calls during replay
 19. Server restart / database connection reopen reconstruction
 20. Legacy session tolerance (pre-Phase 11/12/13 sessions)
 21. Malformed JSON resilience (defensive fallback on corrupt JSON strings)
 22. Multi-category session replay and coverage
"""

import sys
import json
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
from backend.interview_engine import (
    get_session_replay,
    get_session_summary,
    SessionNotFoundError,
    IncompleteSessionError
)


def create_schema(conn: sqlite3.Connection):
    """Creates the exact SQLite schema up to Phase 14 with zero Phase 15 schema changes."""
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


class TestPhase15Replay(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        create_schema(self.conn)

        # Patch get_db in backend.main
        self.get_db_patch = patch("backend.main.get_db", side_effect=self._get_test_db)
        self.get_db_patch.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.get_db_patch.stop()
        self.conn.close()
        try:
            Path(self.db_path).unlink()
        except OSError:
            pass

    def _get_test_db(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    # 1. Completed session returns HTTP 200 with full replay payload
    def test_replay_completed_session_200(self):
        profile = {
            "skills": ["Python", "PostgreSQL"],
            "past_roles": ["Senior Engineer"],
            "projects": [{"name": "Auth Service", "description": "OAuth provider", "technologies": ["Python"]}],
            "years_of_experience": 5.0,
            "top_domains": ["Backend"],
            "claims": [{
                "claim_id": "c1",
                "statement": "Reduced API latency by 40%",
                "project_name": "Auth Service",
                "category": "Python",
                "claim_type": "performance",
                "technologies": ["Python"],
                "metric": "40% latency reduction",
                "ownership": "lead"
            }]
        }
        job = {
            "title": "Staff Backend Engineer",
            "required_skills": ["Python", "Distributed Systems"],
            "preferred_skills": ["Kubernetes"],
            "responsibilities": ["Scale core architecture"],
            "seniority_level": "senior"
        }
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (
                category, difficulty, status, current_turn, max_turns,
                completed_at, target_role, experience_level, selected_categories,
                interviewer_style, candidate_profile, job_context
            ) VALUES (
                'Python', 'medium', 'completed', 2, 2,
                CURRENT_TIMESTAMP, 'Staff Backend Engineer', 'senior',
                '["Python"]', 'strict', ?, ?
            )
        """, (json.dumps(profile), json.dumps(job)))
        sess_id = cur.lastrowid

        cur = self.conn.execute(
            "INSERT INTO questions (category, difficulty, question, topic, quality_tier) VALUES ('Python', 'medium', 'Explain GIL', 'Internals', 'core')"
        )
        q1_id = cur.lastrowid
        cur = self.conn.execute("INSERT INTO answers (question_id, answer) VALUES (?, 'The GIL locks thread execution')", (q1_id,))
        ans1_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy, strengths, missing_points) VALUES (?, 8, 'Good', 'Accurate', ?, ?)",
            (ans1_id, json.dumps(["Clear"]), json.dumps(["Subinterpreters"]))
        )
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, answer_id, status)
            VALUES (?, 1, ?, 'Explain GIL', 0, NULL, ?, 'evaluated')
        """, (sess_id, q1_id, ans1_id))

        cur = self.conn.execute("INSERT INTO answers (question_id, answer) VALUES (NULL, 'Used asyncio profiling')")
        ans2_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy, strengths, missing_points) VALUES (?, 9, 'Great', 'Deep', ?, ?)",
            (ans2_id, json.dumps(["Profiling"]), json.dumps([]))
        )
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, answer_id, status, claim_id)
            VALUES (?, 2, NULL, 'How did you achieve 40% latency reduction?', 1, 1, ?, 'evaluated', 'c1')
        """, (sess_id, ans2_id))
        self.conn.commit()

        resp = self.client.get(f"/sessions/{sess_id}/replay")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["session_id"], sess_id)
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["configuration"]["interviewer_style"], "strict")
        self.assertEqual(data["configuration"]["experience_level"], "senior")
        self.assertEqual(data["configuration"]["target_role"], "Staff Backend Engineer")
        self.assertEqual(data["configuration"]["selected_categories"], ["Python"])
        self.assertIsNotNone(data["context"]["candidate_profile"])
        self.assertIsNotNone(data["context"]["job_context"])
        self.assertIn("summary", data)
        self.assertEqual(len(data["turns"]), 2)
        self.assertEqual(data["turns"][0]["turn_type"], "bank_question")
        self.assertEqual(data["turns"][1]["turn_type"], "claim_probe")

    # 2. Incomplete/active session returns HTTP 400 Bad Request
    def test_replay_incomplete_session_400(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('active')")
        sess_id = cur.lastrowid
        self.conn.commit()

        resp = self.client.get(f"/sessions/{sess_id}/replay")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Interview session is still in progress", resp.json()["detail"])

    # 3. Nonexistent session returns HTTP 404 Not Found
    def test_replay_nonexistent_session_404(self):
        resp = self.client.get("/sessions/99999/replay")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Interview session not found", resp.json()["detail"])

    # 4. Strict chronological ordering (ORDER BY turn_number ASC, id ASC)
    def test_replay_strict_chronological_ordering(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        q100 = self.conn.execute("INSERT INTO questions (category, difficulty, question) VALUES ('Python', 'easy', 'Q100')").lastrowid
        q1 = self.conn.execute("INSERT INTO questions (category, difficulty, question) VALUES ('Python', 'easy', 'Q1')").lastrowid

        t2_id = self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up)
            VALUES (?, 2, ?, 'Q1', 0)
        """, (sess_id, q1)).lastrowid

        t1_id = self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up)
            VALUES (?, 1, ?, 'Q100', 0)
        """, (sess_id, q100)).lastrowid
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        turns = replay["turns"]
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["turn_number"], 1)
        self.assertEqual(turns[0]["turn_id"], t1_id)
        self.assertEqual(turns[0]["question"]["question_id"], q100)
        self.assertEqual(turns[1]["turn_number"], 2)
        self.assertEqual(turns[1]["turn_id"], t2_id)
        self.assertEqual(turns[1]["question"]["question_id"], q1)

    # 5. Bank question turn structure
    def test_replay_bank_turn_structure(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        q_id = self.conn.execute(
            "INSERT INTO questions (category, difficulty, question, topic, quality_tier) VALUES ('Databases', 'hard', 'B-Tree depth', 'Storage', 'advanced')"
        ).lastrowid
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id)
            VALUES (?, 1, ?, 'B-Tree depth', 0, NULL)
        """, (sess_id, q_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t = replay["turns"][0]
        self.assertEqual(t["turn_type"], "bank_question")
        self.assertIsNone(t["parent_turn_id"])
        self.assertIsNone(t["parent_turn_number"])
        self.assertIsNone(t["claim_probe"])
        self.assertEqual(t["question"]["question_id"], q_id)
        self.assertEqual(t["question"]["topic"], "Storage")
        self.assertEqual(t["question"]["quality_tier"], "advanced")
        self.assertEqual(t["category"], "Databases")
        self.assertEqual(t["difficulty"], "hard")

    # 6. Remedial follow-up turn structure and parent linkage
    def test_replay_remedial_follow_up_structure(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        t1_id = self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up)
            VALUES (?, 1, NULL, 'Base Question', 0)
        """, (sess_id,)).lastrowid

        t2_id = self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id)
            VALUES (?, 2, NULL, 'Follow up on edge case', 1, ?)
        """, (sess_id, t1_id)).lastrowid
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t2 = replay["turns"][1]
        self.assertEqual(t2["turn_type"], "remedial_follow_up")
        self.assertEqual(t2["parent_turn_id"], t1_id)
        self.assertEqual(t2["parent_turn_number"], 1)
        self.assertIsNone(t2["claim_probe"])
        self.assertIsNone(t2["question"]["question_id"])

    # 7. Resume claim probe structure and claim resolution
    def test_replay_claim_probe_structure(self):
        profile = {
            "claims": [{
                "claim_id": "c1",
                "statement": "Architected Redis cluster",
                "project_name": "Caching Grid",
                "category": "Databases",
                "claim_type": "architecture",
                "technologies": ["Redis", "Python"],
                "metric": "100k QPS",
                "ownership": "sole_author"
            }]
        }
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (status, candidate_profile)
            VALUES ('completed', ?)
        """, (json.dumps(profile),))
        sess_id = cur.lastrowid

        t1_id = self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up)
            VALUES (?, 1, NULL, 'Base Question', 0)
        """, (sess_id,)).lastrowid

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, claim_id)
            VALUES (?, 2, NULL, 'How was Redis partitioned?', 1, ?, 'c1')
        """, (sess_id, t1_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t2 = replay["turns"][1]
        self.assertEqual(t2["turn_type"], "claim_probe")
        self.assertEqual(t2["parent_turn_id"], t1_id)
        self.assertEqual(t2["parent_turn_number"], 1)
        cp = t2["claim_probe"]
        self.assertIsNotNone(cp)
        self.assertEqual(cp["claim_id"], "c1")
        self.assertEqual(cp["statement"], "Architected Redis cluster")
        self.assertEqual(cp["project_name"], "Caching Grid")
        self.assertEqual(cp["category"], "Databases")
        self.assertEqual(cp["claim_type"], "architecture")
        self.assertEqual(cp["technologies"], ["Redis", "Python"])
        self.assertEqual(cp["metric"], "100k QPS")
        self.assertEqual(cp["ownership"], "sole_author")

    # 8. Unresolved claim handling with safe fallback
    def test_replay_unresolved_claim_handling(self):
        profile = {"claims": [{"claim_id": "c1", "statement": "Other claim"}]}
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (status, candidate_profile)
            VALUES ('completed', ?)
        """, (json.dumps(profile),))
        sess_id = cur.lastrowid

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, claim_id)
            VALUES (?, 1, NULL, 'Probe for missing claim', 1, 'c99')
        """, (sess_id,))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t = replay["turns"][0]
        self.assertEqual(t["turn_type"], "claim_probe")
        cp = t["claim_probe"]
        self.assertIsNotNone(cp)
        self.assertEqual(cp["claim_id"], "c99")
        self.assertIsNone(cp["statement"])
        self.assertIsNone(cp["project_name"])
        self.assertEqual(cp["technologies"], [])

    # 9. Defensive turn classification (handles malformed combinations)
    def test_replay_defensive_turn_classification(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, is_follow_up, claim_id)
            VALUES (?, 1, 'Malformed 1', 0, 'c1')
        """, (sess_id,))

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, is_follow_up, claim_id)
            VALUES (?, 2, 'Malformed 2', 1, '')
        """, (sess_id,))

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, is_follow_up, claim_id)
            VALUES (?, 3, 'Malformed 3', 1, '   ')
        """, (sess_id,))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        turns = replay["turns"]
        self.assertEqual(turns[0]["turn_type"], "bank_question")
        self.assertIsNone(turns[0]["claim_probe"])
        self.assertEqual(turns[1]["turn_type"], "remedial_follow_up")
        self.assertIsNone(turns[1]["claim_probe"])
        self.assertEqual(turns[2]["turn_type"], "remedial_follow_up")
        self.assertIsNone(turns[2]["claim_probe"])

    # 10. Answer and evaluation fidelity
    def test_replay_answer_and_evaluation_fidelity(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        cur = self.conn.execute("INSERT INTO answers (question_id, answer) VALUES (NULL, 'Exact candidate answer text')")
        ans_id = cur.lastrowid
        self.conn.execute("""
            INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy, strengths, missing_points)
            VALUES (?, 7, 'Detailed feedback', 'Mostly accurate', '["Solid logic", "Good structure"]', '["Missing edge case"]')
        """, (ans_id,))

        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, is_follow_up, answer_id)
            VALUES (?, 1, 'Question text', 0, ?)
        """, (sess_id, ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t = replay["turns"][0]
        self.assertEqual(t["answer"]["answer_id"], ans_id)
        self.assertEqual(t["answer"]["text"], "Exact candidate answer text")
        self.assertEqual(t["evaluation"]["score"], 7)
        self.assertEqual(t["evaluation"]["feedback"], "Detailed feedback")
        self.assertEqual(t["evaluation"]["technical_accuracy"], "Mostly accurate")
        self.assertEqual(t["evaluation"]["strengths"], ["Solid logic", "Good structure"])
        self.assertEqual(t["evaluation"]["missing_points"], ["Missing edge case"])

    # 11. Speech analytics linkage
    def test_replay_speech_analytics_linkage(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Spoken answer')").lastrowid
        self.conn.execute("""
            INSERT INTO speech_analytics (
                answer_id, audio_duration_seconds, speaking_duration_seconds, pause_duration_seconds,
                pause_count, average_pause_duration, long_pause_count, speaking_rate_wpm,
                articulation_rate_wpm, filler_word_count, filler_rate, filler_breakdown,
                repeated_words_count, phonation_ratio, delivery_score, delivery_feedback
            ) VALUES (
                ?, 45.0, 40.0, 5.0, 4, 1.25, 1, 140.0, 150.0, 3, 2.1, '{"um": 2, "like": 1}', 0, 0.88, 8, 'Good delivery'
            )
        """, (ans_id,))
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, answer_id)
            VALUES (?, 1, 'Q', ?)
        """, (sess_id, ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        sa = replay["turns"][0]["speech_analytics"]
        self.assertIsNotNone(sa)
        self.assertEqual(sa["audio_duration_seconds"], 45.0)
        self.assertEqual(sa["speaking_rate_wpm"], 140.0)
        self.assertEqual(sa["filler_word_count"], 3)
        self.assertEqual(sa["filler_breakdown"], {"um": 2, "like": 1})
        self.assertEqual(sa["delivery_score"], 8)

    # 12. Nonverbal analytics linkage
    def test_replay_nonverbal_analytics_linkage(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Video answer')").lastrowid
        self.conn.execute("""
            INSERT INTO nonverbal_analytics (
                answer_id, video_duration_seconds, frames_analyzed, face_detected_ratio,
                centering_offset, gaze_deviation_ratio, avg_yaw_degrees, avg_pitch_degrees,
                avg_roll_degrees, yaw_variance, pitch_variance, roll_variance,
                head_motion_frequency_hz, motion_energy, camera_quality_flags,
                nonverbal_telemetry_score, nonverbal_feedback, vision_backend
            ) VALUES (
                ?, 50.0, 750, 0.98, 0.05, 0.12, 1.5, -2.0, 0.5, 3.2, 2.1, 1.0, 0.8, 4.5, '["low_light"]', 9, 'Good presence', 'mediapipe'
            )
        """, (ans_id,))
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, answer_id)
            VALUES (?, 1, 'Q', ?)
        """, (sess_id, ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        nv = replay["turns"][0]["nonverbal_analytics"]
        self.assertIsNotNone(nv)
        self.assertEqual(nv["face_detected_ratio"], 0.98)
        self.assertEqual(nv["centering_offset"], 0.05)
        self.assertEqual(nv["camera_quality_flags"], ["low_light"])
        self.assertEqual(nv["nonverbal_telemetry_score"], 9)

    # 13. Null missing modality guarantee (never zeroed)
    def test_replay_null_missing_modality_guarantee(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Text answer')").lastrowid
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, answer_id)
            VALUES (?, 1, 'Q', ?)
        """, (sess_id, ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t = replay["turns"][0]
        self.assertIsNone(t["speech_analytics"])
        self.assertIsNone(t["nonverbal_analytics"])

    # 14. Sanitized CandidateProfile and JobContext exposure
    def test_replay_sanitized_profile_and_job_context(self):
        profile = {
            "skills": ["Python", "Docker"],
            "past_roles": ["Software Engineer"],
            "projects": [{"name": "P1", "description": "D1", "technologies": ["Python"]}],
            "years_of_experience": 3.5,
            "top_domains": ["Backend"],
            "claims": []
        }
        job = {
            "title": "Backend Lead",
            "required_skills": ["Python"],
            "preferred_skills": ["Go"],
            "responsibilities": ["Lead team"],
            "seniority_level": "lead"
        }
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (status, candidate_profile, job_context)
            VALUES ('completed', ?, ?)
        """, (json.dumps(profile), json.dumps(job)))
        sess_id = cur.lastrowid
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        ctx = replay["context"]
        self.assertEqual(ctx["candidate_profile"]["skills"], ["Python", "Docker"])
        self.assertEqual(ctx["candidate_profile"]["years_of_experience"], 3.5)
        self.assertEqual(ctx["job_context"]["title"], "Backend Lead")
        self.assertEqual(ctx["job_context"]["seniority_level"], "lead")

    # 15. Privacy exclusions (no raw resume, raw JD, raw media, or prompts)
    def test_replay_privacy_exclusions(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid
        self.conn.commit()

        resp = self.client.get(f"/sessions/{sess_id}/replay")
        self.assertEqual(resp.status_code, 200)
        raw_json_str = resp.text

        self.assertNotIn("resume_text", raw_json_str)
        self.assertNotIn("job_description", raw_json_str)
        self.assertNotIn(".wav", raw_json_str)
        self.assertNotIn(".webm", raw_json_str)
        self.assertNotIn("system_prompt", raw_json_str)
        self.assertNotIn("gemini_prompt", raw_json_str)

    # 16. Session summary fidelity (exact match with get_session_summary)
    def test_replay_summary_fidelity(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status, category, difficulty) VALUES ('completed', 'Python', 'medium')")
        sess_id = cur.lastrowid

        ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Ans')").lastrowid
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, 8, 'Good')", (ans_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_text, answer_id) VALUES (?, 1, 'Q', ?)", (sess_id, ans_id))
        self.conn.commit()

        base_summary = get_session_summary(self.conn, sess_id)
        replay = get_session_replay(self.conn, sess_id)
        rep_summary = replay["summary"]

        self.assertEqual(rep_summary["average_score"], base_summary["average_score"])
        self.assertEqual(rep_summary["total_turns_evaluated"], base_summary["total_turns_evaluated"])
        self.assertEqual(rep_summary["bank_questions_count"], base_summary["bank_questions_count"])
        self.assertEqual(rep_summary["overall_recommendation"], base_summary["overall_recommendation"])

    # 17. No secondary scoring (direct Phase 2 evaluation score reuse)
    def test_replay_no_secondary_scoring(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        for num, score in enumerate([4, 7, 9], start=1):
            ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Ans')").lastrowid
            self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, ?, 'F')", (ans_id, score))
            self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_text, answer_id) VALUES (?, ?, 'Q', ?)", (sess_id, num, ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        scores = [t["evaluation"]["score"] for t in replay["turns"]]
        self.assertEqual(scores, [4, 7, 9])
        self.assertEqual(replay["summary"]["average_score"], 6.7)

    # 18. Zero Gemini / LLM calls during replay
    def test_replay_zero_gemini_calls(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid
        self.conn.commit()

        with patch("google.genai.Client") as mock_client:
            replay = get_session_replay(self.conn, sess_id)
            self.assertIsNotNone(replay)
            mock_client.assert_not_called()

    # 19. Server restart / database connection reopen reconstruction
    def test_replay_server_restart_reconstruction(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status, category) VALUES ('completed', 'Databases')")
        sess_id = cur.lastrowid
        ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Disk persistence')").lastrowid
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, 9, 'Persistent')", (ans_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_text, answer_id) VALUES (?, 1, 'Q', ?)", (sess_id, ans_id))
        self.conn.commit()
        self.conn.close()

        new_conn = sqlite3.connect(self.db_path)
        new_conn.row_factory = sqlite3.Row
        self.conn = new_conn

        replay = get_session_replay(self.conn, sess_id)
        self.assertEqual(replay["session_id"], sess_id)
        self.assertEqual(replay["turns"][0]["answer"]["text"], "Disk persistence")
        self.assertEqual(replay["turns"][0]["evaluation"]["score"], 9)

    # 20. Legacy session tolerance (pre-Phase 11/12/13 sessions)
    def test_replay_legacy_session_tolerance(self):
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (category, difficulty, status)
            VALUES ('Python', 'medium', 'completed')
        """)
        sess_id = cur.lastrowid
        self.conn.execute("""
            INSERT INTO session_turns (session_id, turn_number, question_text, is_follow_up)
            VALUES (?, 1, 'Legacy Q', 0)
        """, (sess_id,))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        self.assertEqual(replay["session_id"], sess_id)
        self.assertEqual(replay["configuration"]["experience_level"], "mid")
        self.assertEqual(replay["configuration"]["interviewer_style"], "professional")
        self.assertIsNone(replay["context"]["candidate_profile"])
        self.assertIsNone(replay["context"]["job_context"])
        self.assertIsNone(replay["turns"][0]["claim_probe"])

    # 21. Malformed JSON resilience (defensive fallback on corrupt JSON strings)
    def test_replay_malformed_json_resilience(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('completed')")
        sess_id = cur.lastrowid

        ans_id = self.conn.execute("INSERT INTO answers (answer) VALUES ('Ans')").lastrowid
        self.conn.execute("""
            INSERT INTO evaluations (answer_id, score, feedback, strengths, missing_points)
            VALUES (?, 7, 'Feed', '{corrupt json', 'not a list')
        """, (ans_id,))
        self.conn.execute("""
            INSERT INTO speech_analytics (
                answer_id, audio_duration_seconds, speaking_duration_seconds, pause_duration_seconds,
                pause_count, average_pause_duration, long_pause_count, speaking_rate_wpm,
                articulation_rate_wpm, filler_word_count, filler_rate, filler_breakdown,
                repeated_words_count, phonation_ratio, delivery_score, delivery_feedback
            ) VALUES (
                ?, 10.0, 8.0, 2.0, 1, 2.0, 0, 120.0, 130.0, 0, 0.0, 'corrupt', 0, 0.8, 7, 'ok'
            )
        """, (ans_id,))
        self.conn.execute("""
            INSERT INTO nonverbal_analytics (
                answer_id, video_duration_seconds, frames_analyzed, face_detected_ratio,
                centering_offset, motion_energy, camera_quality_flags, nonverbal_telemetry_score,
                nonverbal_feedback, vision_backend
            ) VALUES (
                ?, 10.0, 150, 0.9, 0.0, 1.0, 'corrupt flags', 7, 'ok', 'mediapipe'
            )
        """, (ans_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_text, answer_id) VALUES (?, 1, 'Q', ?)", (sess_id, ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        t = replay["turns"][0]
        self.assertEqual(t["evaluation"]["strengths"], [])
        self.assertEqual(t["evaluation"]["missing_points"], [])
        self.assertEqual(t["speech_analytics"]["filler_breakdown"], {})
        self.assertEqual(t["nonverbal_analytics"]["camera_quality_flags"], [])

    # 22. Multi-category session replay and coverage
    def test_replay_multicategory_session_coverage(self):
        cats = ["Python", "Databases", "System Design"]
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (status, selected_categories)
            VALUES ('completed', ?)
        """, (json.dumps(cats),))
        sess_id = cur.lastrowid

        for i, c in enumerate(cats, start=1):
            q_id = self.conn.execute("INSERT INTO questions (category, difficulty, question) VALUES (?, 'medium', ?)", (c, f"Q in {c}")).lastrowid
            ans_id = self.conn.execute("INSERT INTO answers (question_id, answer) VALUES (?, 'Ans')", (q_id,)).lastrowid
            self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, 8, 'ok')", (ans_id,))
            self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, answer_id) VALUES (?, ?, ?, ?, ?)", (sess_id, i, q_id, f"Q in {c}", ans_id))
        self.conn.commit()

        replay = get_session_replay(self.conn, sess_id)
        self.assertEqual(replay["configuration"]["selected_categories"], cats)
        self.assertEqual(len(replay["turns"]), 3)
        turn_cats = [t["category"] for t in replay["turns"]]
        self.assertEqual(turn_cats, cats)
        self.assertEqual(replay["summary"]["categories_covered"], 3)
        self.assertIn("Python", replay["summary"]["difficulty_progression"])
        self.assertIn("Databases", replay["summary"]["difficulty_progression"])


if __name__ == "__main__":
    unittest.main()
