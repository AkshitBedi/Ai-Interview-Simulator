import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, r"c:\Users\akshi\OneDrive\Documents\Desktop\git clone\Ai-Interview-Simulator")

from backend.evaluator import (
    evaluate_interview_answer,
    _heuristic_evaluate,
    EvaluationResult
)


class TestEvaluatorCalibration(unittest.TestCase):
    """
    Test suite for evaluator calibration covering:
    a. exact repetition
    b. paraphrased repetition
    c. "I don't know" / refusals
    d. acknowledgement-only
    e. short technical answer
    f. normal good answer
    g. irrelevant answer
    """

    def setUp(self):
        self.question = "Explain normalization in databases."
        self.category = "Databases"
        self.difficulty = "medium"

    # --- CASE A: EXACT REPETITION ---
    def test_exact_repetition(self):
        answer = "Explain normalization in databases."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Exact repetition scored {result.score}, expected <= 2")
        self.assertIn("echo", result.feedback.lower() + result.technical_accuracy.lower())

    def test_exact_repetition_case_insensitive_no_punct(self):
        answer = "explain normalization in databases"
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Exact repetition without punct scored {result.score}, expected <= 2")

    def test_topic_fragment_repetition(self):
        answer = "Normalization in databases."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Topic fragment repetition scored {result.score}, expected <= 2")

    # --- CASE B: PARAPHRASED REPETITION / ECHO ---
    def test_paraphrased_repetition_with_lead_in(self):
        answer = "So to explain normalization in databases, please tell me."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Paraphrased repetition with lead-in scored {result.score}, expected <= 2")

    def test_paraphrased_repetition_question_restatement(self):
        answer = "Can you explain normalization in databases please?"
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Question restatement scored {result.score}, expected <= 2")

    def test_circular_tautological_echo(self):
        answer = "Normalization in databases is when you normalize databases."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Circular tautology scored {result.score}, expected <= 2")

    def test_echo_with_generic_filler(self):
        answer = "Normalization in databases is very important for databases."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Echo with filler scored {result.score}, expected <= 2")

    # --- CASE C: "I DON'T KNOW" / REFUSAL ---
    def test_refusal_i_dont_know(self):
        answer = "I don't know."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"'I don't know' scored {result.score}, expected <= 2")
        self.assertEqual(result.score, 1)

    def test_refusal_no_idea(self):
        answer = "I have no idea, pass."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2)
        self.assertEqual(result.score, 1)

    def test_refusal_skip(self):
        answer = "Skip."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertEqual(result.score, 1)

    # --- CASE D: ACKNOWLEDGEMENT-ONLY ---
    def test_acknowledgement_yes_thats_correct(self):
        answer = "Yes, that's correct."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Acknowledgement scored {result.score}, expected <= 2")
        self.assertEqual(result.score, 1)

    def test_acknowledgement_single_word(self):
        answer = "Right."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertEqual(result.score, 1)

    def test_acknowledgement_understood(self):
        answer = "Understood, makes sense."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertEqual(result.score, 1)

    # --- CASE E: SHORT GENUINE TECHNICAL ANSWER ---
    def test_short_technical_answer(self):
        answer = "Normalization organizes database columns and tables to reduce redundancy and improve data integrity."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertTrue(
            5 <= result.score <= 7,
            f"Short technical answer scored {result.score}, expected between 5 and 7"
        )
        self.assertIn("heuristic", result.evaluator)

    def test_short_technical_answer_python(self):
        question = "What is the purpose of Python virtual environments?"
        answer = "Virtual environments isolate project dependencies and prevent package version conflicts across different Python projects."
        result = evaluate_interview_answer(question, "Python", "medium", answer)
        self.assertTrue(
            5 <= result.score <= 7,
            f"Short technical answer scored {result.score}, expected between 5 and 7"
        )

    # --- CASE F: NORMAL GOOD ANSWER ---
    def test_normal_good_answer(self):
        answer = (
            "Database normalization is the process of structuring a relational database in "
            "accordance with normal forms like 1NF, 2NF, and 3NF. It reduces data redundancy "
            "by splitting large tables into smaller related tables and establishing relationships "
            "using foreign keys, which prevents insertion, update, and deletion anomalies while "
            "maintaining referential and data integrity."
        )
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertTrue(
            7 <= result.score <= 10,
            f"Good answer scored {result.score}, expected 7-10, got {result.score}"
        )

    # --- CASE G: IRRELEVANT ANSWER ---
    def test_irrelevant_answer(self):
        answer = "Photosynthesis is the process by which green plants use sunlight to synthesize nutrients from carbon dioxide and water."
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertLessEqual(result.score, 2, f"Irrelevant answer scored {result.score}, expected <= 2")

    # --- EMPTY ANSWER ---
    def test_empty_answer(self):
        answer = "   "
        result = evaluate_interview_answer(self.question, self.category, self.difficulty, answer)
        self.assertEqual(result.score, 1)


class TestGeminiPromptAndOutputContract(unittest.TestCase):
    """
    Verifies that the Gemini evaluation flow respects the schema and handles responses properly.
    """

    @patch("backend.evaluator.os.getenv")
    def test_gemini_client_invoked_and_handles_low_score_for_repetition(self, mock_getenv):
        mock_getenv.return_value = "fake_gemini_api_key"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            '{"score": 1, "feedback": "Candidate repeated the prompt.", '
            '"technical_accuracy": "Question repetition with no technical content.", '
            '"strengths": [], "missing_points": ["Explanation of normalization."]}'
        )
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            res = evaluate_interview_answer(
                "Explain normalization in databases.",
                "Databases",
                "medium",
                "Explain normalization in databases."
            )
            self.assertEqual(res.score, 1)
            self.assertEqual(res.evaluator, "gemini-3.6-flash")
            self.assertIn("repeated", res.feedback.lower())


if __name__ == "__main__":
    unittest.main()
