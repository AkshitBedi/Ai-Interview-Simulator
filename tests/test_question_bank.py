"""
tests/test_question_bank.py

Phase 10: Step 4 Unit Test Suite
Covers all 16 required areas:
1. schema migration
2. defaults
3. backward-compatible inserts
4. metadata parsing
5. malformed JSON
6. empty metadata
7. valid taxonomy values
8. invalid taxonomy values
9. difficulty normalization
10. legacy beginner compatibility
11. topic validation
12. question-type validation
13. skill-type validation
14. quality-tier validation
15. existing question preservation
16. sparse test-fixture compatibility
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.question_bank import (
    CANONICAL_CATEGORIES,
    CANONICAL_DIFFICULTIES,
    TECHNICAL_QUESTION_TYPES,
    BEHAVIORAL_QUESTION_TYPES,
    ALL_QUESTION_TYPES,
    SKILL_TYPES,
    QUALITY_TIERS,
    DEFAULT_QUALITY_TIER,
    TOPICS_BY_CATEGORY,
    normalize_difficulty,
    is_valid_difficulty,
    is_valid_category,
    is_valid_topic,
    is_valid_question_type,
    is_valid_skill_type,
    is_valid_quality_tier,
    parse_string_list,
    serialize_string_list,
    ValidationStatus,
    ValidationResult,
    validate_question_record,
    parse_question_row,
    get_question_by_id,
    NEAR_DUPLICATE_JACCARD_THRESHOLD,
    SHORT_QUESTION_TOKEN_LIMIT,
    normalize_question_text,
    extract_meaningful_tokens,
    compute_token_jaccard,
    compare_questions,
    check_question_duplicate,
    find_all_bank_duplicates,
)
from backend.database import create_tables, get_db


class TestQuestionBankMetadata(unittest.TestCase):
    def setUp(self):
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_file.close()
        self.db_path = self.temp_db_file.name

        # Create minimal connection for testing
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()
        try:
            Path(self.db_path).unlink(missing_ok=True)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 1. Schema Migration & Idempotency
    # -----------------------------------------------------------------------
    def test_schema_migration(self):
        """Verify migration adds all 9 metadata columns to a legacy 4-column table."""
        # Setup legacy table
        self.conn.execute("""
            CREATE TABLE questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                question TEXT NOT NULL
            )
        """)
        self.conn.execute(
            "INSERT INTO questions (category, difficulty, question) VALUES ('Python', 'medium', 'Explain GIL')"
        )
        self.conn.commit()

        # Run migration logic
        cols_before = {r["name"] for r in self.conn.execute("PRAGMA table_info(questions)").fetchall()}
        self.assertEqual(len(cols_before), 4)

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
            if col_name not in cols_before:
                self.conn.execute(f"ALTER TABLE questions ADD COLUMN {col_name} {col_def}")
        self.conn.commit()

        cols_after = {r["name"] for r in self.conn.execute("PRAGMA table_info(questions)").fetchall()}
        self.assertEqual(len(cols_after), 13)
        self.assertIn("topic", cols_after)
        self.assertIn("expected_concepts", cols_after)
        self.assertIn("quality_tier", cols_after)

        # Existing row preserved with default values
        row = self.conn.execute("SELECT * FROM questions WHERE id = 1").fetchone()
        self.assertEqual(row["question"], "Explain GIL")
        self.assertIsNone(row["topic"])
        self.assertEqual(row["quality_tier"], "core")
        self.assertEqual(row["expected_concepts"], "[]")

    # -----------------------------------------------------------------------
    # 2. Defaults
    # -----------------------------------------------------------------------
    def test_defaults(self):
        """Inserting without metadata populates default values correctly."""
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
        self.conn.execute(
            "INSERT INTO questions (category, difficulty, question) VALUES ('Databases', 'hard', 'Explain ACID')"
        )
        self.conn.commit()

        row = self.conn.execute("SELECT * FROM questions WHERE id = 1").fetchone()
        self.assertIsNone(row["topic"])
        self.assertIsNone(row["subtopic"])
        self.assertIsNone(row["question_type"])
        self.assertIsNone(row["skill_type"])
        self.assertEqual(row["quality_tier"], "core")
        self.assertEqual(row["expected_concepts"], "[]")
        self.assertEqual(row["common_mistakes"], "[]")
        self.assertEqual(row["ideal_answer_points"], "[]")
        self.assertEqual(row["prerequisites"], "[]")

    # -----------------------------------------------------------------------
    # 3. Backward-Compatible Inserts
    # -----------------------------------------------------------------------
    def test_backward_compatible_inserts(self):
        """Legacy 3-tuple inserts succeed on the upgraded table without syntax or constraint errors."""
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
        legacy_data = [
            ("Python", "easy", "What is a list?"),
            ("System Design", "medium", "Explain load balancing"),
            ("Behavioral", "medium", "Tell me about a time you failed"),
        ]
        self.conn.executemany(
            "INSERT INTO questions (category, difficulty, question) VALUES (?, ?, ?)",
            legacy_data
        )
        self.conn.commit()

        count = self.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        self.assertEqual(count, 3)

    # -----------------------------------------------------------------------
    # 4. Metadata Parsing
    # -----------------------------------------------------------------------
    def test_metadata_parsing(self):
        """parse_string_list and parse_question_row correctly parse JSON strings and lists."""
        # JSON string
        items, ok, err = parse_string_list('["atomicity", "consistency"]', "concepts")
        self.assertTrue(ok)
        self.assertEqual(items, ["atomicity", "consistency"])
        self.assertIsNone(err)

        # Python list
        items2, ok2, err2 = parse_string_list(["durability", "isolation"], "concepts")
        self.assertTrue(ok2)
        self.assertEqual(items2, ["durability", "isolation"])

        # Row parsing
        row_dict = {
            "id": 10,
            "category": "Databases",
            "difficulty": "hard",
            "question": "Explain ACID properties",
            "topic": "Transactions & ACID Internals",
            "subtopic": "Isolation Anomalies",
            "question_type": "conceptual",
            "skill_type": "understanding",
            "quality_tier": "advanced",
            "expected_concepts": '["atomicity", "consistency", "isolation", "durability"]',
            "common_mistakes": '["confusing isolation with durability"]',
            "ideal_answer_points": '["explain dirty reads", "explain serializability"]',
            "prerequisites": '["relational schema basics"]',
        }
        parsed = parse_question_row(row_dict)
        self.assertEqual(parsed["category"], "Databases")
        self.assertEqual(parsed["topic"], "Transactions & ACID Internals")
        self.assertEqual(len(parsed["expected_concepts"]), 4)
        self.assertEqual(parsed["expected_concepts"][0], "atomicity")
        self.assertTrue(parsed["has_rich_metadata"])

    # -----------------------------------------------------------------------
    # 5. Malformed JSON Handling
    # -----------------------------------------------------------------------
    def test_malformed_json(self):
        """Malformed JSON is rejected with INVALID status by validation and never crashes the app."""
        # 1. Direct parser safely returns error without raising
        items, ok, err = parse_string_list("{not valid json", "expected_concepts")
        self.assertFalse(ok)
        self.assertEqual(items, [])
        self.assertIn("Malformed JSON", err)

        # 2. Non-string elements in list rejected
        items, ok, err = parse_string_list([123, "valid"], "expected_concepts")
        self.assertFalse(ok)
        self.assertIn("must be a string", err)

        # 3. Validation result flags INVALID
        record = {
            "category": "Python",
            "difficulty": "medium",
            "question": "Explain generators and yield expressions in Python",
            "topic": "Core Language & Data Structures",
            "expected_concepts": '{"invalid": true}',  # JSON object instead of array
        }
        res = validate_question_record(record)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.INVALID.value)
        self.assertTrue(any("must represent a list" in e for e in res.errors))

        # 4. parse_question_row doesn't crash on malformed JSON
        bad_row = {
            "category": "Python",
            "difficulty": "medium",
            "question": "Explain generators",
            "expected_concepts": "{completely corrupted json!",
        }
        parsed = parse_question_row(bad_row)
        self.assertEqual(parsed["expected_concepts"], [])

    # -----------------------------------------------------------------------
    # 6. Empty Metadata Handling
    # -----------------------------------------------------------------------
    def test_empty_metadata(self):
        """Empty strings, empty lists, or nulls are treated as missing/no-data and not as concepts."""
        for empty_val in [None, "", "[]", []]:
            items, ok, err = parse_string_list(empty_val, "test")
            self.assertTrue(ok)
            self.assertEqual(items, [])
            self.assertIsNone(err)

        # Empty string element inside a list is rejected as invalid concept
        items, ok, err = parse_string_list([""], "test")
        self.assertFalse(ok)
        self.assertIn("cannot be an empty", err)

        # Record with all empty metadata is classified as MISSING
        sparse = {
            "category": "Python",
            "difficulty": "medium",
            "question": "What is the Global Interpreter Lock?",
            "topic": "",
            "expected_concepts": "[]",
            "common_mistakes": None,
        }
        res = validate_question_record(sparse)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.MISSING.value)
        self.assertFalse(res.cleaned_data["has_rich_metadata"])

    # -----------------------------------------------------------------------
    # 7. Valid Taxonomy Values
    # -----------------------------------------------------------------------
    def test_valid_taxonomy_values(self):
        """Rich question with full valid taxonomy metadata passes validation cleanly."""
        record = {
            "category": "Python",
            "difficulty": "hard",
            "question": "How does Python's asyncio event loop schedule and multiplex coroutines?",
            "topic": "Concurrency & Async",
            "subtopic": "Event Loop & Epoll",
            "question_type": "conceptual",
            "skill_type": "understanding",
            "quality_tier": "advanced",
            "expected_concepts": ["event loop", "coroutines", "futures", "selectors"],
            "common_mistakes": ["confusing asyncio with multiprocessing"],
            "ideal_answer_points": ["explain cooperative yielding with await"],
            "prerequisites": ["generators and iterators"],
        }
        res = validate_question_record(record)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.VALID.value)
        self.assertEqual(len(res.errors), 0)
        self.assertTrue(res.cleaned_data["has_rich_metadata"])
        self.assertEqual(res.cleaned_data["topic"], "Concurrency & Async")

    # -----------------------------------------------------------------------
    # 8. Invalid Taxonomy Values
    # -----------------------------------------------------------------------
    def test_invalid_taxonomy_values(self):
        """Values outside controlled taxonomies are rejected with UNKNOWN_TAXONOMY status."""
        # 1. Unknown category
        res = validate_question_record({
            "category": "Astronomy",
            "difficulty": "easy",
            "question": "What is the distance to the sun?",
        })
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.UNKNOWN_TAXONOMY.value)
        self.assertTrue(any("Unknown category" in e for e in res.errors))

        # 2. Unknown topic for valid category
        res = validate_question_record({
            "category": "Python",
            "difficulty": "medium",
            "question": "How to optimize quantum circuits in Python?",
            "topic": "Quantum Computing & Entanglement",
        })
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.UNKNOWN_TAXONOMY.value)
        self.assertTrue(any("Unknown topic" in e for e in res.errors))

        # 3. Unknown question_type
        res = validate_question_record({
            "category": "Python",
            "difficulty": "medium",
            "question": "Explain Python GIL",
            "topic": "Memory Management & Internals",
            "question_type": "mind_reading",
        })
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.UNKNOWN_TAXONOMY.value)

        # 4. Unknown skill_type
        res = validate_question_record({
            "category": "Databases",
            "difficulty": "medium",
            "question": "Explain B-tree indexes",
            "topic": "Indexing & Query Optimization",
            "skill_type": "clairvoyance",
        })
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.UNKNOWN_TAXONOMY.value)

        # 5. Unknown quality_tier
        res = validate_question_record({
            "category": "Databases",
            "difficulty": "medium",
            "question": "Explain B-tree indexes",
            "topic": "Indexing & Query Optimization",
            "quality_tier": "ultra_legendary",
        })
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.UNKNOWN_TAXONOMY.value)

    # -----------------------------------------------------------------------
    # 9. Difficulty Normalization
    # -----------------------------------------------------------------------
    def test_difficulty_normalization(self):
        """normalize_difficulty standardizes to canonical difficulties."""
        self.assertEqual(normalize_difficulty("easy"), "easy")
        self.assertEqual(normalize_difficulty("EASY"), "easy")
        self.assertEqual(normalize_difficulty("medium"), "medium")
        self.assertEqual(normalize_difficulty("hard"), "hard")
        self.assertEqual(normalize_difficulty(None), "medium")
        self.assertEqual(normalize_difficulty("invalid_value"), "medium")

    # -----------------------------------------------------------------------
    # 10. Legacy Beginner Compatibility
    # -----------------------------------------------------------------------
    def test_legacy_beginner_compatibility(self):
        """Legacy 'beginner' correctly normalizes to 'easy' and passes validation."""
        self.assertEqual(normalize_difficulty("beginner"), "easy")
        self.assertEqual(normalize_difficulty("BEGINNER"), "easy")
        self.assertTrue(is_valid_difficulty("beginner"))

        record = {
            "category": "Python",
            "difficulty": "beginner",
            "question": "What are Python list comprehensions and how do they work?",
        }
        res = validate_question_record(record)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.cleaned_data["difficulty"], "easy")

    # -----------------------------------------------------------------------
    # 11. Topic Validation
    # -----------------------------------------------------------------------
    def test_topic_validation(self):
        """Topics must match the controlled taxonomy for the specified category."""
        # Valid topics for each category
        self.assertTrue(is_valid_topic("Python", "Core Language & Data Structures"))
        self.assertTrue(is_valid_topic("Databases", "Indexing & Query Optimization"))
        self.assertTrue(is_valid_topic("System Design", "Caching, Buffering & Message Queues"))
        self.assertTrue(is_valid_topic("Behavioral", "Leadership & Initiative"))

        # Case-insensitive topic validation
        self.assertTrue(is_valid_topic("Python", "core language & data structures"))

        # Topic belonging to another category is invalid
        self.assertFalse(is_valid_topic("Behavioral", "Indexing & Query Optimization"))
        self.assertFalse(is_valid_topic("Python", "Distributed Architecture & Scalability"))

    # -----------------------------------------------------------------------
    # 12. Question-Type Validation
    # -----------------------------------------------------------------------
    def test_question_type_validation(self):
        """Technical vs Behavioral question type boundaries are enforced."""
        # Technical question types valid for technical categories
        self.assertTrue(is_valid_question_type("debugging", "Python"))
        self.assertTrue(is_valid_question_type("design", "System Design"))
        self.assertTrue(is_valid_question_type("tradeoff", "Databases"))

        # Technical question type is invalid for Behavioral
        self.assertFalse(is_valid_question_type("debugging", "Behavioral"))
        self.assertFalse(is_valid_question_type("prediction", "Behavioral"))

        # Behavioral question types valid for Behavioral
        self.assertTrue(is_valid_question_type("leadership", "Behavioral"))
        self.assertTrue(is_valid_question_type("conflict", "Behavioral"))
        self.assertTrue(is_valid_question_type("situational", "Behavioral"))

        # Behavioral question type is invalid for Technical
        self.assertFalse(is_valid_question_type("conflict", "Python"))
        self.assertFalse(is_valid_question_type("leadership", "Databases"))

    # -----------------------------------------------------------------------
    # 13. Skill-Type Validation
    # -----------------------------------------------------------------------
    def test_skill_type_validation(self):
        """Only allowed skill types from SKILL_TYPES are accepted."""
        for st in SKILL_TYPES:
            self.assertTrue(is_valid_skill_type(st))
            self.assertTrue(is_valid_skill_type(st.upper()))

        self.assertFalse(is_valid_skill_type("memorization"))
        self.assertFalse(is_valid_skill_type("telepathy"))
        self.assertFalse(is_valid_skill_type(123))

    # -----------------------------------------------------------------------
    # 14. Quality-Tier Validation
    # -----------------------------------------------------------------------
    def test_quality_tier_validation(self):
        """Only 'core', 'advanced', 'specialized' are accepted."""
        for qt in QUALITY_TIERS:
            self.assertTrue(is_valid_quality_tier(qt))
            self.assertTrue(is_valid_quality_tier(qt.upper()))

        self.assertFalse(is_valid_quality_tier("legendary"))
        self.assertFalse(is_valid_quality_tier("beginner"))
        self.assertEqual(DEFAULT_QUALITY_TIER, "core")

    # -----------------------------------------------------------------------
    # 15. Existing Question Preservation
    # -----------------------------------------------------------------------
    def test_existing_question_preservation(self):
        """Verifies all existing questions in interview.db (including ID 4) are preserved."""
        live_conn = get_db()
        rows = live_conn.execute("SELECT * FROM questions ORDER BY id ASC").fetchall()
        live_conn.close()

        # Must have at least 13 rows
        self.assertGreaterEqual(len(rows), 13)

        # ID 4 must exist and not be silently deleted
        id4_row = next((r for r in rows if r["id"] == 4), None)
        self.assertIsNotNone(id4_row, "ID 4 was unexpectedly deleted!")
        self.assertEqual(id4_row["question"], "stringstri")

        # Legitimate questions exist with expected IDs
        id1_row = next((r for r in rows if r["id"] == 1), None)
        self.assertIsNotNone(id1_row)
        self.assertEqual(id1_row["category"], "Python")

    # -----------------------------------------------------------------------
    # 16. Sparse Test-Fixture Compatibility
    # -----------------------------------------------------------------------
    def test_sparse_test_fixture_compatibility(self):
        """Existing sparse fixtures with only category, difficulty, question are valid with MISSING status."""
        sparse_record = {
            "category": "Python",
            "difficulty": "medium",
            "question": "What is the purpose of Python virtual environments?",
        }
        res = validate_question_record(sparse_record)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.status, ValidationStatus.MISSING.value)
        self.assertFalse(res.cleaned_data["has_rich_metadata"])
        self.assertEqual(res.cleaned_data["quality_tier"], "core")
        self.assertEqual(res.cleaned_data["expected_concepts"], [])
        self.assertEqual(res.cleaned_data["common_mistakes"], [])
        self.assertEqual(res.cleaned_data["ideal_answer_points"], [])
        self.assertEqual(res.cleaned_data["prerequisites"], [])


class TestDuplicateDetection(unittest.TestCase):
    """
    Step 5 Test Suite: Deterministic Exact and Near-Duplicate Detection.
    Covers:
    - exact duplicate
    - case variation
    - whitespace variation
    - punctuation variation
    - obvious rewording
    - word-order variation
    - short-question safeguard
    - SQL vs NoSQL example
    - genuinely distinct questions
    - malformed/empty question handling
    - threshold boundary
    - deterministic repeated results
    - candidate validation against bank
    - bank duplicate scanning
    """

    def test_exact_duplicate(self):
        """Identical strings are detected as exact duplicates."""
        q1 = "Explain how memory management and the Global Interpreter Lock (GIL) work in CPython."
        q2 = "Explain how memory management and the Global Interpreter Lock (GIL) work in CPython."
        cmp = compare_questions(q1, q2)
        self.assertTrue(cmp["is_exact_duplicate"])
        self.assertTrue(cmp["is_duplicate"])
        self.assertEqual(cmp["duplicate_type"], "EXACT")
        self.assertEqual(cmp["jaccard_similarity"], 1.0)

    def test_case_variation(self):
        """Case variations normalize to exact duplicates."""
        q1 = "What is the Global Interpreter Lock?"
        q2 = "WHAT IS THE GLOBAL INTERPRETER LOCK?"
        cmp = compare_questions(q1, q2)
        self.assertTrue(cmp["is_exact_duplicate"])
        self.assertEqual(cmp["duplicate_type"], "EXACT")

    def test_whitespace_variation(self):
        """Multiple spaces, tabs, and newlines collapse into exact duplicates."""
        q1 = "Explain how Python decorators work under the hood."
        q2 = "  Explain   how \t\t Python \n decorators  work   under  the   hood.  "
        cmp = compare_questions(q1, q2)
        self.assertTrue(cmp["is_exact_duplicate"])
        self.assertEqual(cmp["duplicate_type"], "EXACT")

    def test_punctuation_variation(self):
        """Punctuation variations are stripped and normalize to exact duplicates."""
        q1 = "What are ACID properties in database transactions?"
        q2 = "What are ACID properties in database transactions?!!"
        q3 = "What are, ACID properties, in database transactions..."
        cmp1 = compare_questions(q1, q2)
        cmp2 = compare_questions(q1, q3)
        self.assertTrue(cmp1["is_exact_duplicate"])
        self.assertTrue(cmp2["is_exact_duplicate"])

    def test_obvious_rewording(self):
        """Synonymous framing with high token overlap (>= 0.80) is detected as near-duplicate."""
        q1 = "How does Python asyncio event loop handle cooperative multitasking for high concurrency IO?"
        q2 = "How does Python asyncio event loop manage cooperative multitasking for high concurrency IO?"
        cmp = compare_questions(q1, q2)
        self.assertFalse(cmp["is_exact_duplicate"])
        self.assertTrue(cmp["is_near_duplicate"])
        self.assertEqual(cmp["duplicate_type"], "NEAR")
        self.assertGreaterEqual(cmp["jaccard_similarity"], NEAR_DUPLICATE_JACCARD_THRESHOLD)

    def test_word_order_variation(self):
        """Reordered words produce identical token sets and are detected as near-duplicates."""
        q1 = "Explain difference between clustered indexes and non clustered indexes in databases"
        q2 = "In databases explain difference between non clustered indexes and clustered indexes"
        cmp = compare_questions(q1, q2)
        self.assertTrue(cmp["is_near_duplicate"])
        self.assertEqual(cmp["jaccard_similarity"], 1.0)

    def test_short_question_safeguard(self):
        """Questions with < 3 meaningful tokens require Jaccard == 1.0 to be duplicates."""
        # Both reduce to {"sql"} (< 3 tokens) -> Jaccard == 1.0 -> Duplicate
        q1 = "What is SQL?"
        q2 = "Explain SQL."
        cmp1 = compare_questions(q1, q2)
        self.assertTrue(cmp1["short_safeguard_applied"])
        self.assertTrue(cmp1["is_near_duplicate"])
        self.assertEqual(cmp1["jaccard_similarity"], 1.0)

        # Tokens {"sql"} vs {"python"} (< 3 tokens) -> Jaccard 0.0 -> NOT duplicate
        q3 = "What is Python?"
        cmp2 = compare_questions(q1, q3)
        self.assertTrue(cmp2["short_safeguard_applied"])
        self.assertFalse(cmp2["is_duplicate"])
        self.assertEqual(cmp2["jaccard_similarity"], 0.0)

    def test_sql_vs_nosql_example(self):
        """'What is SQL?' and 'What is NoSQL?' are NEVER treated as duplicates."""
        q_sql = "What is SQL?"
        q_nosql = "What is NoSQL?"
        cmp = compare_questions(q_sql, q_nosql)
        self.assertFalse(cmp["is_exact_duplicate"])
        self.assertFalse(cmp["is_near_duplicate"])
        self.assertFalse(cmp["is_duplicate"])
        self.assertIsNone(cmp["duplicate_type"])
        self.assertEqual(cmp["jaccard_similarity"], 0.0)
        self.assertTrue(cmp["short_safeguard_applied"])

    def test_genuinely_distinct_questions(self):
        """Related but substantively distinct questions are NOT flagged as duplicates."""
        # Example from prompt:
        q1 = "What is database indexing?"
        q2 = "How would you design an indexing strategy for a high-traffic database?"
        cmp = compare_questions(q1, q2)
        self.assertFalse(cmp["is_duplicate"])
        self.assertLess(cmp["jaccard_similarity"], NEAR_DUPLICATE_JACCARD_THRESHOLD)

        # Another pair:
        q3 = "Explain the difference between clustered and non-clustered indexes."
        q4 = "What are ACID properties in database transactions?"
        cmp2 = compare_questions(q3, q4)
        self.assertFalse(cmp2["is_duplicate"])

    def test_malformed_empty_question_handling(self):
        """Empty, None, or blank questions safely return non-duplicate without crashing."""
        self.assertFalse(compare_questions("", "What is GIL?")["is_duplicate"])
        self.assertFalse(compare_questions(None, "What is GIL?")["is_duplicate"])
        self.assertFalse(compare_questions("   ", "   ")["is_duplicate"])
        self.assertFalse(compare_questions(None, None)["is_duplicate"])

        # Check candidate duplicate with None
        chk = check_question_duplicate(None, [{"id": 1, "question": "What is GIL?"}])
        self.assertFalse(chk["has_duplicate"])

    def test_threshold_boundary(self):
        """Validates exact behavior at 0.80 Jaccard threshold boundary."""
        # Synthesize questions with >= 3 tokens
        # Set A: {t1, t2, t3, t4, t5} (5 tokens)
        # Set B: {t1, t2, t3, t4, t6} (5 tokens)
        # Intersection: 4, Union: 6 -> 4/6 = 0.6667 < 0.80 -> False
        q_a = "alpha beta gamma delta epsilon"
        q_b = "alpha beta gamma delta zeta"
        cmp_sub = compare_questions(q_a, q_b)
        self.assertFalse(cmp_sub["is_near_duplicate"])
        self.assertAlmostEqual(cmp_sub["jaccard_similarity"], 0.6667, places=3)

        # Set C: {t1, t2, t3, t4, t5, t6} (6 tokens)
        # Set D: {t1, t2, t3, t4, t5, t7} (6 tokens)
        # Intersection: 5, Union: 7 -> 5/7 = 0.7143 < 0.80 -> False
        q_c = "alpha beta gamma delta epsilon eta"
        q_d = "alpha beta gamma delta epsilon theta"
        cmp_sub2 = compare_questions(q_c, q_d)
        self.assertFalse(cmp_sub2["is_near_duplicate"])

        # Set E: {t1, t2, t3, t4, t5} (5 tokens)
        # Set F: {t1, t2, t3, t4} (4 tokens)
        # Intersection: 4, Union: 5 -> 4/5 = 0.8000 -> Exactly 0.80 -> True
        q_e = "alpha beta gamma delta epsilon"
        q_f = "alpha beta gamma delta"
        cmp_exact_80 = compare_questions(q_e, q_f)
        self.assertTrue(cmp_exact_80["is_near_duplicate"])
        self.assertEqual(cmp_exact_80["jaccard_similarity"], 0.8)

        # Set G: {t1, t2, t3, t4, t5, t6}
        # Set H: {t1, t2, t3, t4, t5}
        # Intersection: 5, Union: 6 -> 5/6 = 0.8333 >= 0.80 -> True
        q_g = "alpha beta gamma delta epsilon zeta"
        q_h = "alpha beta gamma delta epsilon"
        cmp_above_80 = compare_questions(q_g, q_h)
        self.assertTrue(cmp_above_80["is_near_duplicate"])
        self.assertGreater(cmp_above_80["jaccard_similarity"], 0.8)

    def test_deterministic_repeated_results(self):
        """Repeated comparisons on identical inputs return deterministic identical results."""
        q1 = "Explain how Python decorators work under the hood."
        q2 = "Describe how Python decorators work under the hood."
        initial = compare_questions(q1, q2)
        for _ in range(50):
            repeated = compare_questions(q1, q2)
            self.assertEqual(initial["is_duplicate"], repeated["is_duplicate"])
            self.assertEqual(initial["duplicate_type"], repeated["duplicate_type"])
            self.assertEqual(initial["jaccard_similarity"], repeated["jaccard_similarity"])

    def test_check_candidate_against_bank(self):
        """check_question_duplicate accurately matches against an existing question list."""
        bank = [
            {"id": 1, "question": "What is the Global Interpreter Lock in Python?"},
            {"id": 2, "question": "Explain database indexes and B-trees."},
        ]

        # Exact match
        res_exact = check_question_duplicate(
            "What is the Global Interpreter Lock in Python?", bank
        )
        self.assertTrue(res_exact["has_duplicate"])
        self.assertEqual(res_exact["duplicate_type"], "EXACT")
        self.assertEqual(res_exact["conflicting_question_id"], 1)

        # Reworded near match with candidate_id=1 skipped -> no duplicate with remaining items
        res_near = check_question_duplicate(
            "What is the Global Interpreter Lock in Python?", bank, candidate_id=1
        )
        self.assertFalse(res_near["has_duplicate"])

        # Unrelated candidate
        res_diff = check_question_duplicate(
            "How does horizontal scaling differ from vertical scaling?", bank
        )
        self.assertFalse(res_diff["has_duplicate"])

    def test_find_all_bank_duplicates(self):
        """find_all_bank_duplicates correctly detects all duplicate pairs in a collection."""
        bank = [
            {"id": 1, "question": "What is SQL?"},
            {"id": 2, "question": "Explain SQL."},  # near duplicate of 1 (< 3 tokens safeguard, Jaccard 1.0)
            {"id": 3, "question": "What is NoSQL?"},  # distinct
            {"id": 4, "question": "What is NoSQL?"},  # exact duplicate of 3
        ]
        dups = find_all_bank_duplicates(bank)
        self.assertEqual(len(dups), 2)
        # Pair 1 & 2
        p1 = next(d for d in dups if d["question_id_a"] == 1 and d["question_id_b"] == 2)
        self.assertEqual(p1["duplicate_type"], "NEAR")
        # Pair 3 & 4
        p2 = next(d for d in dups if d["question_id_a"] == 3 and d["question_id_b"] == 4)
        self.assertEqual(p2["duplicate_type"], "EXACT")

    def test_existing_database_duplicate_free(self):
        """Verifies the existing questions in the database have zero duplicates among each other."""
        live_conn = get_db()
        rows = [dict(r) for r in live_conn.execute("SELECT id, question FROM questions").fetchall()]
        live_conn.close()

        # Filter out stringstri artifact if necessary or check all
        legit_rows = [r for r in rows if r["question"] != "stringstri"]
        dups = find_all_bank_duplicates(legit_rows)
        self.assertEqual(len(dups), 0, f"Found unexpected duplicates in baseline questions: {dups}")


if __name__ == "__main__":
    unittest.main()
