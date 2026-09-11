"""
tests/test_diversity_selection.py

Phase 10: Step 6 Diversity-Aware Candidate Ordering Test Suite.
Covers all 24 required test cases and 6 manual verification scenarios:
1. No-history candidates all tie -> ID ASC
2. Same topic gets penalized (-40)
3. Older topic gets smaller penalty than immediate topic (-20 vs -40)
4. Same subtopic among recent 3 gets penalized (-30)
5. Question-type repetition penalty (-15)
6. Skill-type repetition penalty (-10)
7. Concept overlap penalty (up to -20)
8. Empty topic does not match empty topic
9. NULL topic does not match NULL/empty topic
10. Empty concepts produce zero concept penalty
11. Sparse legacy questions remain deterministic
12. Diversity ranking occurs within difficulty tier
13. Scenario A: Medium candidate beats more-diverse easy candidate (tier never skipped)
14. Scenario B: Fallback to easy only when medium has zero eligible candidates
15. Hard fallback behavior (hard -> medium -> easy)
16. Easy fallback behavior (easy -> medium -> hard)
17. Scenario C: ID ASC breaks equal diversity scores
18. Scenario D: Candidate missing metadata receives no artificial penalty
19. Scenario E: Follow-up turns do not enter diversity history
20. Scenario F: Topic four bank questions ago is not penalized (bounded window = 3)
21. Only most recent 3 bank questions are used
22. No random selection / deterministic repeated selection
23. Category selection remains controlled by Phase 7
24. Difficulty adaptation remains unchanged
25. Bank exhaustion behavior remains unchanged
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.question_bank import (
    BASE_DIVERSITY_SCORE,
    TOPIC_RECENT_1_PENALTY,
    TOPIC_RECENT_2_PENALTY,
    SUBTOPIC_RECENT_PENALTY,
    QUESTION_TYPE_RECENT_PENALTY,
    SKILL_TYPE_RECENT_PENALTY,
    MAX_CONCEPT_PENALTY,
    calculate_diversity_breakdown,
    calculate_diversity_score,
    rank_candidates_by_diversity,
)
from backend import strategy_engine
from backend.database import create_tables, get_db


class TestDiversityScoring(unittest.TestCase):
    """Tests unit calculation of diversity penalties and scores."""

    def test_no_history_candidates_all_tie_at_100(self):
        """With empty history, all candidates receive BASE_DIVERSITY_SCORE (100.0)."""
        cand = {
            "id": 1,
            "topic": "Core Language & Data Structures",
            "subtopic": "Generators",
            "question_type": "conceptual",
            "skill_type": "understanding",
            "expected_concepts": ["yield", "iterator"],
        }
        score = calculate_diversity_score(cand, [])
        self.assertEqual(score, 100.0)

    def test_same_topic_as_immediate_prior_penalized_40(self):
        """Candidate matching topic of history[-1] receives -40 penalty."""
        history = [
            {"id": 99, "topic": "Memory Management & Internals", "subtopic": "GIL"}
        ]
        cand = {"id": 1, "topic": "Memory Management & Internals", "subtopic": "RefCounting"}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["topic_penalty"], 40.0)
        self.assertEqual(b["diversity_score"], 60.0)

    def test_older_topic_smaller_penalty_than_immediate(self):
        """History[-2] topic gets -20 penalty, whereas history[-1] gets -40."""
        history = [
            {"id": 98, "topic": "Concurrency & Async"},
            {"id": 99, "topic": "Memory Management & Internals"},
        ]
        cand_older = {"id": 1, "topic": "Concurrency & Async"}
        b_older = calculate_diversity_breakdown(cand_older, history)
        self.assertEqual(b_older["topic_penalty"], 20.0)
        self.assertEqual(b_older["diversity_score"], 80.0)

        cand_recent = {"id": 2, "topic": "Memory Management & Internals"}
        b_recent = calculate_diversity_breakdown(cand_recent, history)
        self.assertEqual(b_recent["topic_penalty"], 40.0)
        self.assertEqual(b_recent["diversity_score"], 60.0)

        self.assertGreater(b_older["diversity_score"], b_recent["diversity_score"])

    def test_subtopic_recent_3_penalized_30(self):
        """Candidate matching subtopic of history[-3] receives -30 penalty."""
        history = [
            {"id": 97, "topic": "Databases", "subtopic": "B-Trees"},
            {"id": 98, "topic": "System Design", "subtopic": "Transactions"},
            {"id": 99, "topic": "Python", "subtopic": "Replication"},
        ]
        cand = {"id": 1, "topic": "Databases", "subtopic": "B-Trees"}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["subtopic_penalty"], 30.0)
        # Topic penalty is 0 because topic appeared in history[-3], not [-1] or [-2]
        self.assertEqual(b["topic_penalty"], 0.0)
        self.assertEqual(b["diversity_score"], 70.0)

    def test_question_type_repetition_penalty_15(self):
        """Candidate matching question_type of history[-1] receives -15 penalty."""
        history = [{"id": 99, "question_type": "debugging"}]
        cand = {"id": 1, "question_type": "debugging"}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["question_type_penalty"], 15.0)
        self.assertEqual(b["diversity_score"], 85.0)

    def test_skill_type_repetition_penalty_10(self):
        """Candidate matching skill_type of history[-1] receives -10 penalty."""
        history = [{"id": 99, "skill_type": "tradeoff_analysis"}]
        cand = {"id": 1, "skill_type": "tradeoff_analysis"}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["skill_type_penalty"], 10.0)
        self.assertEqual(b["diversity_score"], 90.0)

    def test_concept_overlap_penalty(self):
        """Concept overlap Jaccard produces proportional penalty up to -20."""
        # 100% overlap
        history = [{"id": 99, "expected_concepts": ["gil", "thread", "cpython"]}]
        cand_full = {"id": 1, "expected_concepts": ["gil", "thread", "cpython"]}
        b_full = calculate_diversity_breakdown(cand_full, history)
        self.assertEqual(b_full["concept_overlap"], 1.0)
        self.assertEqual(b_full["concept_penalty"], 20.0)
        self.assertEqual(b_full["diversity_score"], 80.0)

        # 50% overlap: candidate has {a, b}, history has {b, c} -> intersection {b}, union {a, b, c} -> 1/3 = 0.3333
        # Let's make exact 50%: candidate {a, b, c}, history {b, c, d} -> intersection {b, c} (2), union {a, b, c, d} (4) -> 2/4 = 0.5
        history_50 = [{"id": 99, "expected_concepts": ["lock", "mutex", "deadlock"]}]
        cand_50 = {"id": 2, "expected_concepts": ["mutex", "deadlock", "starvation"]}
        b_50 = calculate_diversity_breakdown(cand_50, history_50)
        self.assertEqual(b_50["concept_overlap"], 0.5)
        self.assertEqual(b_50["concept_penalty"], 10.0)
        self.assertEqual(b_50["diversity_score"], 90.0)

    def test_stacked_diversity_penalties_clamp_to_zero(self):
        """
        Stacked diversity edge case where all applicable penalties stack:
        - topic: same as history[-1] (40.0) and history[-2] (20.0) -> topic penalty = 60.0
        - subtopic: same as one of recent 3 -> subtopic penalty = 30.0
        - question_type: same as history[-1] -> question_type penalty = 15.0
        - skill_type: same as history[-1] -> skill_type penalty = 10.0
        - expected_concepts: 100% Jaccard overlap with recent concepts -> concept penalty = 20.0
        Total penalty = 135.0
        Raw score = 100.0 - 135.0 = -35.0
        Final diversity score = 0.0 after clamping.
        """
        q_prev2 = {
            "id": 101,
            "topic": "Memory Management & Internals",
            "subtopic": "Global Interpreter Lock",
            "question_type": "conceptual",
            "skill_type": "understanding",
            "expected_concepts": ["GIL", "thread safety", "CPython"],
        }
        q_prev1 = {
            "id": 102,
            "topic": "Memory Management & Internals",
            "subtopic": "Global Interpreter Lock",
            "question_type": "conceptual",
            "skill_type": "understanding",
            "expected_concepts": ["GIL", "thread safety", "CPython"],
        }
        candidate = {
            "id": 103,
            "topic": "Memory Management & Internals",
            "subtopic": "Global Interpreter Lock",
            "question_type": "conceptual",
            "skill_type": "understanding",
            "expected_concepts": ["GIL", "thread safety", "CPython"],
        }
        history = [q_prev2, q_prev1]
        breakdown = calculate_diversity_breakdown(candidate, history)

        self.assertEqual(breakdown["topic_penalty"], 60.0)
        self.assertEqual(breakdown["subtopic_penalty"], 30.0)
        self.assertEqual(breakdown["question_type_penalty"], 15.0)
        self.assertEqual(breakdown["skill_type_penalty"], 10.0)
        self.assertEqual(breakdown["concept_penalty"], 20.0)
        self.assertEqual(breakdown["concept_overlap"], 1.0)

        total_penalty = (
            breakdown["topic_penalty"]
            + breakdown["subtopic_penalty"]
            + breakdown["question_type_penalty"]
            + breakdown["skill_type_penalty"]
            + breakdown["concept_penalty"]
        )
        self.assertEqual(total_penalty, 135.0)
        raw_score = BASE_DIVERSITY_SCORE - total_penalty
        self.assertEqual(raw_score, -35.0)
        self.assertEqual(breakdown["diversity_score"], 0.0)
        self.assertEqual(calculate_diversity_score(candidate, history), 0.0)

    def test_empty_topic_does_not_match_empty_topic(self):
        """Candidate with empty topic does not match history question with empty topic."""
        history = [{"id": 99, "topic": ""}]
        cand = {"id": 1, "topic": ""}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["topic_penalty"], 0.0)
        self.assertEqual(b["diversity_score"], 100.0)

    def test_null_topic_does_not_match_null_or_empty_topic(self):
        """Candidate with NULL topic does not match history with NULL/empty topic."""
        history = [{"id": 99, "topic": None}]
        cand = {"id": 1, "topic": None}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["topic_penalty"], 0.0)
        self.assertEqual(b["diversity_score"], 100.0)

    def test_empty_concepts_produce_zero_concept_penalty(self):
        """Empty concepts list produces 0 overlap and 0 concept penalty."""
        history = [{"id": 99, "expected_concepts": ["indexes", "b-tree"]}]
        cand = {"id": 1, "expected_concepts": []}
        b = calculate_diversity_breakdown(cand, history)
        self.assertEqual(b["concept_penalty"], 0.0)
        self.assertEqual(b["concept_overlap"], 0.0)
        self.assertEqual(b["diversity_score"], 100.0)

    def test_sparse_legacy_questions_remain_deterministic(self):
        """Candidates with completely missing metadata receive 100.0 and sort by id ASC."""
        candidates = [
            {"id": 40, "question": "Q40"},
            {"id": 10, "question": "Q10"},
            {"id": 25, "question": "Q25"},
        ]
        history = [{"id": 99, "topic": "Python", "question_type": "conceptual"}]
        ranked = rank_candidates_by_diversity(candidates, history)
        self.assertEqual([q["id"] for q in ranked], [10, 25, 40])
        for q in ranked:
            self.assertEqual(q["diversity_score"], 100.0)


class TestDiversityCandidateSelection(unittest.TestCase):
    """Tests runtime question selection integration in strategy engine."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.conn = sqlite3.connect(self.temp_db.name)
        self.conn.row_factory = sqlite3.Row
        create_tables_sql = """
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
            CREATE TABLE answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                answer TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL
            );
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        self.conn.executescript(create_tables_sql)

    def tearDown(self):
        self.conn.close()
        try:
            Path(self.temp_db.name).unlink(missing_ok=True)
        except Exception:
            pass

    def seed_question(self, q_id, category, difficulty, question, topic=None, subtopic=None, q_type=None, s_type=None, concepts=None):
        self.conn.execute(
            """
            INSERT INTO questions (id, category, difficulty, question, topic, subtopic, question_type, skill_type, expected_concepts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (q_id, category, difficulty, question, topic, subtopic, q_type, s_type, json.dumps(concepts or []))
        )
        self.conn.commit()

    # -----------------------------------------------------------------------
    # Manual Verification Scenario A: Medium beats more-diverse easy candidate
    # -----------------------------------------------------------------------
    def test_scenario_a_medium_beats_more_diverse_easy_candidate(self):
        """
        Scenario A:
        Requested medium.
        Medium candidate exists (diversity score 60.0 due to repeated topic).
        Easy candidate exists (diversity score 100.0).
        Result: Medium candidate is selected. Tier is NEVER skipped!
        """
        self.seed_question(
            1, "Python", "medium", "Medium Python Q1",
            topic="Memory Management & Internals"
        )
        self.seed_question(
            2, "Python", "easy", "Easy Python Q2",
            topic="Core Language & Data Structures"
        )
        history = [
            {"id": 99, "topic": "Memory Management & Internals"}
        ]

        q, diff = strategy_engine.select_bank_question(
            self.conn, "Python", "medium", set(), recent_bank_questions=history
        )
        self.assertIsNotNone(q)
        self.assertEqual(q["id"], 1, "Medium candidate must be selected despite lower diversity score!")
        self.assertEqual(diff, "medium")
        self.assertEqual(q["difficulty"], "medium")

    # -----------------------------------------------------------------------
    # Manual Verification Scenario B: Fallback to easy only when 0 medium
    # -----------------------------------------------------------------------
    def test_scenario_b_fallback_to_easy_only_when_zero_medium(self):
        """
        Scenario B:
        Requested medium.
        No unused medium candidates exist.
        Easy candidate exists.
        Result: Easy candidate selected via fallback.
        """
        self.seed_question(
            2, "Python", "easy", "Easy Python Q2",
            topic="Core Language & Data Structures"
        )
        history = [{"id": 99, "topic": "Memory Management & Internals"}]

        q, diff = strategy_engine.select_bank_question(
            self.conn, "Python", "medium", set(), recent_bank_questions=history
        )
        self.assertIsNotNone(q)
        self.assertEqual(q["id"], 2)
        self.assertEqual(diff, "easy")

    # -----------------------------------------------------------------------
    # Manual Verification Scenario C: ID ASC breaks equal diversity score
    # -----------------------------------------------------------------------
    def test_scenario_c_id_asc_breaks_equal_diversity(self):
        """
        Scenario C:
        Two medium candidates have identical diversity scores (80.0).
        Result: Candidate with lower question ID is selected.
        """
        # Both match second-most-recent topic -> both get 80.0
        self.seed_question(
            25, "Python", "medium", "Python Q25",
            topic="Concurrency & Async"
        )
        self.seed_question(
            10, "Python", "medium", "Python Q10",
            topic="Concurrency & Async"
        )
        history = [
            {"id": 98, "topic": "Concurrency & Async"},
            {"id": 99, "topic": "Memory Management & Internals"},
        ]

        q, diff = strategy_engine.select_bank_question(
            self.conn, "Python", "medium", set(), recent_bank_questions=history
        )
        self.assertEqual(q["id"], 10, "Tie must be broken by lowest question ID (10 < 25)")

    # -----------------------------------------------------------------------
    # Manual Verification Scenario D: Candidate missing metadata has no penalty
    # -----------------------------------------------------------------------
    def test_scenario_d_candidate_missing_metadata_has_no_artificial_penalty(self):
        """
        Scenario D:
        Candidate 1 has missing metadata (score 100.0).
        Candidate 2 has metadata that repeats recent topic (score 60.0).
        Result: Candidate 1 is preferred because it has 100.0 > 60.0.
        """
        # Note: give Candidate 2 lower ID (ID 5) than Candidate 1 (ID 15) to prove diversity overrides ID
        self.seed_question(
            5, "Python", "medium", "Python Q5 Repetitive Topic",
            topic="Memory Management & Internals"
        )
        self.seed_question(
            15, "Python", "medium", "Python Q15 Missing Metadata",
            topic=None, subtopic=None, concepts=[]
        )
        history = [{"id": 99, "topic": "Memory Management & Internals"}]

        q, diff = strategy_engine.select_bank_question(
            self.conn, "Python", "medium", set(), recent_bank_questions=history
        )
        self.assertEqual(q["id"], 15, "Diverse/non-repetitive question Q15 (score 100) beats repetitive Q5 (score 60)")

    # -----------------------------------------------------------------------
    # Manual Verification Scenario E: Follow-up turns excluded from diversity history
    # -----------------------------------------------------------------------
    def test_scenario_e_follow_up_turns_do_not_enter_diversity_history(self):
        """
        Scenario E:
        A follow-up occurred between two bank questions.
        Result: Follow-up does not enter the diversity history.
        """
        # Create session with:
        # Turn 1: Bank Q1 (id=1)
        # Turn 2: Follow-up (question_id=NULL, is_follow_up=1)
        # Turn 3: Bank Q2 (id=2)
        s_id = 101
        self.seed_question(1, "Python", "medium", "Bank Q1", topic="Topic A")
        self.seed_question(2, "Python", "medium", "Bank Q2", topic="Topic B")

        self.conn.execute("INSERT INTO interview_sessions (id, category, max_turns) VALUES (?, 'Python', 5)", (s_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, 1, 1, 'Bank Q1', 0)", (s_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, 2, NULL, 'Follow-up Q', 1)", (s_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, 3, 2, 'Bank Q2', 0)", (s_id,))
        self.conn.commit()

        recent = strategy_engine.get_recent_bank_questions(self.conn, s_id, limit=3)
        self.assertEqual(len(recent), 2)
        self.assertEqual([q["id"] for q in recent], [1, 2])
        self.assertEqual(recent[-1]["topic"], "Topic B")
        self.assertEqual(recent[-2]["topic"], "Topic A")

    # -----------------------------------------------------------------------
    # Manual Verification Scenario F: Topic 4 bank questions ago not penalized
    # -----------------------------------------------------------------------
    def test_scenario_f_topic_four_bank_questions_ago_not_penalized(self):
        """
        Scenario F:
        Topic appeared four bank questions ago, but not in the recent 3.
        Result: No topic repetition penalty.
        """
        s_id = 102
        self.seed_question(1, "Python", "medium", "Bank Q1", topic="Target Topic")
        self.seed_question(2, "Python", "medium", "Bank Q2", topic="Other 1")
        self.seed_question(3, "Python", "medium", "Bank Q3", topic="Other 2")
        self.seed_question(4, "Python", "medium", "Bank Q4", topic="Other 3")

        self.conn.execute("INSERT INTO interview_sessions (id, category, max_turns) VALUES (?, 'Python', 8)", (s_id,))
        for i in range(1, 5):
            self.conn.execute(
                "INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, ?, ?, ?, 0)",
                (s_id, i, i, f"Bank Q{i}")
            )
        self.conn.commit()

        recent = strategy_engine.get_recent_bank_questions(self.conn, s_id, limit=3)
        self.assertEqual(len(recent), 3)
        self.assertEqual([q["id"] for q in recent], [2, 3, 4])

        # Candidate with "Target Topic" (which was in Q1, outside recent 3)
        cand = {"id": 50, "topic": "Target Topic"}
        b = calculate_diversity_breakdown(cand, recent)
        self.assertEqual(b["topic_penalty"], 0.0, "Topic outside recent 3 window must receive 0 penalty")
        self.assertEqual(b["diversity_score"], 100.0)

    # -----------------------------------------------------------------------
    # Fallback and Determinism Tests
    # -----------------------------------------------------------------------
    def test_hard_fallback_behavior(self):
        """Requested hard with no hard candidates falls back to medium, then easy."""
        self.seed_question(1, "Databases", "easy", "Easy DB Q1")
        self.seed_question(2, "Databases", "medium", "Med DB Q2")

        # Requested hard -> medium exists -> returns medium
        q, diff = strategy_engine.select_bank_question(self.conn, "Databases", "hard", set())
        self.assertEqual(q["id"], 2)
        self.assertEqual(diff, "medium")

        # If medium is already used -> returns easy
        q2, diff2 = strategy_engine.select_bank_question(self.conn, "Databases", "hard", {2})
        self.assertEqual(q2["id"], 1)
        self.assertEqual(diff2, "easy")

    def test_easy_fallback_behavior(self):
        """Requested easy with no easy candidates falls back to medium, then hard."""
        self.seed_question(1, "System Design", "hard", "Hard SD Q1")
        self.seed_question(2, "System Design", "medium", "Med SD Q2")

        # Requested easy -> medium exists -> returns medium
        q, diff = strategy_engine.select_bank_question(self.conn, "System Design", "easy", set())
        self.assertEqual(q["id"], 2)
        self.assertEqual(diff, "medium")

        # If medium is already used -> returns hard
        q2, diff2 = strategy_engine.select_bank_question(self.conn, "System Design", "easy", {2})
        self.assertEqual(q2["id"], 1)
        self.assertEqual(diff2, "hard")

    def test_deterministic_repeated_selection(self):
        """Repeated calls with identical DB and history return identical question and difficulty."""
        self.seed_question(1, "Python", "medium", "Q1", topic="Topic A")
        self.seed_question(2, "Python", "medium", "Q2", topic="Topic B")
        history = [{"id": 99, "topic": "Topic A"}]

        first_q, first_diff = strategy_engine.select_bank_question(
            self.conn, "Python", "medium", set(), recent_bank_questions=history
        )
        for _ in range(50):
            q, diff = strategy_engine.select_bank_question(
                self.conn, "Python", "medium", set(), recent_bank_questions=history
            )
            self.assertEqual(first_q["id"], q["id"])
            self.assertEqual(first_diff, diff)

    def test_decide_next_turn_integrates_diversity_and_preserves_strategy(self):
        """decide_next_turn fetches recent bank questions, applies diversity, and retains Phase 7 rules."""
        s_id = 201
        self.seed_question(1, "Python", "medium", "Python Q1", topic="Topic A")
        self.seed_question(2, "Python", "medium", "Python Q2", topic="Topic B")

        self.conn.execute("INSERT INTO interview_sessions (id, category, max_turns) VALUES (?, 'Python', 5)", (s_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, 1, 1, 'Python Q1', 0)", (s_id,))
        self.conn.commit()

        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["category"], "Python")
        self.assertEqual(decision["question"]["id"], 2)

    def test_bank_exhaustion_returns_none(self):
        """When all questions in a category are used, select_bank_question returns (None, None)."""
        self.seed_question(1, "Python", "medium", "Python Q1")
        q, diff = strategy_engine.select_bank_question(
            self.conn, "Python", "medium", used_question_ids={1}
        )
        self.assertIsNone(q)
        self.assertIsNone(diff)

    def test_category_selection_remains_controlled_by_phase7(self):
        """Phase 7 category coverage rules strictly decide which category is next."""
        # Session in 'All' with Python already asked, Databases never asked
        s_id = 301
        self.seed_question(1, "Python", "medium", "Python Q1")
        self.seed_question(2, "Databases", "medium", "Databases Q2")
        self.conn.execute("INSERT INTO interview_sessions (id, category, max_turns) VALUES (?, 'All', 5)", (s_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up) VALUES (?, 1, 1, 'Python Q1', 0)", (s_id,))
        self.conn.commit()

        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        # Coverage rule: uncovered categories get priority -> Databases must be selected
        self.assertEqual(decision["category"], "Databases")
        self.assertEqual(decision["question"]["id"], 2)

    def test_difficulty_adaptation_remains_unchanged(self):
        """Score thresholds adapt difficulty (medium -> hard on score >= 80). Diversity does not override."""
        s_id = 302
        self.seed_question(1, "Python", "medium", "Python Q1")
        self.seed_question(2, "Python", "hard", "Python Q2")
        self.seed_question(3, "Python", "medium", "Python Q3")
        self.conn.execute("INSERT INTO interview_sessions (id, category, max_turns) VALUES (?, 'Python', 5)", (s_id,))
        self.conn.execute("INSERT INTO session_turns (session_id, turn_number, question_id, question_text, is_follow_up, answer_id) VALUES (?, 1, 1, 'Python Q1', 0, 1)", (s_id,))
        self.conn.execute("INSERT INTO answers (id, question_id, answer) VALUES (1, 1, 'High quality answer')",)
        self.conn.execute("INSERT INTO evaluations (answer_id, score, feedback) VALUES (1, 85, 'Excellent')",)
        self.conn.commit()

        # Score 85 >= 80 -> adapt difficulty to hard
        decision = strategy_engine.decide_next_turn(self.conn, s_id)
        self.assertEqual(decision["action"], "new_bank_question")
        self.assertEqual(decision["difficulty"], "hard")
        self.assertEqual(decision["question"]["id"], 2)


if __name__ == "__main__":
    unittest.main()
