import os
import re
import json
from pathlib import Path
from pydantic import BaseModel, Field

# Load .env if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass


class EvaluationResult(BaseModel):
    score: int = Field(ge=1, le=10, description="Overall performance score from 1 to 10")
    feedback: str = Field(description="Actionable summary feedback for the candidate")
    technical_accuracy: str = Field(description="Evaluation of technical correctness, concepts, and depth")
    strengths: list[str] = Field(default_factory=list, description="Specific concepts or points explained well")
    missing_points: list[str] = Field(default_factory=list, description="Key concepts, edge cases, or trade-offs that were missed")
    evaluator: str = Field(default="gemini-2.5-flash", description="Identifier of the evaluator used")


def _normalize_token(w: str) -> str:
    """Normalize word tokens by stripping common suffixes."""
    w = w.lower().strip()
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) > len(suffix) + 3:
            return w[:-len(suffix)]
    return w


def _extract_keywords(text: str) -> set[str]:
    """Extract lowercase significant words from text, ignoring common stopwords and normalizing."""
    stopwords = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
        "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
        "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
        "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
        "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
        "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
        "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
        "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
        "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
        "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
        "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
        "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
        "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
        "they've", "this", "those", "through", "to", "too", "under", "until", "up",
        "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
        "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
        "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
        "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
        "yourself", "yourselves", "explain", "describe", "difference", "between"
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {_normalize_token(w) for w in words if w not in stopwords}


def _heuristic_evaluate(
    question: str,
    category: str,
    difficulty: str,
    answer: str
) -> EvaluationResult:
    """
    Context-aware heuristic evaluation used when no external LLM API key is available.
    Evaluates the user's answer in relation to the specific question and category.
    """
    q_keywords = _extract_keywords(question)
    cat_keywords = _extract_keywords(category)
    target_keywords = q_keywords | cat_keywords

    a_keywords = _extract_keywords(answer)
    words = answer.strip().split()
    word_count = len(words)

    # Calculate question relevance via keyword overlap
    overlap = target_keywords & a_keywords
    overlap_ratio = len(overlap) / max(len(target_keywords), 1)

    strengths = []
    missing_points = []

    if overlap:
        matched_sample = ", ".join(sorted(list(overlap))[:3])
        strengths.append(f"Addressed key concepts from the question ({matched_sample}).")

    missing_keywords = target_keywords - a_keywords
    if missing_keywords:
        missing_sample = ", ".join(sorted(list(missing_keywords))[:3])
        missing_points.append(f"Consider exploring aspects related to: {missing_sample}.")

    # Difficulty expectations
    min_words_expected = 20 if difficulty == "beginner" else (35 if difficulty == "medium" else 50)

    # Determine score based on question relevance and depth
    if len(overlap) == 0:
        score = 2
        accuracy = "The answer does not appear to address the question asked."
        feedback = f"Your answer is off-topic for this {difficulty} {category} question. Make sure to directly address the core prompt."
        if not missing_points:
            missing_points.append("Direct answer to the core question prompt.")
    elif overlap_ratio < 0.25:
        score = 4
        accuracy = f"Partially touches upon the subject, but lacks focus on the specific prompt: '{question}'."
        feedback = f"You touched on some ideas, but didn't directly answer the core of the question. Structure your explanation around the main concepts."
        if word_count < min_words_expected:
            missing_points.append("Expand your answer with more concrete detail and a practical example.")
    elif word_count < min_words_expected:
        score = 6
        accuracy = "Answer is relevant to the question, but could be more comprehensive."
        feedback = f"Good start that directly addresses the question. To reach a top score for a {difficulty} question, provide a concrete real-world example or discuss trade-offs."
        strengths.append("Answer is focused on the correct topic.")
        missing_points.append("Include a specific real-world example or implementation nuance.")
    else:
        # High overlap and adequate length
        score = 8 if difficulty in ["medium", "hard"] else 9
        accuracy = f"Demonstrates solid technical understanding of the question topic ({category})."
        feedback = f"Strong and relevant explanation. You addressed the key aspects of the question clearly."
        strengths.append(f"Well-structured explanation appropriate for {difficulty} level.")
        if missing_keywords:
            missing_points.append("Mention edge cases or performance implications to make this answer exceptional.")
        else:
            missing_points.append("Discuss production edge cases or alternative architectures.")

    return EvaluationResult(
        score=score,
        feedback=feedback,
        technical_accuracy=accuracy,
        strengths=strengths,
        missing_points=missing_points,
        evaluator="heuristic-context-evaluator"
    )


def evaluate_interview_answer(
    question: str,
    category: str,
    difficulty: str,
    answer: str
) -> EvaluationResult:
    """
    Evaluates a candidate's answer to an interview question using Google Gemini API.
    Falls back to a context-aware heuristic analyzer if GEMINI_API_KEY is not configured.
    
    CRITICAL: The evaluator receives both question and answer to assess relevance and accuracy.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return _heuristic_evaluate(question, category, difficulty, answer)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""
You are an expert technical interviewer evaluating a candidate's response.

INTERVIEW QUESTION CONTEXT:
- Question: {question}
- Category: {category}
- Difficulty Level: {difficulty}

CANDIDATE'S SUBMITTED ANSWER:
\"\"\"{answer}\"\"\"

CRITICAL EVALUATION GUIDELINES:
1. You MUST evaluate this answer specifically in response to the question above. Never evaluate the answer in a vacuum.
2. Check if the answer is factually accurate for {category}, covers the necessary concepts for a {difficulty} interview, and addresses the actual question.
3. Scoring scale (1 to 10):
   - 1-3: Completely incorrect, irrelevant, or minimal effort.
   - 4-5: Vague, largely incomplete, or contains significant misconceptions.
   - 6-7: Acceptable basic understanding, but lacks depth, examples, or precision.
   - 8-9: Strong, well-explained answer covering the core concepts and trade-offs.
   - 10: Outstanding, expert-level response with clear nuance and precision.
4. Output structured JSON matching the requested schema.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationResult,
                temperature=0.2
            )
        )

        if response.text:
            data = json.loads(response.text)
            data["evaluator"] = "gemini-2.5-flash"
            return EvaluationResult(**data)
        else:
            return _heuristic_evaluate(question, category, difficulty, answer)

    except Exception as e:
        # Graceful fallback in case of rate limit or network glitch
        result = _heuristic_evaluate(question, category, difficulty, answer)
        result.feedback += f" (Note: Evaluated using local evaluator: {str(e)[:60]})"
        return result
