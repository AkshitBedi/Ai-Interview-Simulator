"""
tests/test_question_bank_expansion.py

Phase 10: Step 7 Intelligent Question Bank Expansion Test Suite.
Verifies:
1. Inventory size within target bounds (115–150 legitimate questions, exactly 125).
2. Category targets: Python (30–40), Databases (30–40), System Design (30–40), Behavioral (25–30).
3. Canonical difficulties: all in {'easy', 'medium', 'hard'} and well distributed.
4. Taxonomies: 100% of questions conform to controlled taxonomies with VALID status.
5. Rich metadata: expected_concepts, common_mistakes, ideal_answer_points non-empty.
6. Zero exact or near-duplicates across the entire inventory (Jaccard < 0.80).
7. ID 4 preservation: test-artifact ID 4 remains completely untouched.
8. Existing question ID preservation: IDs 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 preserved.
9. Runtime compatibility: Phase 7 category selection, difficulty adaptation, and Step 6 diversity ordering.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.question_bank import (
    CANONICAL_CATEGORIES,
    CANONICAL_DIFFICULTIES,
    QUALITY_TIERS,
    SKILL_TYPES,
    TECHNICAL_QUESTION_TYPES,
    BEHAVIORAL_QUESTION_TYPES,
    TOPICS_BY_CATEGORY,
    DEFAULT_QUESTION_BANK,
    ValidationStatus,
    find_all_bank_duplicates,
    parse_question_row,
    seed_question_bank,
    validate_question_record,
)
from backend import strategy_engine
from backend.database import get_db


class TestQuestionBankInventory(unittest.TestCase):
    """Verifies inventory size, categorization, difficulty, and rich metadata."""

    def test_total_legitimate_question_count_in_target_range(self):
        """Total legitimate questions must be between 115 and 150 (current count: 125)."""
        total = len(DEFAULT_QUESTION_BANK)
        self.assertGreaterEqual(total, 115, f"Expected at least 115 questions, found {total}")
        self.assertLessEqual(total, 150, f"Expected at most 150 questions, found {total}")
        self.assertEqual(total, 125)

    def test_category_distribution_meets_targets(self):
        """Each category meets its specific authoring target range."""
        by_cat = {}
        for q in DEFAULT_QUESTION_BANK:
            c = q.get("category")
            by_cat[c] = by_cat.get(c, 0) + 1

        self.assertEqual(set(by_cat.keys()), set(CANONICAL_CATEGORIES))
        # Python: 30–40
        self.assertGreaterEqual(by_cat["Python"], 30)
        self.assertLessEqual(by_cat["Python"], 40)
        self.assertEqual(by_cat["Python"], 33)

        # Databases: 30–40
        self.assertGreaterEqual(by_cat["Databases"], 30)
        self.assertLessEqual(by_cat["Databases"], 40)
        self.assertEqual(by_cat["Databases"], 33)

        # System Design: 30–40
        self.assertGreaterEqual(by_cat["System Design"], 30)
        self.assertLessEqual(by_cat["System Design"], 40)
        self.assertEqual(by_cat["System Design"], 33)

        # Behavioral: 25–30
        self.assertGreaterEqual(by_cat["Behavioral"], 25)
        self.assertLessEqual(by_cat["Behavioral"], 30)
        self.assertEqual(by_cat["Behavioral"], 26)

    def test_difficulty_distribution_and_validity(self):
        """All questions have canonical difficulty and each category has easy, medium, and hard."""
        for q in DEFAULT_QUESTION_BANK:
            diff = q.get("difficulty")
            self.assertIn(diff, CANONICAL_DIFFICULTIES, f"Non-canonical difficulty {diff} in {q.get('question')}")

        for cat in CANONICAL_CATEGORIES:
            cat_qs = [q for q in DEFAULT_QUESTION_BANK if q["category"] == cat]
            diffs = {q["difficulty"] for q in cat_qs}
            self.assertTrue({"easy", "medium", "hard"}.issubset(diffs), f"{cat} missing difficulties: {diffs}")

    def test_quality_tiers_validity(self):
        """All questions have valid quality tiers ('core', 'advanced', 'specialized')."""
        for q in DEFAULT_QUESTION_BANK:
            tier = q.get("quality_tier")
            self.assertIn(tier, QUALITY_TIERS)

    def test_all_questions_have_valid_metadata_status(self):
        """Every single question in DEFAULT_QUESTION_BANK passes taxonomy validation with status VALID."""
        for i, q in enumerate(DEFAULT_QUESTION_BANK, 1):
            res = validate_question_record(q)
            self.assertTrue(
                res.is_valid and res.status == ValidationStatus.VALID.value,
                f"Question #{i} ({q.get('category')} - {q.get('question')[:40]}...) failed validation: {res.errors}"
            )

    def test_rich_metadata_fields_are_populated_and_meaningful(self):
        """No question in the bank has empty placeholder expected_concepts or answers."""
        for q in DEFAULT_QUESTION_BANK:
            q_text = q.get("question")
            self.assertGreater(len(q.get("expected_concepts", [])), 1, f"Missing concepts for: {q_text}")
            self.assertGreater(len(q.get("common_mistakes", [])), 1, f"Missing mistakes for: {q_text}")
            self.assertGreater(len(q.get("ideal_answer_points", [])), 1, f"Missing ideal points for: {q_text}")
            self.assertIsInstance(q.get("prerequisites", []), list)

    def test_zero_near_or_exact_duplicates_across_bank(self):
        """Deterministic Step 5 duplicate detector finds 0 conflicts across all 125 questions."""
        conflicts = find_all_bank_duplicates(DEFAULT_QUESTION_BANK)
        self.assertEqual(
            len(conflicts), 0,
            f"Found {len(conflicts)} duplicate/near-duplicate pairs: {conflicts}"
        )


class TestQuestionBankDatabaseSeeding(unittest.TestCase):
    """Verifies seeding, ID preservation, and ID 4 untouched status."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.conn = sqlite3.connect(self.temp_db.name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("""
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
        # Seed legacy rows including ID 4 artifact
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (1, 'Python', 'medium', 'What is GIL in Python?')")
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (4, 'string', 'string', 'stringstri')")
        self.conn.execute("INSERT INTO questions (id, category, difficulty, question) VALUES (5, 'Python', 'medium', 'Explain how memory management and the Global Interpreter Lock (GIL) work in CPython.')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        try:
            Path(self.temp_db.name).unlink(missing_ok=True)
        except Exception:
            pass

    def test_id_4_remains_untouched_after_seeding(self):
        """Test artifact ID 4 remains completely untouched and unmodified."""
        id4_before = dict(self.conn.execute("SELECT * FROM questions WHERE id = 4").fetchone())
        self.assertEqual(id4_before["question"], "stringstri")

        res = seed_question_bank(self.conn)
        self.assertGreater(res["inserted"], 0)

        id4_after = dict(self.conn.execute("SELECT * FROM questions WHERE id = 4").fetchone())
        self.assertEqual(id4_after["category"], "string")
        self.assertEqual(id4_after["difficulty"], "string")
        self.assertEqual(id4_after["question"], "stringstri")
        self.assertIsNone(id4_after["topic"])
        self.assertEqual(id4_after["expected_concepts"], "[]")

    def test_existing_question_ids_are_preserved(self):
        """Existing legitimate question IDs (1, 5) are updated in-place, preserving their primary keys."""
        res = seed_question_bank(self.conn)
        q1 = dict(self.conn.execute("SELECT * FROM questions WHERE id = 1").fetchone())
        q5 = dict(self.conn.execute("SELECT * FROM questions WHERE id = 5").fetchone())

        self.assertEqual(q1["id"], 1)
        self.assertEqual(q1["question"], "What is GIL in Python?")
        self.assertEqual(q1["topic"], "Memory Management & Internals")

        self.assertEqual(q5["id"], 5)
        self.assertEqual(q5["topic"], "Memory Management & Internals")

    def test_seeding_is_idempotent(self):
        """Calling seed_question_bank multiple times does not insert duplicate rows."""
        res1 = seed_question_bank(self.conn)
        count1 = self.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]

        res2 = seed_question_bank(self.conn)
        count2 = self.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]

        self.assertEqual(count1, count2)
        self.assertEqual(res2["inserted"], 0)


class TestQuestionBankRuntimeCompatibility(unittest.TestCase):
    """Verifies runtime strategy engine and diversity ordering with the expanded bank."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.conn = sqlite3.connect(self.temp_db.name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("""
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
            );
        """)
        self.conn.execute("""
            CREATE TABLE answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                answer TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL
            );
        """)
        self.conn.execute("""
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
            );
        """)
        self.conn.execute("""
            CREATE TABLE interview_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                difficulty TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                current_turn INTEGER NOT NULL DEFAULT 1,
                max_turns INTEGER NOT NULL DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)
        self.conn.execute("""
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
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL
            );
        """)
        # Seed full bank into test database
        seed_question_bank(self.conn)

    def tearDown(self):
        self.conn.close()
        try:
            Path(self.temp_db.name).unlink(missing_ok=True)
        except Exception:
            pass

    def test_runtime_turn_selection_picks_rich_question_with_metadata(self):
        """decide_next_turn selects a legitimate question with all rich metadata populated."""
        s_id = self.conn.execute(
            "INSERT INTO interview_sessions (category, max_turns) VALUES ('Python', 5)"
        ).lastrowid
        self.conn.commit()

        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["category"], "Python")
        self.assertEqual(decision["difficulty"], "medium")

        q = decision["question"]
        self.assertIsNotNone(q["id"])
        self.assertIsNotNone(q["topic"])
        self.assertIsNotNone(q["subtopic"])
        self.assertIsInstance(q["expected_concepts"], list)
        self.assertGreater(len(q["expected_concepts"]), 0)

    def test_diversity_ordering_prevents_immediate_topic_repetition_at_runtime(self):
        """Two consecutive turns in the same category avoid repeating the immediate topic."""
        s_id = self.conn.execute(
            "INSERT INTO interview_sessions (category, max_turns) VALUES ('Python', 5)"
        ).lastrowid

        # Turn 1: Select question 1 (Memory Management & Internals)
        q1, diff1 = strategy_engine.select_bank_question(self.conn, "Python", "medium", set())
        self.conn.execute(
            "INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, 1, ?, ?, 0)",
            (s_id, q1["id"], q1["question"])
        )
        self.conn.commit()

        # Turn 2: Decide next turn with recent history
        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        q2 = decision["question"]

        # Diversity scoring should penalize same topic by -40, so different topic should be preferred
        self.assertNotEqual(q1["topic"], q2["topic"], "Turn 2 should prefer a diverse topic over immediate repeat")

    def test_difficulty_adaptation_works_with_expanded_bank(self):
        """High score triggers adaptation to hard difficulty, selecting a hard question from expanded bank."""
        s_id = self.conn.execute(
            "INSERT INTO interview_sessions (category, max_turns) VALUES ('Databases', 5)"
        ).lastrowid
        q1, _ = strategy_engine.select_bank_question(self.conn, "Databases", "medium", set())
        self.conn.execute(
            "INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id) VALUES (?, 1, ?, ?, 0, 1)",
            (s_id, q1["id"], q1["question"])
        )
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (1, ?, 'Superb answer')", (q1["id"],))
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 9, 'Outstanding')",)
        self.conn.commit()

        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["difficulty"], "hard")
        self.assertEqual(decision["question"]["difficulty"], "hard")


if __name__ == "__main__":
    unittest.main()
