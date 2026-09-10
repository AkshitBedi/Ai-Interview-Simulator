import sys
import tempfile
import sqlite3
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path.cwd()))

from fastapi.testclient import TestClient
import backend.main as main
from backend.database import create_tables, get_db
from backend.interview_engine import generate_follow_up_question


def run_phase3_tests():
    print("==================================================")
    print("PHASE 3 VERIFICATION SUITE")
    print("==================================================")

    client = TestClient(main.app)

    # ----------------------------------------------------
    # TEST 1: Foreign Key Integrity & Database Schema
    # ----------------------------------------------------
    print("\n[TEST 1] Checking Foreign Key Integrity & Schema...")
    create_tables()
    conn = get_db()
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert len(fk_violations) == 0, f"Foreign key violations found: {fk_violations}"

    # Verify tables exist
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for expected in ["questions", "answers", "evaluations", "interview_sessions", "session_turns"]:
        assert expected in tables, f"Table {expected} missing!"

    # Verify answers.question_id allows NULL
    answers_info = {r["name"]: r for r in conn.execute("PRAGMA table_info(answers)").fetchall()}
    assert answers_info["question_id"]["notnull"] == 0, "answers.question_id must be nullable!"

    # Verify session_turns schema (Modification 1)
    turns_info = {r["name"]: r for r in conn.execute("PRAGMA table_info(session_turns)").fetchall()}
    assert "question_id" in turns_info and turns_info["question_id"]["notnull"] == 0
    assert "question_text" in turns_info and turns_info["question_text"]["notnull"] == 1
    conn.close()
    print("PASS: Database schema and foreign key integrity verified.")

    # ----------------------------------------------------
    # TEST 2: Missing Gemini API Key Fallback
    # ----------------------------------------------------
    print("\n[TEST 2] Testing Missing Gemini API Key Fallback...")
    import os
    orig_key = os.environ.get("GEMINI_API_KEY")
    try:
        os.environ["GEMINI_API_KEY"] = ""
        fallback_q = generate_follow_up_question(
            original_question="What is the GIL?",
            candidate_answer="It locks threads in Python.",
            evaluation_feedback="Partially correct.",
            missing_points=["multiprocessing alternatives", "CPU-bound vs IO-bound limits"],
            category="Python",
            difficulty="medium"
        )
        assert len(fallback_q) > 15
        assert "multiprocessing" in fallback_q or "elaborate" in fallback_q
        print(f"Fallback Generated: \"{fallback_q}\"")
    finally:
        if orig_key:
            os.environ["GEMINI_API_KEY"] = orig_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
    print("PASS: Fallback generates natural question without crashing when offline/no key.")

    # ----------------------------------------------------
    # TEST 3: Complete Flow (POST /sessions -> answer -> follow-up -> answer -> complete -> summary)
    # ----------------------------------------------------
    print("\n[TEST 3] Testing Complete Session Flow & Adaptive Follow-Up...")
    # Start session with max_turns = 3
    res_start = client.post("/sessions", json={"category": "Python", "difficulty": "medium", "max_turns": 3})
    assert res_start.status_code == 201, res_start.text
    session_data = res_start.json()
    session_id = session_data["session_id"]
    assert session_data["current_turn"] == 1
    assert session_data["max_turns"] == 3
    q1 = session_data["question"]
    assert q1["is_follow_up"] is False
    assert q1["question_id"] is not None
    assert len(q1["question"]) > 10
    print(f"Session #{session_id} Started. Turn 1 (Bank Q#{q1['question_id']}): \"{q1['question'][:50]}...\"")

    # Turn 1: Submit answer designed to get partial score (score ~4-6) so follow-up triggers
    ans1_text = "It manages threads and memory in Python so that only one thread runs at a time."
    res_ans1 = client.post(f"/sessions/{session_id}/answer", json={"answer": ans1_text})
    assert res_ans1.status_code == 200, res_ans1.text
    turn1_eval = res_ans1.json()
    print(f"Turn 1 Answer Evaluated: score={turn1_eval['evaluated_turn']['score']}, decision={turn1_eval['decision']}")

    # Verification: If score 3-6 with missing points, decision must be follow_up
    assert turn1_eval["decision"] == "follow_up"
    q2 = turn1_eval["next_question"]
    assert q2["is_follow_up"] is True
    assert q2["question_id"] is None, "Generated follow-up question_id must be NULL (Modification 1)!"
    assert q2["turn_number"] == 2
    assert len(q2["question"]) > 10
    print(f"Turn 2 Generated Follow-Up: \"{q2['question']}\" (question_id=NULL)")

    # Turn 2: Submit strong answer for follow-up
    ans2_text = "To bypass this limitation for CPU-bound tasks in Python, you should use the multiprocessing module or ProcessPoolExecutor to run separate processes on multiple CPU cores."
    res_ans2 = client.post(f"/sessions/{session_id}/answer", json={"answer": ans2_text})
    assert res_ans2.status_code == 200, res_ans2.text
    turn2_eval = res_ans2.json()
    print(f"Turn 2 Answer Evaluated: score={turn2_eval['evaluated_turn']['score']}, decision={turn2_eval['decision']}")

    # Verification: Circuit breaker rule! Previous turn was a follow-up, so decision must be new_question!
    assert turn2_eval["decision"] == "new_question"
    q3 = turn2_eval["next_question"]
    assert q3["is_follow_up"] is False
    assert q3["question_id"] is not None
    assert q3["question_id"] != q1["question_id"], "Question must not repeat within session!"
    assert q3["turn_number"] == 3
    print(f"Turn 3 Next Bank Question (Bank Q#{q3['question_id']}): \"{q3['question'][:50]}...\"")

    # Turn 3: Submit answer for turn 3 (should reach max_turns = 3 and complete session)
    ans3_text = "Generators use the yield keyword to produce items lazily on-demand, which conserves memory compared to storing complete lists."
    res_ans3 = client.post(f"/sessions/{session_id}/answer", json={"answer": ans3_text})
    assert res_ans3.status_code == 200, res_ans3.text
    turn3_eval = res_ans3.json()
    assert turn3_eval["decision"] == "completed"
    assert turn3_eval["status"] == "completed"
    assert turn3_eval["next_question"] is None
    print(f"Turn 3 Completed. Session Status: {turn3_eval['status']}")

    # Check Summary
    res_summary = client.get(f"/sessions/{session_id}/summary")
    assert res_summary.status_code == 200
    summary_data = res_summary.json()
    assert summary_data["total_turns_evaluated"] == 3
    assert summary_data["follow_up_questions_count"] == 1
    assert summary_data["bank_questions_count"] == 2
    assert summary_data["average_score"] > 0
    assert len(summary_data["score_breakdown"]) == 3
    assert "overall_recommendation" in summary_data
    print(f"Summary generated: Avg Score={summary_data['average_score']}, Recommendation: {summary_data['overall_recommendation'][:60]}...")
    print("PASS: Complete session flow, follow-up generation, and completion summary verified.")

    # ----------------------------------------------------
    # TEST 4: No Repeated Bank Questions Within a Session
    # ----------------------------------------------------
    print("\n[TEST 4] Testing No Repeated Bank Questions...")
    res_s2 = client.post("/sessions", json={"max_turns": 4})
    s2_id = res_s2.json()["session_id"]
    asked_q_ids = [res_s2.json()["question"]["question_id"]]

    # Submit strong answers to force new bank questions every turn
    for _ in range(3):
        res = client.post(f"/sessions/{s2_id}/answer", json={"answer": "This is a detailed technical explanation covering all architecture aspects and production considerations."})
        next_q = res.json().get("next_question")
        if next_q and next_q["question_id"] is not None:
            assert next_q["question_id"] not in asked_q_ids, f"Duplicate bank question asked: {next_q['question_id']}"
            asked_q_ids.append(next_q["question_id"])

    assert len(asked_q_ids) == len(set(asked_q_ids)), "All asked bank questions must be unique!"
    print(f"Asked Bank Questions in Session #{s2_id}: {asked_q_ids} (All unique)")
    print("PASS: No bank questions repeated within a session.")

    # ----------------------------------------------------
    # TEST 5: Off-Topic Answers Pivot Immediately (Score <= 2)
    # ----------------------------------------------------
    print("\n[TEST 5] Testing Off-Topic Answers Pivot to New Question (Score <= 2)...")
    res_s3 = client.post("/sessions", json={"category": "Python", "max_turns": 3})
    s3_id = res_s3.json()["session_id"]
    res_off = client.post(f"/sessions/{s3_id}/answer", json={"answer": "The weather outside today is extremely sunny and very warm."})
    eval_off = res_off.json()
    assert eval_off["evaluated_turn"]["score"] <= 2, f"Expected score <= 2 for off-topic, got {eval_off['evaluated_turn']['score']}"
    assert eval_off["decision"] == "new_question", f"Off-topic answer must move to new question, got {eval_off['decision']}"
    assert eval_off["next_question"]["is_follow_up"] is False
    print("PASS: Off-topic answer (score <= 2) immediately moves to a new question.")

    # ----------------------------------------------------
    # TEST 6: Maximum One Consecutive Follow-Up Limit
    # ----------------------------------------------------
    print("\n[TEST 6] Testing Max 1 Consecutive Follow-Up Limit...")
    res_s4 = client.post("/sessions", json={"max_turns": 4})
    s4_id = res_s4.json()["session_id"]
    # Turn 1: Partial answer -> follow-up
    ans_p = client.post(f"/sessions/{s4_id}/answer", json={"answer": "It manages memory and threads in the software system."}).json()
    if ans_p["decision"] == "follow_up":
        # Turn 2: Another partial answer to the follow-up
        ans_f = client.post(f"/sessions/{s4_id}/answer", json={"answer": "It manages memory and threads in the software system."}).json()
        assert ans_f["decision"] == "new_question", f"Must NOT allow consecutive follow-up! Got: {ans_f['decision']}"
        assert ans_f["next_question"]["is_follow_up"] is False
    print("PASS: Consecutive follow-up circuit breaker enforced.")

    # ----------------------------------------------------
    # TEST 7: Existing Single-Question Endpoints Backward Compatibility
    # ----------------------------------------------------
    print("\n[TEST 7] Testing Existing Single-Question Endpoints...")
    r_stats = client.get("/stats")
    assert r_stats.status_code == 200
    assert "total_questions" in r_stats.json() and "total_answers" in r_stats.json()

    r_rand = client.get("/questions/random")
    assert r_rand.status_code == 200
    q_id = r_rand.json()["question"]["id"]

    r_sub = client.post(f"/questions/{q_id}/answers", json={"answer": "Comprehensive answer testing standalone single question endpoint."})
    assert r_sub.status_code == 200
    ans_id = r_sub.json()["answer_id"]

    r_fb = client.get(f"/answers/{ans_id}/feedback")
    assert r_fb.status_code == 200
    assert "score" in r_fb.json() and "feedback" in r_fb.json()

    r_prev = client.get(f"/questions/{q_id}/answers")
    assert r_prev.status_code == 200
    print("PASS: Existing single-question API endpoints fully functional.")

    print("\n==================================================")
    print("ALL 7 PHASE 3 VERIFICATION TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_phase3_tests()
