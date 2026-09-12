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
    evaluator: str = Field(default="gemini-3.6-flash", description="Identifier of the evaluator used")


def _normalize_token(w: str) -> str:
    """Normalize word tokens by stripping common inflectional suffixes."""
    w = w.lower().strip()
    for suffix in ("ization", "isation", "izing", "ising", "ized", "ised", "ize", "ise", "tion", "sion", "ing", "ed"):
        if w.endswith(suffix) and len(w) > len(suffix) + 3:
            return w[:-len(suffix)]
    if w.endswith(("sses", "xes", "ches", "shes")) and len(w) >= 5:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 4:
        return w[:-1]
    return w


_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could", "couldn't",
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
    "yourself", "yourselves", "explain", "describe", "difference", "between",
    "tell", "please", "question", "answer"
}

_GENERIC_META_WORDS = {
    "answer", "question", "explain", "explan", "mean", "concept", "topic",
    "subject", "thing", "use", "import", "way", "tell", "think", "talk",
    "want", "need", "look", "see", "ask", "said", "say", "good", "bad",
    "basic", "realli", "much", "well", "like"
}

_REFUSAL_PHRASES = {
    "i dont know", "i do not know", "dont know", "do not know", "no idea",
    "i have no idea", "no clue", "i have no clue", "not sure", "im not sure",
    "i am not sure", "pass", "skip", "can we skip", "skip this", "next",
    "next question", "no answer", "cannot answer", "cant answer", "idk",
    "na", "none", "i dont know the answer", "i do not know the answer",
    "not familiar with this", "no experience with this"
}

_ACKNOWLEDGEMENT_PHRASES = {
    "yes", "no", "yeah", "yep", "nope", "sure", "ok", "okay", "right",
    "correct", "thats correct", "that is correct", "yes thats correct",
    "yes that is correct", "thats right", "that is right", "yes thats right",
    "understood", "i see", "makes sense", "i agree", "sounds good", "exactly",
    "yes please", "sure thing", "got it"
}


def _extract_keywords(text: str) -> set[str]:
    """Extract lowercase significant words from text, ignoring common stopwords and normalizing."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {_normalize_token(w) for w in words if w not in _STOPWORDS}


def _heuristic_evaluate(
    question: str,
    category: str,
    difficulty: str,
    answer: str
) -> EvaluationResult:
    """
    Context-aware heuristic evaluation used when no external LLM API key is available.
    Evaluates the user's answer in relation to the specific question and category,
    strictly distinguishing genuine technical answers from question repetition,
    refusals, trivial acknowledgements, and off-topic responses.
    """
    # Strip apostrophes first so words like don't / that's / i'm become dont / thats / im
    norm_a = re.sub(r"['’]", "", answer.lower())
    clean_a = re.sub(r"[^a-z0-9\s]", " ", norm_a)
    clean_a = re.sub(r"\s+", " ", clean_a).strip()

    norm_q = re.sub(r"['’]", "", question.lower())
    clean_q = re.sub(r"[^a-z0-9\s]", " ", norm_q)
    clean_q = re.sub(r"\s+", " ", clean_q).strip()

    clean_a_words = clean_a.split()
    clean_q_words = clean_q.split()
    word_count = len(answer.strip().split())

    if not clean_a or word_count == 0:
        return EvaluationResult(
            score=1,
            feedback="No answer was provided. Please provide a substantive technical response.",
            technical_accuracy="Empty response.",
            strengths=[],
            missing_points=["Substantive response addressing the question."],
            evaluator="heuristic-context-evaluator"
        )

    # 1. Refusal check
    is_refusal = (
        clean_a in _REFUSAL_PHRASES
        or (
            any(clean_a == p or clean_a.startswith(p + " ") for p in (
                "i dont know", "i do not know", "no idea", "i have no idea",
                "no clue", "not sure", "im not sure", "cant answer", "cannot answer",
                "pass", "skip"
            ))
            and len(clean_a_words) <= 8
        )
    )

    # 2. Acknowledgement-only check
    is_acknowledgement = (
        clean_a in _ACKNOWLEDGEMENT_PHRASES
        or (
            any(clean_a == p or clean_a.startswith(p + " ") for p in (
                "yes thats correct", "that is correct", "thats correct", "thats right",
                "that is right", "yes that is correct", "understood", "makes sense",
                "i agree", "sounds good"
            ))
            and len(clean_a_words) <= 6
        )
    )

    # 3. Verbatim or Substring Repetition
    is_verbatim = (clean_a == clean_q)
    is_question_substring = (
        (clean_a in clean_q and len(clean_a_words) >= 2)
        or (clean_q in clean_a and len(clean_a_words) <= len(clean_q_words) + 4)
    )

    # 4. Conversational lead-in and trailing echo stripping
    stripped_a = clean_a
    changed = True
    while changed:
        changed = False
        for prefix in (
            "so ", "well ", "i think ", "i believe ", "the question is ",
            "to explain ", "let me explain ", "i will explain ", "i would like to explain ",
            "can you explain ", "could you explain ", "what is ", "what are ",
            "in terms of ", "regarding ", "with regards to ", "talking about ",
            "as for ", "you asked about ", "the answer is ", "i guess "
        ):
            if stripped_a.startswith(prefix):
                stripped_a = stripped_a[len(prefix):].strip()
                changed = True
        for suffix in (
            " please", " thank you", " thanks", " right", " correct", " as asked",
            " you know", " if that makes sense", " is the question", " that is all"
        ):
            if stripped_a.endswith(suffix):
                stripped_a = stripped_a[:-len(suffix)].strip()
                changed = True

    is_filler_echo = (
        (stripped_a == clean_q)
        or (stripped_a in clean_q and len(stripped_a.split()) >= 2)
        or (clean_q in stripped_a and len(stripped_a.split()) <= len(clean_q_words) + 2)
    )

    # 5. Lexical & Novelty analysis
    q_keywords = _extract_keywords(question)
    cat_keywords = _extract_keywords(category)
    target_keywords = q_keywords | cat_keywords

    a_keywords = _extract_keywords(answer)
    overlap = target_keywords & a_keywords
    overlap_ratio = len(overlap) / max(len(target_keywords), 1)

    # Novel keywords: meaningful tokens in answer not in target or generic meta words
    novel_keywords = a_keywords - target_keywords - _GENERIC_META_WORDS
    echo_ratio = len(overlap) / max(len(a_keywords), 1)

    # Substance echo: answer built mainly from echoing question terms with little or no new technical vocabulary
    is_substance_echo = (
        len(overlap) > 0
        and (
            len(novel_keywords) == 0
            or (len(novel_keywords) <= 1 and word_count <= 15 and len(clean_a_words) <= len(clean_q_words) + 5)
            or (echo_ratio >= 0.75 and len(novel_keywords) <= 1 and word_count <= 25)
        )
    )

    is_repetition = is_verbatim or is_question_substring or is_filler_echo or is_substance_echo

    # Non-answer / refusal / acknowledgement / repetition handling (Band 1-2)
    if is_refusal:
        return EvaluationResult(
            score=1,
            feedback="You indicated that you do not know the answer or skipped the question. In an interview, if you are unsure, try to outline what you do know about related concepts or how you would approach solving the problem.",
            technical_accuracy="Candidate indicated they do not know the answer or declined to answer.",
            strengths=[],
            missing_points=["Substantive technical explanation addressing the core question."],
            evaluator="heuristic-context-evaluator"
        )

    if is_acknowledgement:
        return EvaluationResult(
            score=1,
            feedback="A brief confirmation or acknowledgement does not demonstrate technical understanding. Provide a detailed explanation explaining the concept and how it works.",
            technical_accuracy="Trivial acknowledgement or confirmation without technical explanation.",
            strengths=[],
            missing_points=["Detailed technical explanation and core principles."],
            evaluator="heuristic-context-evaluator"
        )

    if is_repetition:
        score = 1 if (is_verbatim or is_question_substring or len(novel_keywords) == 0) else 2
        return EvaluationResult(
            score=score,
            feedback="Your answer merely restates or echoes the question rather than answering it. Mentioning keywords from the prompt is not evidence of technical understanding. Provide a substantive explanation covering principles, mechanisms, or trade-offs.",
            technical_accuracy="Repeats or restates the question prompt without providing an actual technical explanation.",
            strengths=[],
            missing_points=["Substantive technical explanation rather than echoing the prompt."],
            evaluator="heuristic-context-evaluator"
        )

    # Strengths and missing points extraction
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

    # Completely off-topic (Band 1-2)
    if len(overlap) == 0:
        score = 2
        accuracy = "The answer does not appear to address the question asked."
        feedback = f"Your answer is off-topic for this {difficulty} {category} question. Make sure to directly address the core prompt."
        if not missing_points:
            missing_points.append("Direct answer to the core question prompt.")
    # Mentions category but zero question keywords
    elif len(q_keywords & a_keywords) == 0 and len(cat_keywords & a_keywords) > 0:
        score = 4
        accuracy = f"Touches upon {category} concepts, but lacks focus on the specific prompt: '{question}'."
        feedback = f"You mentioned {category} concepts, but didn't directly answer the core of the question. Focus your explanation around the specific prompt."
        missing_points.append("Direct answer to the specific prompt.")
    # Low overlap with question (Band 2-4)
    elif overlap_ratio < 0.25:
        score = 4
        accuracy = f"Partially touches upon the subject, but lacks focus on the specific prompt: '{question}'."
        feedback = f"You touched on some ideas, but didn't directly answer the core of the question. Structure your explanation around the main concepts."
        if word_count < min_words_expected:
            missing_points.append("Expand your answer with more concrete detail and a practical example.")
    # Below word count expectation for depth
    elif word_count < min_words_expected:
        if len(novel_keywords) <= 2:
            # Minimal substance (Band 2-4)
            score = 3 if word_count < 10 else 4
            accuracy = "Relevant to the topic, but extremely brief with minimal technical substance."
            feedback = f"You mentioned relevant concepts, but the explanation is too superficial for a {difficulty} question. Elaborate on the mechanisms and principles."
            missing_points.append("Provide a deeper technical explanation with specific mechanisms.")
        else:
            # Meaningful technical content in concise form (Band 4-6)
            if difficulty == "beginner":
                score = 7
            elif difficulty == "medium":
                score = 6 if word_count >= 10 else 5
            else:  # hard
                score = 6 if word_count >= 15 else 5
            accuracy = f"Accurate and concise technical definition addressing the core concepts of {category}."
            feedback = f"Good, focused explanation of the core concept. To achieve a top score for a {difficulty} question, provide a concrete real-world example or discuss trade-offs."
            strengths.append("Answer is focused on the correct topic with clear technical terminology.")
            missing_points.append("Include a specific real-world example or implementation nuance.")
    else:
        # High overlap and adequate length
        if len(novel_keywords) <= 3:
            score = 5
            accuracy = "Adequate length, but relies on repetition and lacks technical depth."
            feedback = f"Your answer has adequate length but needs more specific technical depth and concepts for a {difficulty} question."
            missing_points.append("Discuss specific architecture, algorithms, or practical trade-offs.")
        else:
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
    
    CRITICAL: The evaluator receives both question and answer to assess relevance, substance, and accuracy.
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
1. SUBSTANTIVE CONTENT REQUIREMENT:
   - You MUST evaluate whether the candidate provides actual substantive technical explanation, mechanisms, principles, or reasoning that directly answers the question.
   - Merely echoing, repeating, or paraphrasing the question (verbatim or restated) WITHOUT providing an actual answer is a NON-ANSWER.
   - Mentioning keywords from the question (e.g. repeating terms like "{question}") is NOT evidence of technical understanding.

2. NON-ANSWERS, REFUSALS, AND QUESTION REPETITIONS:
   - Verbatim or paraphrased/restated repetition of the question without an actual answer MUST be scored 1 or 2 out of 10.
   - Refusals (e.g., "I don't know", "skip", "no idea"), evasions, and trivial acknowledgements (e.g., "Yes, that's correct", "Okay") MUST be scored 1 or 2 out of 10.
   - Completely off-topic or irrelevant answers MUST be scored 1 or 2 out of 10.

3. SCORING BANDS (1 to 10):
   - 1-2: Non-answer, question repetition/paraphrase, refusal, acknowledgement-only, or completely irrelevant.
   - 2-4: Relevant but extremely incomplete/superficial, or contains major technical errors.
   - 4-6: Partially correct with meaningful technical content, but lacks depth, precision, or examples.
   - 7-8: Good, accurate answer covering key concepts clearly.
   - 9-10: Strong/expert answer with depth, precision, and trade-offs/edge cases where appropriate.

4. Evaluate specifically in response to the question and category ({category}), accounting for the expected depth of a {difficulty}-level interview.
5. Output structured JSON matching the requested schema.
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationResult,
                temperature=0.2
            )
        )

        if response.text:
            data = json.loads(response.text)
            data["evaluator"] = "gemini-3.6-flash"
            return EvaluationResult(**data)
        else:
            return _heuristic_evaluate(question, category, difficulty, answer)

    except Exception as e:
        # Graceful fallback in case of rate limit or network glitch
        result = _heuristic_evaluate(question, category, difficulty, answer)
        result.feedback += f" (Note: Evaluated using local evaluator: {str(e)[:60]})"
        return result

