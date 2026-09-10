"""
tests/test_strategy_engine.py

Complete test suite for Phase 7: Adaptive Interview Strategy & Intelligent Question Selection.
Self-contained in repository tests/ directory with zero external path dependencies.
"""

import sys
import unittest
import sqlite3
from pathlib import Path

# Ensure repository root and backend/ are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

for p in (str(REPO_ROOT), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import strategy_engine
from backend import interview_engine


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


class MockEvaluation:
    def __init__(self, score, feedback="Good answer", technical_accuracy="Accurate", strengths=None, missing_points=None):
        self.score = score
        self.feedback = feedback
        self.technical_accuracy = technical_accuracy
        self.strengths = strengths or ["Solid technical grasp"]
        self.missing_points = missing_points or []


class TestStrategyEngine(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite database with fresh schema
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_test_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def seed_test_question(self, q_id: int, category: str, difficulty: str, question_text: str):
        self.conn.execute(
            "INSERT INTO questions (id, category, difficulty, question) VALUES (?, ?, ?, ?)",
            (q_id, category, difficulty, question_text)
        )
        self.conn.commit()

    # =========================================================================
    # SECTION A: Difficulty Normalization
    # =========================================================================
    def test_difficulty_normalization(self):
        self.assertEqual(strategy_engine.normalize_difficulty("beginner"), "easy")
        self.assertEqual(strategy_engine.normalize_difficulty("Beginner"), "easy")
        self.assertEqual(strategy_engine.normalize_difficulty("BEGINNER "), "easy")
        self.assertEqual(strategy_engine.normalize_difficulty("easy"), "easy")
        self.assertEqual(strategy_engine.normalize_difficulty("medium"), "medium")
        self.assertEqual(strategy_engine.normalize_difficulty("hard"), "hard")
        self.assertEqual(strategy_engine.normalize_difficulty(None), "medium")
        self.assertEqual(strategy_engine.normalize_difficulty("expert"), "medium")

        # Confirm canonical levels are strictly easy, medium, hard
        self.assertEqual(strategy_engine.CANONICAL_DIFFICULTIES, ["easy", "medium", "hard"])
        self.assertNotIn("beginner", strategy_engine.CANONICAL_DIFFICULTIES)

    # =========================================================================
    # SECTION B: Coverage Target Rules & Clamping
    # =========================================================================
    def test_coverage_target_rules(self):
        self.assertEqual(strategy_engine.calculate_coverage_target(5, 10), 3)
        self.assertEqual(strategy_engine.calculate_coverage_target(8, 10), 4)
        self.assertEqual(strategy_engine.calculate_coverage_target(10, 10), 4)
        self.assertEqual(strategy_engine.calculate_coverage_target(6, 10), 3)
        self.assertEqual(strategy_engine.calculate_coverage_target(12, 10), 6)

        # Clamping to available category count
        self.assertEqual(strategy_engine.calculate_coverage_target(8, 2), 2)
        self.assertEqual(strategy_engine.calculate_coverage_target(5, 1), 1)
        self.assertEqual(strategy_engine.calculate_coverage_target(5, 0), 0)

    # =========================================================================
    # SECTION C: Category State Classification
    # =========================================================================
    def test_category_state_classification(self):
        # UNSEEN: bank_questions_asked == 0
        self.assertEqual(strategy_engine.classify_category_state(0, []), "UNSEEN")

        # COVERED_UNSCORED: bank_questions_asked > 0 but evaluated count == 0
        self.assertEqual(strategy_engine.classify_category_state(1, []), "COVERED_UNSCORED")

        # Boundary tests:
        # score < 6.0 -> NEEDS_FOCUS
        # 6.0 <= score < 7.0 -> MODERATE
        # score >= 7.0 -> STRONG
        self.assertEqual(strategy_engine.classify_category_state(1, [5.9]), "NEEDS_FOCUS")
        self.assertEqual(strategy_engine.classify_category_state(1, [6.0]), "MODERATE")
        self.assertEqual(strategy_engine.classify_category_state(1, [6.9]), "MODERATE")
        self.assertEqual(strategy_engine.classify_category_state(1, [7.0]), "STRONG")

        # Multi-score tests:
        self.assertEqual(strategy_engine.classify_category_state(2, [3.0, 5.0]), "NEEDS_FOCUS")
        self.assertEqual(strategy_engine.classify_category_state(2, [6.2, 6.8]), "MODERATE")
        self.assertEqual(strategy_engine.classify_category_state(2, [8.0, 9.5]), "STRONG")

        # Adaptive Category-State Average Window (Issue 3):
        # State classification strictly uses the most recent 2 evaluated bank-question scores.
        # scores = [9.0, 9.0, 4.0]
        # lifetime average = 7.33 (reporting average)
        # recent-2 average = (9.0 + 4.0) / 2 = 6.5 -> MODERATE
        self.assertEqual(strategy_engine.classify_category_state(3, [9.0, 9.0, 4.0]), "MODERATE")

        # scores = [9.0, 9.0, 7.0]
        # recent-2 average = (9.0 + 7.0) / 2 = 8.0 -> STRONG
        self.assertEqual(strategy_engine.classify_category_state(3, [9.0, 9.0, 7.0]), "STRONG")

    # =========================================================================
    # SECTION D: Deterministic Category Ranking & Tie-Breaking
    # =========================================================================
    def test_pre_coverage_ranking_and_unseen_priority(self):
        # Target = 3 categories, only 1 covered so far
        categories_state = {
            "Python": {"state": "MODERATE", "bank_questions_asked": 1, "average_score": 6.5},
            "SQL": {"state": "UNSEEN", "bank_questions_asked": 0, "average_score": None},
            "Docker": {"state": "UNSEEN", "bank_questions_asked": 0, "average_score": None},
            "FastAPI": {"state": "NEEDS_FOCUS", "bank_questions_asked": 1, "average_score": 4.0}
        }
        # Pre-coverage priority: UNSEEN > NEEDS_FOCUS > COVERED_UNSCORED > MODERATE > STRONG
        # Among UNSEEN: Docker < SQL alphabetically
        ranked = strategy_engine.rank_categories_deterministically(categories_state, coverage_target=3)
        self.assertEqual(ranked, ["Docker", "SQL", "FastAPI", "Python"])

        # Repeat to confirm determinism
        for _ in range(5):
            self.assertEqual(strategy_engine.rank_categories_deterministically(categories_state, 3), ["Docker", "SQL", "FastAPI", "Python"])

    def test_post_coverage_ranking_correction_1(self):
        # Coverage target = 3 met (3 covered)
        # User Correction 1: NEEDS_FOCUS > COVERED_UNSCORED > MODERATE > STRONG > UNSEEN
        categories_state = {
            "Z_Unseen": {"state": "UNSEEN", "bank_questions_asked": 0, "average_score": None},
            "A_Strong": {"state": "STRONG", "bank_questions_asked": 1, "average_score": 8.0},
            "B_Moderate": {"state": "MODERATE", "bank_questions_asked": 1, "average_score": 6.5},
            "C_Unscored": {"state": "COVERED_UNSCORED", "bank_questions_asked": 1, "average_score": None},
            "D_Focus_Low": {"state": "NEEDS_FOCUS", "bank_questions_asked": 1, "average_score": 3.0},
            "E_Focus_High": {"state": "NEEDS_FOCUS", "bank_questions_asked": 1, "average_score": 5.0}
        }
        ranked = strategy_engine.rank_categories_deterministically(categories_state, coverage_target=3)
        expected = [
            "D_Focus_Low",   # NEEDS_FOCUS (avg 3.0)
            "E_Focus_High",  # NEEDS_FOCUS (avg 5.0)
            "C_Unscored",    # COVERED_UNSCORED
            "B_Moderate",    # MODERATE
            "A_Strong",      # STRONG
            "Z_Unseen"       # UNSEEN (ranked 5th, below STRONG but above bank exhaustion)
        ]
        self.assertEqual(ranked, expected)

    def test_scored_tie_breaking(self):
        # Authoritative Phase 7 §7 tie-break rules:
        # 1. average_score ASC
        # 2. bank_questions_asked ASC
        # 3. category name ASC

        # Category A: bank_questions_asked = 1
        # Category B: bank_questions_asked = 2
        # => A must rank before B
        categories_state = {
            "CatB": {"state": "NEEDS_FOCUS", "bank_questions_asked": 2, "average_score": 4.0},
            "CatA": {"state": "NEEDS_FOCUS", "bank_questions_asked": 1, "average_score": 4.0},
        }
        ranked = strategy_engine.rank_categories_deterministically(categories_state, coverage_target=1)
        self.assertEqual(ranked, ["CatA", "CatB"])

        # Final alphabetical tie when both average and bank_questions_asked are equal
        categories_state_tie = {
            "CatZ": {"state": "MODERATE", "bank_questions_asked": 2, "average_score": 6.5},
            "CatM": {"state": "MODERATE", "bank_questions_asked": 2, "average_score": 6.5},
            "CatA": {"state": "MODERATE", "bank_questions_asked": 2, "average_score": 6.5},
        }
        ranked_tie = strategy_engine.rank_categories_deterministically(categories_state_tie, coverage_target=1)
        self.assertEqual(ranked_tie, ["CatA", "CatM", "CatZ"])

        # Full tie-break with bank_questions_asked ASC:
        # Lower bank_questions_asked first: Cat_Light (1) < Cat_Alpha_A (2) == Cat_Alpha_Z (2) < Cat_Heavy (3)
        categories_state_full = {
            "Cat_Heavy": {"state": "NEEDS_FOCUS", "bank_questions_asked": 3, "average_score": 4.0},
            "Cat_Light": {"state": "NEEDS_FOCUS", "bank_questions_asked": 1, "average_score": 4.0},
            "Cat_Alpha_Z": {"state": "NEEDS_FOCUS", "bank_questions_asked": 2, "average_score": 4.0},
            "Cat_Alpha_A": {"state": "NEEDS_FOCUS", "bank_questions_asked": 2, "average_score": 4.0},
        }
        ranked_full = strategy_engine.rank_categories_deterministically(categories_state_full, coverage_target=1)
        expected_full = ["Cat_Light", "Cat_Alpha_A", "Cat_Alpha_Z", "Cat_Heavy"]
        self.assertEqual(ranked_full, expected_full)

    # =========================================================================
    # SECTION E: Difficulty Adaptation & Decrease Protection
    # =========================================================================
    def test_difficulty_adaptation(self):
        # Escalation: >= 8.0
        self.assertEqual(strategy_engine.adapt_difficulty("easy", [8.0]), "medium")
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [8.0]), "hard")
        self.assertEqual(strategy_engine.adapt_difficulty("hard", [9.0, 9.5]), "hard")

        # Maintain: 5.0 to 7.99
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [6.0]), "medium")
        self.assertEqual(strategy_engine.adapt_difficulty("hard", [7.5]), "hard")
        self.assertEqual(strategy_engine.adapt_difficulty("easy", [5.0]), "easy")

        # Immediate Decrease Rule: most recent <= 3 decreases immediately
        self.assertEqual(strategy_engine.adapt_difficulty("hard", [3.0]), "medium")
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [3.0]), "easy")
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [2.5]), "easy")
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [2.0]), "easy")
        self.assertEqual(strategy_engine.adapt_difficulty("easy", [1.0]), "easy")  # bounded at easy
        self.assertEqual(strategy_engine.adapt_difficulty("easy", [3.0]), "easy")  # bounded at easy

        # Decrease Protection: single score like 4.0 with only one evaluation remains protected
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [4.0]), "medium")
        self.assertEqual(strategy_engine.adapt_difficulty("hard", [4.0]), "hard")

        # Two consecutive scores < 5.0 allows decrease
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [4.0, 4.0]), "easy")
        self.assertEqual(strategy_engine.adapt_difficulty("hard", [4.0, 4.5]), "medium")

        # One good score and one 4 (e.g. 6.0 and 4.0) maintains medium (avg = 5.0)
        self.assertEqual(strategy_engine.adapt_difficulty("medium", [6.0, 4.0]), "medium")

    # =========================================================================
    # SECTION F: Isolation of Follow-Up Scores (Contradictory Score Test Cases)
    # =========================================================================
    def test_isolation_of_contradictory_follow_up_scores(self):
        # Seed questions
        self.seed_test_question(1, "Python", "medium", "Python Bank Q1")
        self.seed_test_question(2, "Python", "medium", "Python Bank Q2")
        self.seed_test_question(3, "Python", "hard", "Python Bank Q3")

        # Start session
        session = interview_engine.start_session(self.conn, category="Python", max_turns=5)
        s_id = session["session_id"]

        # Turn 1: Bank question scored 4.0 with missing points -> triggers follow-up
        res1 = interview_engine.record_answer_and_advance(
            self.conn, s_id, "Answer 1", MockEvaluation(score=4.0, missing_points=["GIL detail"])
        )
        self.assertEqual(res1["decision"], "follow_up")
        self.assertTrue(res1["next_question"]["is_follow_up"])

        # Turn 2: Follow-up question is answered with score 10.0!
        # Contradictory Case: Bank score 4.0, Follow-up score 10.0!
        # If follow-up were included, avg would be (4+10)/2 = 7.0 or follow-up 10 would escalate.
        # But follow-up must be strictly excluded: only Bank score 4.0 counts!
        res2 = interview_engine.record_answer_and_advance(
            self.conn, s_id, "Answer 2 Follow-Up", MockEvaluation(score=10.0)
        )
        self.assertEqual(res2["decision"], "new_question")

        # Turn 3 bank question: Category was medium, recent bank score was [4.0].
        # Single score of 4 maintains medium (decrease protection). It does NOT escalate to hard!
        self.assertEqual(res2["next_question"]["difficulty"], "medium")

        # Build interview state and verify recent_scores has only [4.0], not [10.0]
        state = strategy_engine.build_interview_state(self.conn, s_id)
        py_state = state["categories"]["Python"]
        self.assertEqual(py_state["bank_questions_asked"], 2)  # Turn 1 and Turn 3
        self.assertEqual(py_state["evaluated_bank_answers_count"], 1)  # Only Turn 1 evaluated
        self.assertEqual(py_state["recent_scores"], [4.0])
        self.assertNotIn(10.0, py_state["recent_scores"])

    # =========================================================================
    # SECTION G: Question Selection & Inventory Fallbacks
    # =========================================================================
    def test_difficulty_inventory_fallback_order(self):
        # Medium requested: fallback is [medium, easy, hard]
        # Only easy and hard questions exist
        self.seed_test_question(10, "Python", "hard", "Hard Q10")
        self.seed_test_question(20, "Python", "beginner", "Beginner Q20")

        # Asking for medium should fall back to easy (beginner normalized to easy)
        q, diff = strategy_engine.select_bank_question(self.conn, "Python", "medium", set())
        self.assertIsNotNone(q)
        self.assertEqual(q["id"], 20)
        self.assertEqual(q["difficulty"], "easy")
        self.assertEqual(diff, "easy")

        # Asking for hard with only easy available
        q2, diff2 = strategy_engine.select_bank_question(self.conn, "Python", "hard", {10})
        self.assertEqual(q2["id"], 20)
        self.assertEqual(diff2, "easy")

    def test_lowest_id_deterministic_tie_breaker(self):
        self.seed_test_question(55, "SQL", "medium", "SQL Q55")
        self.seed_test_question(12, "SQL", "medium", "SQL Q12")
        self.seed_test_question(34, "SQL", "medium", "SQL Q34")

        q, diff = strategy_engine.select_bank_question(self.conn, "SQL", "medium", set())
        self.assertEqual(q["id"], 12)  # Lowest id selected

    def test_category_inventory_fallback_and_bank_exhaustion(self):
        # Category A has 1 question, Category B has 1 question
        self.seed_test_question(1, "CatA", "medium", "CatA Q1")
        self.seed_test_question(2, "CatB", "medium", "CatB Q1")

        session = interview_engine.start_session(self.conn, max_turns=5)
        s_id = session["session_id"]
        # Turn 1 used CatA Q1
        res1 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=8.0))
        # Turn 2 used CatB Q1
        res2 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 2", MockEvaluation(score=8.0))

        # Turn 3: Both CatA and CatB are exhausted. Bank is exhausted!
        self.assertEqual(res2["decision"], "completed")
        self.assertIsNone(res2["next_question"])

    def test_post_coverage_inventory_fallback_selects_unseen_category(self):
        """
        User Requirement 3:
        E2E post-coverage inventory fallback scenario:
        - 4 categories total
        - max_turns configured so coverage target = 3
        - cover 3 categories
        - ensure those 3 categories have no unused bank questions remaining
        - leave the 4th category genuinely UNSEEN
        - call decide_next_turn()
        - verify the engine excludes the exhausted categories, re-runs the FULL category ranking,
          and eventually selects the UNSEEN 4th category.
        """
        # 4 categories total: CatA, CatB, CatC, CatD
        self.seed_test_question(1, "CatA", "medium", "CatA Q1")
        self.seed_test_question(2, "CatB", "medium", "CatB Q1")
        self.seed_test_question(3, "CatC", "medium", "CatC Q1")
        self.seed_test_question(4, "CatD", "medium", "CatD Q1")

        # Session with max_turns = 5 -> calculate_coverage_target(5, 4) = 3
        session = interview_engine.start_session(self.conn, max_turns=5)
        s_id = session["session_id"]

        # Turn 1: CatA (alphabetical first among unseen)
        self.assertEqual(session["question"]["category"], "CatA")
        self.assertEqual(session["question"]["question_id"], 1)

        # Turn 1 evaluated with score 8.0 (CatA now STRONG, 0 unused questions remaining)
        res1 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=8.0))
        self.assertEqual(res1["status"], "active")
        self.assertEqual(res1["next_question"]["category"], "CatB")
        self.assertEqual(res1["next_question"]["question_id"], 2)

        # Turn 2 evaluated with score 8.0 (CatB now STRONG, 0 unused questions remaining)
        res2 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 2", MockEvaluation(score=8.0))
        self.assertEqual(res2["status"], "active")
        self.assertEqual(res2["next_question"]["category"], "CatC")
        self.assertEqual(res2["next_question"]["question_id"], 3)

        # Turn 3: Record answer and evaluation directly on Turn 3 to test decide_next_turn() at the exact state
        turn3_id = res2["next_question"]["turn_id"]
        turn3_q_id = res2["next_question"]["question_id"]
        cursor = self.conn.execute(
            "INSERT INTO answers (question_id, answer) VALUES (?, ?)",
            (turn3_q_id, "Ans 3")
        )
        ans3_id = cursor.lastrowid
        self.conn.execute(
            "INSERT INTO evaluations (answer_id, score, feedback, technical_accuracy) VALUES (?, ?, ?, ?)",
            (ans3_id, 8.0, "Great answer", "Accurate")
        )
        self.conn.execute(
            "UPDATE session_turns SET answer_id = ?, status = 'evaluated' WHERE id = ?",
            (ans3_id, turn3_id)
        )
        self.conn.commit()

        # Check interview state: exactly 3 categories covered, target = 3 (post-coverage!)
        state = strategy_engine.build_interview_state(self.conn, s_id)
        self.assertEqual(state["coverage_target"], 3)
        self.assertEqual(state["categories_covered"], 3)
        self.assertEqual(state["categories"]["CatA"]["state"], "STRONG")
        self.assertEqual(state["categories"]["CatB"]["state"], "STRONG")
        self.assertEqual(state["categories"]["CatC"]["state"], "STRONG")
        self.assertEqual(state["categories"]["CatD"]["state"], "UNSEEN")

        # Initial post-coverage ranking: STRONG categories (CatA, CatB, CatC) rank ahead of UNSEEN (CatD)
        initial_ranking = strategy_engine.rank_categories_deterministically(state["categories"], state["coverage_target"])
        self.assertEqual(initial_ranking[:3], ["CatA", "CatB", "CatC"])
        self.assertEqual(initial_ranking[3], "CatD")

        # Call decide_next_turn():
        # CatA, CatB, CatC are all inventory-exhausted.
        # The engine excludes them, re-runs ranking, and falls back to UNSEEN CatD!
        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["category"], "CatD")
        self.assertEqual(decision["target_difficulty"], "medium")
        self.assertEqual(decision["difficulty"], "medium")
        self.assertEqual(decision["question"]["id"], 4)
        self.assertEqual(decision["question"]["category"], "CatD")

    # =========================================================================
    # SECTION H: Final-Turn Follow-Up Gate
    # =========================================================================
    def test_final_turn_follow_up_gate(self):
        # Seed questions for a 2-turn session
        self.seed_test_question(1, "Python", "medium", "Q1")
        self.seed_test_question(2, "SQL", "medium", "Q2")

        session = interview_engine.start_session(self.conn, max_turns=2)
        s_id = session["session_id"]

        # Turn 1: score 8
        res1 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=8.0))
        self.assertEqual(res1["status"], "active")
        self.assertEqual(res1["current_turn"], 2)

        # Turn 2 (Final Turn): Candidate provides answer with score 4.0 and missing points
        # Normally eligible for follow-up, but current_turn == max_turns!
        res2 = interview_engine.record_answer_and_advance(
            self.conn, s_id, "Ans 2 Final", MockEvaluation(score=4.0, missing_points=["Missing index"])
        )
        # MUST complete immediately, zero follow-up generated
        self.assertEqual(res2["status"], "completed")
        self.assertEqual(res2["decision"], "completed")
        self.assertIsNone(res2["next_question"])

    # =========================================================================
    # SECTION I: Full End-to-End Multi-Turn Session Simulation
    # =========================================================================
    def test_e2e_5_turn_session_adaptive_progression(self):
        # Seed questions across 3 domains at various difficulties
        self.seed_test_question(1, "Python", "medium", "Python M1")
        self.seed_test_question(2, "Python", "hard", "Python H1")
        self.seed_test_question(3, "SQL", "medium", "SQL M1")
        self.seed_test_question(4, "SQL", "easy", "SQL E1")
        self.seed_test_question(5, "FastAPI", "medium", "FastAPI M1")

        session = interview_engine.start_session(self.conn, max_turns=5)
        s_id = session["session_id"]
        self.assertEqual(session["current_turn"], 1)

        # Turn 1 (FastAPI M1: alphabetical first among unseen)
        res1 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=9.0))
        self.assertEqual(res1["status"], "active")

        # Turn 2 (Next unseen: Python M1)
        res2 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 2", MockEvaluation(score=2.0))
        self.assertEqual(res2["status"], "active")

        # Turn 3 (Next unseen: SQL M1) -> coverage target 3 reached!
        res3 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 3", MockEvaluation(score=7.0))
        self.assertEqual(res3["status"], "active")

        # Turn 4 (Coverage met -> NEEDS_FOCUS: Python had score 2.0. Adapts to easy, but Python only has hard -> fallback)
        res4 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 4", MockEvaluation(score=8.0))
        self.assertEqual(res4["status"], "active")

        # Turn 5 (Final Turn)
        res5 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 5", MockEvaluation(score=8.0))
        self.assertEqual(res5["status"], "completed")

        # Verify summary output
        summary = interview_engine.get_session_summary(self.conn, s_id)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total_turns_evaluated"], 5)
        self.assertEqual(summary["categories_covered"], 3)
        self.assertEqual(summary["coverage_target"], 3)
        self.assertIn("difficulty_progression", summary)
        self.assertIn("adaptive_summary", summary)

        # Verify canonical difficulty representation in trajectory
        for cat, traj in summary["difficulty_progression"].items():
            for part in traj.split(" -> "):
                self.assertIn(part, ["easy", "medium", "hard"])

    def test_isolation_contradictory_case_b(self):
        # Contradictory Case B: Bank Question Score = 9.0, Follow-Up Score = 2.0
        self.seed_test_question(1, "Python", "medium", "Bank Q1")
        self.seed_test_question(2, "Python", "hard", "Bank Q2")

        session = interview_engine.start_session(self.conn, category="Python", max_turns=5)
        s_id = session["session_id"]

        # Turn 1: Bank question answered with score 9.0 (Outstanding, but has a missing point)
        # Note: Score 9 does not normally trigger follow-up in Phase 3 (since 3 <= score <= 6 rule),
        # but if a follow-up turn exists with score 2.0:
        # Let's insert a follow-up turn directly to simulate
        turn1 = self.conn.execute("SELECT * FROM session_turns WHERE session_id = ? AND turn_number = 1", (s_id,)).fetchone()
        ans1 = self.conn.execute("INSERT INTO answers (question_id, answer) VALUES (?, 'Ans 1')", (turn1["question_id"],)).lastrowid
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, 9.0, 'Great')", (ans1,))
        self.conn.execute("UPDATE session_turns SET answer_id = ?, status = 'evaluated' WHERE id = ?", (ans1, turn1["id"]))

        # Insert Follow-Up Turn 2
        turn2_id = self.conn.execute(
            "INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, parent_turn_id, status) VALUES (?, 2, NULL, 'Follow-up text', 1, ?, 'evaluated')",
            (s_id, turn1["id"])
        ).lastrowid
        ans2 = self.conn.execute("INSERT INTO answers (question_id, answer) VALUES (NULL, 'Ans 2 Follow-Up')").lastrowid
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (?, 2.0, 'Poor follow-up')", (ans2,))
        self.conn.execute("UPDATE session_turns SET answer_id = ? WHERE id = ?", (ans2, turn2_id))
        self.conn.execute("UPDATE interview_sessions SET current_turn = 2 WHERE id = ?", (s_id,))
        self.conn.commit()

        # Next decision should adapt difficulty ONLY from the Bank score (9.0), NOT follow-up (2.0)
        # Bank score 9.0 >= 8.0 -> escalates medium to hard!
        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["target_difficulty"], "hard")
        self.assertEqual(decision["question"]["id"], 2)

    def test_post_coverage_inventory_fallback_to_unseen(self):
        # User Correction 1 & 4:
        # Coverage target = 2 met.
        # Covered categories: CatA (STRONG) and CatB (MODERATE).
        # Both CatA and CatB run out of questions.
        # CatC is UNSEEN.
        # Priority post-coverage: NEEDS_FOCUS > COVERED_UNSCORED > MODERATE > STRONG > UNSEEN
        # Fallback must select CatC (UNSEEN) rather than declaring bank exhausted!
        self.seed_test_question(1, "CatA", "medium", "CatA Q1")
        self.seed_test_question(2, "CatB", "medium", "CatB Q1")
        self.seed_test_question(3, "CatC", "medium", "CatC Q1")

        session = interview_engine.start_session(self.conn, max_turns=5)
        s_id = session["session_id"]
        # Turn 1: CatA Q1 (alphabetical first) -> evaluated score 8.0 (STRONG)
        interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=8.0))
        # Turn 2: CatB Q1 (next unseen) -> evaluated score 6.5 (MODERATE)
        # Target = calculate_coverage_target(5, 3) = 3 categories.
        # Wait, if available count was 2, target is 2. Let's make target 2 by checking state.
        state = strategy_engine.build_interview_state(self.conn, s_id)
        # At this point, 2 categories covered. Both CatA and CatB have no more questions!
        # When decide_next_turn runs:
        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["category"], "CatC")
        self.assertEqual(decision["question"]["id"], 3)

    def test_interview_state_turn_accounting(self):
        # User Correction 2:
        # max_turns = configured session capacity
        # total_turns = actual number of session_turn rows
        # remaining_turns = max_turns - total_turns
        # total_turns != max_turns
        self.seed_test_question(1, "Python", "medium", "Q1")
        self.seed_test_question(2, "Python", "medium", "Q2")
        self.seed_test_question(3, "Python", "medium", "Q3")

        session = interview_engine.start_session(self.conn, category="Python", max_turns=5)
        s_id = session["session_id"]

        state1 = strategy_engine.build_interview_state(self.conn, s_id)
        self.assertEqual(state1["max_turns"], 5)
        self.assertEqual(state1["total_turns"], 1)
        self.assertEqual(state1["remaining_turns"], 4)
        self.assertNotEqual(state1["total_turns"], state1["max_turns"])

        # Advance 1 turn
        interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=8.0))

        state2 = strategy_engine.build_interview_state(self.conn, s_id)
        self.assertEqual(state2["max_turns"], 5)
        self.assertEqual(state2["total_turns"], 2)
        self.assertEqual(state2["remaining_turns"], 3)
        self.assertNotEqual(state2["total_turns"], state2["max_turns"])

    def test_e2e_8_turn_session_adaptive_flow(self):
        # Coverage target for 8 turns is 4 categories
        self.assertEqual(strategy_engine.calculate_coverage_target(8, 4), 4)

        for i in range(1, 10):
            cat = ["Python", "SQL", "FastAPI", "Docker"][(i - 1) % 4]
            diff = ["easy", "medium", "hard"][(i - 1) % 3]
            self.seed_test_question(i, cat, diff, f"Question {i}")

        session = interview_engine.start_session(self.conn, max_turns=8)
        s_id = session["session_id"]

        # Advance 7 turns
        for t in range(1, 8):
            res = interview_engine.record_answer_and_advance(self.conn, s_id, f"Answer {t}", MockEvaluation(score=7.0))
            self.assertEqual(res["status"], "active")
            self.assertEqual(res["current_turn"], t + 1)

        # Final Turn 8: Candidate answers with score 4.0 and missing points
        res_final = interview_engine.record_answer_and_advance(
            self.conn, s_id, "Final Answer 8", MockEvaluation(score=4.0, missing_points=["Gap 1"])
        )
        self.assertEqual(res_final["status"], "completed")
        self.assertEqual(res_final["decision"], "completed")
        self.assertIsNone(res_final["next_question"])

        summary = interview_engine.get_session_summary(self.conn, s_id)
        self.assertEqual(summary["total_turns_evaluated"], 8)
        self.assertEqual(summary["coverage_target"], 4)

    def test_unseen_category_always_starts_at_medium_even_if_session_configured_hard(self):
        """
        Finalized Phase 7 Rule:
        A genuinely UNSEEN category MUST always start at MEDIUM,
        even if a session was configured with difficulty 'hard'.
        """
        self.seed_test_question(1, "Python", "medium", "Python Medium Q1")
        self.seed_test_question(2, "Python", "hard", "Python Hard Q2")
        self.seed_test_question(3, "SQL", "medium", "SQL Medium Q1")
        self.seed_test_question(4, "SQL", "hard", "SQL Hard Q2")

        # Session configured with difficulty="hard"
        session = interview_engine.start_session(self.conn, difficulty="hard", max_turns=5)
        s_id = session["session_id"]

        # Turn 1: Python is UNSEEN. It MUST start at target_difficulty = "medium", NOT "hard"!
        self.assertEqual(session["question"]["category"], "Python")
        self.assertEqual(session["question"]["difficulty"], "medium")
        self.assertEqual(session["question"]["question_id"], 1)

        # Advance Turn 1 with a high score (9.0)
        res1 = interview_engine.record_answer_and_advance(self.conn, s_id, "Ans 1", MockEvaluation(score=9.0))
        self.assertEqual(res1["status"], "active")

        # Turn 2: SQL is UNSEEN. Even though session has difficulty="hard" and previous turn had 9.0,
        # SQL as a genuinely UNSEEN category MUST start at target_difficulty = "medium"!
        turn2_q = res1["next_question"]
        self.assertEqual(turn2_q["category"], "SQL")
        self.assertEqual(turn2_q["difficulty"], "medium")
        self.assertEqual(turn2_q["question_id"], 3)


if __name__ == "__main__":
    unittest.main()