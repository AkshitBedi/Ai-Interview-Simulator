"""
backend/question_bank.py

Phase 10: Rich Question Bank Metadata, Controlled Taxonomies & Validation.
Provides:
- Controlled taxonomies (categories, difficulties, question_types, skill_types, quality_tiers, topics)
- Difficulty normalization and legacy compatibility (beginner -> easy)
- Safe parsing of JSON/list metadata without crashing on malformed input
- Four-way validation status distinction:
    * VALID: Conforms to all taxonomies and constraints with rich metadata
    * MISSING: Sparse/legacy question with valid core fields and missing/empty metadata
    * INVALID: Corrupted structure, invalid types, or malformed JSON
    * UNKNOWN_TAXONOMY: Values outside controlled taxonomies
- Pure parsing and row conversion for SQLite records
- Pydantic models for API integration
"""

import re
import json
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Controlled Taxonomies & Constants
# ---------------------------------------------------------------------------

CANONICAL_CATEGORIES = (
    "Python",
    "Databases",
    "System Design",
    "Behavioral"
)

CANONICAL_DIFFICULTIES = ("easy", "medium", "hard")
LEGACY_DIFFICULTY_MAP = {"beginner": "easy"}

TECHNICAL_QUESTION_TYPES = (
    "conceptual",
    "comparison",
    "scenario",
    "debugging",
    "design",
    "tradeoff",
    "implementation",
    "prediction",
)

BEHAVIORAL_QUESTION_TYPES = (
    "experience",
    "situational",
    "conflict",
    "leadership",
    "failure",
    "decision",
)

ALL_QUESTION_TYPES = TECHNICAL_QUESTION_TYPES + BEHAVIORAL_QUESTION_TYPES

SKILL_TYPES = (
    "recall",
    "understanding",
    "application",
    "reasoning",
    "debugging",
    "design",
    "tradeoff_analysis",
    "communication",
)

QUALITY_TIERS = ("core", "advanced", "specialized")
DEFAULT_QUALITY_TIER = "core"

TOPICS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "Python": (
        "Core Language & Data Structures",
        "Memory Management & Internals",
        "Concurrency & Async",
        "OOP & Metaprogramming",
        "Testing & Performance Profiling",
        "Ecosystem & Tooling",
    ),
    "Databases": (
        "Relational Modeling & Schema Design",
        "Indexing & Query Optimization",
        "Transactions & ACID Internals",
        "Replication, Partitioning & Scaling",
        "Storage Engines & Buffer Management",
        "NoSQL & Distributed Storage Paradigms",
    ),
    "System Design": (
        "Distributed Architecture & Scalability",
        "Data Consistency & Storage Pipelines",
        "Networking, Protocols & Load Balancing",
        "Caching, Buffering & Message Queues",
        "Reliability, Observability & Fault Tolerance",
        "API & Security Architecture",
    ),
    "Behavioral": (
        "Leadership & Initiative",
        "Conflict Resolution & Collaboration",
        "Delivery Under Pressure & Prioritization",
        "Ownership, Failure & Accountability",
        "Communication & Mentorship",
        "Career Growth & Adaptability",
    ),
}

JSON_METADATA_FIELDS = (
    "expected_concepts",
    "common_mistakes",
    "ideal_answer_points",
    "prerequisites",
)

SCALAR_METADATA_FIELDS = (
    "topic",
    "subtopic",
    "question_type",
    "skill_type",
    "quality_tier",
)


# ---------------------------------------------------------------------------
# 2. Difficulty Normalization & Taxonomy Checkers
# ---------------------------------------------------------------------------

def normalize_difficulty(difficulty: str | None) -> str:
    """
    Normalizes difficulty string to canonical 'easy', 'medium', or 'hard'.
    Legacy database value 'beginner' maps to 'easy'.
    Missing/invalid difficulty defaults to 'medium'.
    """
    if not difficulty:
        return "medium"
    cleaned = str(difficulty).strip().lower()
    if cleaned in LEGACY_DIFFICULTY_MAP:
        return LEGACY_DIFFICULTY_MAP[cleaned]
    if cleaned in CANONICAL_DIFFICULTIES:
        return cleaned
    return "medium"


def is_valid_difficulty(difficulty: Any) -> bool:
    """Checks if difficulty is a string matching canonical difficulties or legacy beginner."""
    if not difficulty or not isinstance(difficulty, str):
        return False
    cleaned = difficulty.strip().lower()
    return cleaned in CANONICAL_DIFFICULTIES or cleaned in LEGACY_DIFFICULTY_MAP


def is_valid_category(category: Any) -> bool:
    """Checks if category is one of the 4 canonical categories."""
    if not category or not isinstance(category, str):
        return False
    return category.strip() in CANONICAL_CATEGORIES


def is_valid_topic(category: str, topic: Any) -> bool:
    """Checks if topic belongs to the allowed controlled topic taxonomy for the category."""
    if not topic or not isinstance(topic, str):
        return False
    allowed = TOPICS_BY_CATEGORY.get(category.strip())
    if not allowed:
        return False
    t_clean = topic.strip()
    return any(t_clean.lower() == a.lower() for a in allowed)


def get_canonical_topic(category: str, topic: str) -> str | None:
    """Returns canonical case-matched topic string, or None if not found."""
    allowed = TOPICS_BY_CATEGORY.get(category.strip())
    if not allowed:
        return None
    t_clean = topic.strip()
    for a in allowed:
        if t_clean.lower() == a.lower():
            return a
    return None


def is_valid_question_type(question_type: Any, category: str | None = None) -> bool:
    """
    Validates question type against controlled taxonomy.
    If category is provided:
      - 'Behavioral' -> must be in BEHAVIORAL_QUESTION_TYPES
      - Technical categories -> must be in TECHNICAL_QUESTION_TYPES
    """
    if not question_type or not isinstance(question_type, str):
        return False
    qt_clean = question_type.strip().lower()
    if category:
        c_clean = category.strip()
        if c_clean == "Behavioral":
            return qt_clean in BEHAVIORAL_QUESTION_TYPES
        else:
            return qt_clean in TECHNICAL_QUESTION_TYPES
    return qt_clean in ALL_QUESTION_TYPES


def is_valid_skill_type(skill_type: Any) -> bool:
    """Checks if skill_type is in the controlled SKILL_TYPES taxonomy."""
    if not skill_type or not isinstance(skill_type, str):
        return False
    return skill_type.strip().lower() in SKILL_TYPES


def is_valid_quality_tier(quality_tier: Any) -> bool:
    """Checks if quality_tier is in QUALITY_TIERS ('core', 'advanced', 'specialized')."""
    if not quality_tier or not isinstance(quality_tier, str):
        return False
    return quality_tier.strip().lower() in QUALITY_TIERS


# ---------------------------------------------------------------------------
# 3. Safe JSON / List Parsing & Serialization
# ---------------------------------------------------------------------------

def parse_string_list(val: Any, field_name: str = "field") -> tuple[list[str], bool, str | None]:
    """
    Safely parses a field into a list of non-empty strings.
    Never raises an uncaught exception.
    
    Accepts:
    - None, "", "[]", [] -> ([], True, None) [treated as empty/no-data]
    - JSON string representing list of strings
    - Python list/tuple of strings
    
    Returns:
    - (cleaned_items, is_valid, error_message)
    """
    if val is None:
        return [], True, None

    if isinstance(val, str):
        trimmed = val.strip()
        if trimmed in ("", "[]"):
            return [], True, None
        try:
            parsed = json.loads(trimmed)
        except (json.JSONDecodeError, ValueError) as e:
            return [], False, f"Malformed JSON in {field_name}: {e}"
    elif isinstance(val, (list, tuple)):
        parsed = list(val)
    else:
        return [], False, f"{field_name} must be a list or JSON array string, got {type(val).__name__}"

    if not isinstance(parsed, list):
        return [], False, f"{field_name} must represent a list, got {type(parsed).__name__}"

    cleaned: list[str] = []
    for idx, item in enumerate(parsed):
        if not isinstance(item, str):
            return [], False, f"Item {idx} in {field_name} must be a string, got {type(item).__name__}"
        s = item.strip()
        if not s:
            return [], False, f"Item {idx} in {field_name} cannot be an empty or whitespace string"
        cleaned.append(s)

    return cleaned, True, None


def serialize_string_list(items: list[str] | None) -> str:
    """Serializes a list of strings to JSON string format. Returns '[]' for empty/None."""
    if not items:
        return "[]"
    return json.dumps(list(items))


# ---------------------------------------------------------------------------
# 4. Four-Way Validation Status & Record Validator
# ---------------------------------------------------------------------------

class ValidationStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"
    UNKNOWN_TAXONOMY = "UNKNOWN_TAXONOMY"


@dataclass
class ValidationResult:
    is_valid: bool
    status: str  # "VALID", "MISSING", "INVALID", "UNKNOWN_TAXONOMY"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cleaned_data: dict[str, Any] = field(default_factory=dict)


def validate_question_record(record: dict[str, Any]) -> ValidationResult:
    """
    Validates an interview question record and distinguishes:
    - VALID: Conforms to all taxonomies and structural requirements with rich metadata.
    - MISSING: Valid core fields (category, difficulty, question) with missing/empty metadata
               (sparse fixtures / legacy questions).
    - INVALID: Structural flaws, missing core fields, malformed JSON, or wrong types.
    - UNKNOWN_TAXONOMY: Values that do not exist in the controlled taxonomies.
    
    Does NOT silently invent metadata.
    Does NOT treat '' or [] as meaningful shared metadata.
    """
    structural_errors: list[str] = []
    taxonomy_errors: list[str] = []
    cleaned: dict[str, Any] = {}

    # --- Core Field 1: question ---
    raw_question = record.get("question")
    if raw_question is None:
        structural_errors.append("Missing required field 'question'")
    elif not isinstance(raw_question, str):
        structural_errors.append(f"'question' must be a string, got {type(raw_question).__name__}")
    elif not raw_question.strip():
        structural_errors.append("'question' cannot be empty or whitespace")
    else:
        cleaned["question"] = raw_question.strip()

    # --- Core Field 2: category ---
    raw_category = record.get("category")
    if raw_category is None:
        structural_errors.append("Missing required field 'category'")
    elif not isinstance(raw_category, str):
        structural_errors.append(f"'category' must be a string, got {type(raw_category).__name__}")
    elif not raw_category.strip():
        structural_errors.append("'category' cannot be empty or whitespace")
    else:
        cat_clean = raw_category.strip()
        matched_cat = None
        for canonical in CANONICAL_CATEGORIES:
            if cat_clean.lower() == canonical.lower():
                matched_cat = canonical
                break
        if matched_cat:
            cleaned["category"] = matched_cat
        else:
            taxonomy_errors.append(
                f"Unknown category '{cat_clean}'. Must be one of {CANONICAL_CATEGORIES}"
            )
            cleaned["category"] = cat_clean

    # --- Core Field 3: difficulty ---
    raw_difficulty = record.get("difficulty")
    if raw_difficulty is None:
        structural_errors.append("Missing required field 'difficulty'")
    elif not isinstance(raw_difficulty, str):
        structural_errors.append(f"'difficulty' must be a string, got {type(raw_difficulty).__name__}")
    else:
        diff_clean = raw_difficulty.strip().lower()
        if diff_clean in CANONICAL_DIFFICULTIES or diff_clean in LEGACY_DIFFICULTY_MAP:
            cleaned["difficulty"] = normalize_difficulty(diff_clean)
        else:
            taxonomy_errors.append(
                f"Unknown difficulty '{raw_difficulty}'. Must be one of {CANONICAL_DIFFICULTIES} or 'beginner'"
            )
            cleaned["difficulty"] = diff_clean

    # --- Metadata Fields: Parsing & Validation ---
    cat_for_validation = cleaned.get("category")

    # 1. JSON List Fields
    for field_name in JSON_METADATA_FIELDS:
        raw_val = record.get(field_name)
        parsed_list, is_valid_json, err_msg = parse_string_list(raw_val, field_name)
        if not is_valid_json:
            structural_errors.append(err_msg or f"Invalid JSON list in {field_name}")
            cleaned[field_name] = []
        else:
            cleaned[field_name] = parsed_list

    # 2. Quality Tier
    raw_tier = record.get("quality_tier")
    if raw_tier is None or (isinstance(raw_tier, str) and not raw_tier.strip()):
        cleaned["quality_tier"] = DEFAULT_QUALITY_TIER
    elif not isinstance(raw_tier, str):
        structural_errors.append(f"'quality_tier' must be a string, got {type(raw_tier).__name__}")
        cleaned["quality_tier"] = DEFAULT_QUALITY_TIER
    else:
        tier_clean = raw_tier.strip().lower()
        if tier_clean in QUALITY_TIERS:
            cleaned["quality_tier"] = tier_clean
        else:
            taxonomy_errors.append(
                f"Unknown quality_tier '{raw_tier}'. Must be one of {QUALITY_TIERS}"
            )
            cleaned["quality_tier"] = tier_clean

    # 3. Topic
    raw_topic = record.get("topic")
    if raw_topic is None or (isinstance(raw_topic, str) and not raw_topic.strip()):
        cleaned["topic"] = None
    elif not isinstance(raw_topic, str):
        structural_errors.append(f"'topic' must be a string, got {type(raw_topic).__name__}")
        cleaned["topic"] = None
    else:
        if cat_for_validation and cat_for_validation in TOPICS_BY_CATEGORY:
            canonical_top = get_canonical_topic(cat_for_validation, raw_topic)
            if canonical_top:
                cleaned["topic"] = canonical_top
            else:
                taxonomy_errors.append(
                    f"Unknown topic '{raw_topic}' for category '{cat_for_validation}'. "
                    f"Must be one of {TOPICS_BY_CATEGORY[cat_for_validation]}"
                )
                cleaned["topic"] = raw_topic.strip()
        else:
            cleaned["topic"] = raw_topic.strip()

    # 4. Subtopic
    raw_subtopic = record.get("subtopic")
    if raw_subtopic is None or (isinstance(raw_subtopic, str) and not raw_subtopic.strip()):
        cleaned["subtopic"] = None
    elif not isinstance(raw_subtopic, str):
        structural_errors.append(f"'subtopic' must be a string, got {type(raw_subtopic).__name__}")
        cleaned["subtopic"] = None
    else:
        cleaned["subtopic"] = raw_subtopic.strip()

    # 5. Question Type
    raw_qt = record.get("question_type")
    if raw_qt is None or (isinstance(raw_qt, str) and not raw_qt.strip()):
        cleaned["question_type"] = None
    elif not isinstance(raw_qt, str):
        structural_errors.append(f"'question_type' must be a string, got {type(raw_qt).__name__}")
        cleaned["question_type"] = None
    else:
        qt_clean = raw_qt.strip().lower()
        if is_valid_question_type(qt_clean, cat_for_validation):
            cleaned["question_type"] = qt_clean
        else:
            expected_types = (
                BEHAVIORAL_QUESTION_TYPES if cat_for_validation == "Behavioral"
                else TECHNICAL_QUESTION_TYPES
            )
            taxonomy_errors.append(
                f"Unknown question_type '{raw_qt}' for category '{cat_for_validation}'. "
                f"Must be one of {expected_types}"
            )
            cleaned["question_type"] = qt_clean

    # 6. Skill Type
    raw_skill = record.get("skill_type")
    if raw_skill is None or (isinstance(raw_skill, str) and not raw_skill.strip()):
        cleaned["skill_type"] = None
    elif not isinstance(raw_skill, str):
        structural_errors.append(f"'skill_type' must be a string, got {type(raw_skill).__name__}")
        cleaned["skill_type"] = None
    else:
        skill_clean = raw_skill.strip().lower()
        if is_valid_skill_type(skill_clean):
            cleaned["skill_type"] = skill_clean
        else:
            taxonomy_errors.append(
                f"Unknown skill_type '{raw_skill}'. Must be one of {SKILL_TYPES}"
            )
            cleaned["skill_type"] = skill_clean

    # --- Preserve original ID if present ---
    if "id" in record:
        cleaned["id"] = record["id"]

    # --- Determine 4-way Status ---
    if structural_errors:
        return ValidationResult(
            is_valid=False,
            status=ValidationStatus.INVALID.value,
            errors=structural_errors + taxonomy_errors,
            cleaned_data=cleaned
        )

    if taxonomy_errors:
        return ValidationResult(
            is_valid=False,
            status=ValidationStatus.UNKNOWN_TAXONOMY.value,
            errors=taxonomy_errors,
            cleaned_data=cleaned
        )

    # Check if any rich metadata is provided
    has_rich_metadata = bool(
        cleaned.get("topic")
        or cleaned.get("subtopic")
        or cleaned.get("question_type")
        or cleaned.get("skill_type")
        or cleaned.get("expected_concepts")
        or cleaned.get("common_mistakes")
        or cleaned.get("ideal_answer_points")
        or cleaned.get("prerequisites")
        or (record.get("quality_tier") and record.get("quality_tier") != DEFAULT_QUALITY_TIER)
    )

    cleaned["has_rich_metadata"] = has_rich_metadata

    if not has_rich_metadata:
        return ValidationResult(
            is_valid=True,
            status=ValidationStatus.MISSING.value,
            errors=[],
            cleaned_data=cleaned
        )

    return ValidationResult(
        is_valid=True,
        status=ValidationStatus.VALID.value,
        errors=[],
        cleaned_data=cleaned
    )


# Alias for validate_question_record
validate_question_metadata = validate_question_record


# ---------------------------------------------------------------------------
# 5. Safe Row Parser for SQLite Records
# ---------------------------------------------------------------------------

def parse_question_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """
    Converts a database row or dict into a standard question dict with parsed metadata.
    Guaranteed to never crash on missing columns or malformed JSON.
    """
    d = dict(row)
    category = d.get("category", "")
    difficulty = normalize_difficulty(d.get("difficulty"))
    question = d.get("question", "")

    # Parse JSON list fields safely
    expected_concepts, _, _ = parse_string_list(d.get("expected_concepts"), "expected_concepts")
    common_mistakes, _, _ = parse_string_list(d.get("common_mistakes"), "common_mistakes")
    ideal_answer_points, _, _ = parse_string_list(d.get("ideal_answer_points"), "ideal_answer_points")
    prerequisites, _, _ = parse_string_list(d.get("prerequisites"), "prerequisites")

    topic = d.get("topic")
    if topic is not None and not str(topic).strip():
        topic = None

    subtopic = d.get("subtopic")
    if subtopic is not None and not str(subtopic).strip():
        subtopic = None

    question_type = d.get("question_type")
    if question_type is not None and not str(question_type).strip():
        question_type = None

    skill_type = d.get("skill_type")
    if skill_type is not None and not str(skill_type).strip():
        skill_type = None

    quality_tier = d.get("quality_tier") or DEFAULT_QUALITY_TIER

    has_rich = bool(
        topic or subtopic or question_type or skill_type or
        expected_concepts or common_mistakes or ideal_answer_points or prerequisites or
        (quality_tier != DEFAULT_QUALITY_TIER)
    )

    res = {
        "id": d.get("id"),
        "category": category,
        "difficulty": difficulty,
        "question": question,
        "topic": topic,
        "subtopic": subtopic,
        "question_type": question_type,
        "skill_type": skill_type,
        "quality_tier": quality_tier,
        "expected_concepts": expected_concepts,
        "common_mistakes": common_mistakes,
        "ideal_answer_points": ideal_answer_points,
        "prerequisites": prerequisites,
        "has_rich_metadata": has_rich,
    }
    return res


def get_question_by_id(connection: sqlite3.Connection, question_id: int) -> dict[str, Any] | None:
    """Fetches a question by ID and returns parsed dict with all metadata, or None if not found."""
    cols = {row["name"] for row in connection.execute("PRAGMA table_info(questions)").fetchall()}
    if "topic" in cols:
        row = connection.execute(
            """
            SELECT id, category, difficulty, question,
                   topic, subtopic, question_type, skill_type, quality_tier,
                   expected_concepts, common_mistakes, ideal_answer_points, prerequisites
            FROM questions
            WHERE id = ?
            """,
            (question_id,)
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT id, category, difficulty, question FROM questions WHERE id = ?",
            (question_id,)
        ).fetchone()

    if not row:
        return None
    return parse_question_row(row)


# ---------------------------------------------------------------------------
# Default Expanded Question Bank & Seeder
# ---------------------------------------------------------------------------

try:
    from backend.question_data import ALL_AUTHORED_QUESTIONS
except (ImportError, ValueError):
    try:
        from question_data import ALL_AUTHORED_QUESTIONS
    except (ImportError, ValueError):
        ALL_AUTHORED_QUESTIONS = []

DEFAULT_QUESTION_BANK = ALL_AUTHORED_QUESTIONS


def seed_question_bank(
    connection: sqlite3.Connection,
    questions: list[dict[str, Any]] | None = None
) -> dict[str, int]:
    """
    Seeds and enriches the questions table with the high-quality question bank.
    - Preserves existing rows and question IDs (e.g. 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15).
    - Updates rich metadata for existing questions in-place.
    - Preserves test artifact ID 4 completely untouched.
    - Inserts newly authored questions if not already present.
    Returns: {"updated": int, "inserted": int, "total": int}
    """
    bank = questions if questions is not None else ALL_AUTHORED_QUESTIONS
    if not bank:
        total_curr = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        return {"updated": 0, "inserted": 0, "total": total_curr}

    cols = {row["name"] for row in connection.execute("PRAGMA table_info(questions)").fetchall()}
    has_metadata = "topic" in cols

    updated_count = 0
    inserted_count = 0

    existing_rows = connection.execute("SELECT id, question FROM questions").fetchall()
    existing_by_id = {row["id"]: row["question"] for row in existing_rows}
    existing_by_text = {row["question"]: row["id"] for row in existing_rows}

    for item in bank:
        q_id = item.get("id")
        q_text = item.get("question", "")
        cat = item.get("category", "")
        diff = normalize_difficulty(item.get("difficulty"))
        topic = item.get("topic")
        subtopic = item.get("subtopic")
        q_type = item.get("question_type")
        s_type = item.get("skill_type")
        tier = item.get("quality_tier") or DEFAULT_QUALITY_TIER
        concepts = json.dumps(item.get("expected_concepts") or [])
        mistakes = json.dumps(item.get("common_mistakes") or [])
        ideal_points = json.dumps(item.get("ideal_answer_points") or [])
        prereqs = json.dumps(item.get("prerequisites") or [])

        # Check if question already exists by exact text match
        target_id = None
        if q_text in existing_by_text:
            target_id = existing_by_text[q_text]
        elif q_id is not None and q_id in existing_by_id and q_id != 4:
            if existing_by_id[q_id] == q_text:
                target_id = q_id

        if target_id is not None:
            # Update existing row with rich metadata
            if has_metadata:
                connection.execute(
                    """
                    UPDATE questions
                    SET category = ?, difficulty = ?, question = ?,
                        topic = ?, subtopic = ?, question_type = ?, skill_type = ?, quality_tier = ?,
                        expected_concepts = ?, common_mistakes = ?, ideal_answer_points = ?, prerequisites = ?
                    WHERE id = ?
                    """,
                    (cat, diff, q_text, topic, subtopic, q_type, s_type, tier, concepts, mistakes, ideal_points, prereqs, target_id)
                )
            else:
                connection.execute(
                    "UPDATE questions SET category = ?, difficulty = ?, question = ? WHERE id = ?",
                    (cat, diff, q_text, target_id)
                )
            updated_count += 1
        else:
            # Insert new question
            if q_id is not None and q_id not in existing_by_id and q_id != 4:
                # Insert with explicit ID
                if has_metadata:
                    cursor = connection.execute(
                        """
                        INSERT INTO questions (
                            id, category, difficulty, question,
                            topic, subtopic, question_type, skill_type, quality_tier,
                            expected_concepts, common_mistakes, ideal_answer_points, prerequisites
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (q_id, cat, diff, q_text, topic, subtopic, q_type, s_type, tier, concepts, mistakes, ideal_points, prereqs)
                    )
                else:
                    cursor = connection.execute(
                        "INSERT INTO questions (id, category, difficulty, question) VALUES (?, ?, ?, ?)",
                        (q_id, cat, diff, q_text)
                    )
                new_id = q_id
            else:
                # Insert with auto-increment ID
                if has_metadata:
                    cursor = connection.execute(
                        """
                        INSERT INTO questions (
                            category, difficulty, question,
                            topic, subtopic, question_type, skill_type, quality_tier,
                            expected_concepts, common_mistakes, ideal_answer_points, prerequisites
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (cat, diff, q_text, topic, subtopic, q_type, s_type, tier, concepts, mistakes, ideal_points, prereqs)
                    )
                else:
                    cursor = connection.execute(
                        "INSERT INTO questions (category, difficulty, question) VALUES (?, ?, ?)",
                        (cat, diff, q_text)
                    )
                new_id = cursor.lastrowid

            existing_by_id[new_id] = q_text
            existing_by_text[q_text] = new_id
            inserted_count += 1

    connection.commit()
    total = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    return {"updated": updated_count, "inserted": inserted_count, "total": total}


# ---------------------------------------------------------------------------
# 6. Pydantic Models for Question Metadata
# ---------------------------------------------------------------------------

class QuestionMetadata(BaseModel):
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    question_type: Optional[str] = None
    skill_type: Optional[str] = None
    quality_tier: Optional[str] = DEFAULT_QUALITY_TIER
    expected_concepts: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    ideal_answer_points: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)


class QuestionItem(BaseModel):
    id: Optional[int] = None
    category: str
    difficulty: str
    question: str
    metadata: Optional[QuestionMetadata] = None


# ---------------------------------------------------------------------------
# 7. Deterministic Exact and Near-Duplicate Detection
# ---------------------------------------------------------------------------

NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.80
SHORT_QUESTION_TOKEN_LIMIT = 3

PUNCTUATION_PATTERN = re.compile(r'[^\w\s]')
WHITESPACE_PATTERN = re.compile(r'\s+')

# Controlled English question framing words & structural stopwords.
# Domain-specific technical terms (sql, nosql, gil, acid, join, cache, async,
# thread, process, lock, index, decorator, table, etc.) are strictly excluded.
QUESTION_STOPWORDS = {
    # Articles
    "a", "an", "the",
    # Be verbs
    "am", "is", "are", "was", "were", "be", "been", "being",
    # Auxiliaries & modal verbs
    "do", "does", "did",
    "have", "has", "had", "having",
    "can", "could", "would", "should", "will", "shall", "may", "might", "must",
    # Prepositions & conjunctions
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "into", "onto",
    "about", "and", "or", "but", "nor", "so",
    # Question framing & interrogatives
    "what", "how", "why", "when", "where", "which", "who", "whom", "whose",
    # Common prompt verbs
    "explain", "describe", "discuss", "tell", "me", "please", "briefly",
    # Pronouns
    "i", "you", "your", "yours", "we", "our", "ours", "it", "its", "they", "their", "theirs",
    "this", "that", "these", "those",
}


def normalize_question_text(text: str | None) -> str:
    """
    Exact question text normalization:
    1. Lowercase
    2. Replace punctuation with spaces
    3. Collapse whitespace
    4. Strip leading/trailing whitespace
    Identical normalized text represents an exact duplicate.
    """
    if not text or not isinstance(text, str):
        return ""
    lowered = text.lower()
    punct_replaced = PUNCTUATION_PATTERN.sub(" ", lowered)
    collapsed = WHITESPACE_PATTERN.sub(" ", punct_replaced)
    return collapsed.strip()


def extract_meaningful_tokens(text: str | None) -> set[str]:
    """
    Extracts normalized meaningful tokens from question text:
    1. Normalizes text (lowercase, punctuation to spaces, collapse whitespace).
    2. Splits on whitespace into individual tokens.
    3. Filters out stopwords that do not carry technical distinction.
    4. If all words were stopwords, preserves the full normalized tokens to avoid empty sets.
    """
    norm = normalize_question_text(text)
    if not norm:
        return set()
    all_tokens = norm.split()
    meaningful = {t for t in all_tokens if t not in QUESTION_STOPWORDS}
    if not meaningful:
        meaningful = set(all_tokens)
    return meaningful


def compute_token_jaccard(tokens_a: set[str], tokens_b: set[str]) -> float:
    """
    Deterministic token-set Jaccard similarity:
    Jaccard(A, B) = |A ∩ B| / |A ∪ B|
    Returns 0.0 if either set is empty.
    """
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    if not union:
        return 0.0
    return len(intersection) / len(union)


def compare_questions(q1: str | None, q2: str | None) -> dict[str, Any]:
    """
    Compares two question strings for exact and near duplicate status.
    
    1. Exact duplicate:
       - Compares normalized strings.
       - If both normalized strings are non-empty and identical -> EXACT duplicate.
    
    2. Near duplicate:
       - Token-set Jaccard similarity on meaningful tokens.
       - Short-question safeguard: Questions with fewer than 3 meaningful tokens (< 3)
         must only be treated as near-duplicates when their meaningful token sets are
         identical (Jaccard == 1.0).
       - Standard questions (>= 3 meaningful tokens):
         Near-duplicate threshold is Jaccard >= NEAR_DUPLICATE_JACCARD_THRESHOLD (0.80).
    """
    norm1 = normalize_question_text(q1)
    norm2 = normalize_question_text(q2)

    if not norm1 or not norm2:
        return {
            "is_exact_duplicate": False,
            "is_near_duplicate": False,
            "is_duplicate": False,
            "duplicate_type": None,
            "jaccard_similarity": 0.0,
            "tokens_q1": [],
            "tokens_q2": [],
            "short_safeguard_applied": False,
            "reason": "One or both questions are empty or non-string",
        }

    # 1. Exact Duplicate
    is_exact = (norm1 == norm2)
    tokens1_set = extract_meaningful_tokens(q1)
    tokens2_set = extract_meaningful_tokens(q2)

    if is_exact:
        return {
            "is_exact_duplicate": True,
            "is_near_duplicate": True,
            "is_duplicate": True,
            "duplicate_type": "EXACT",
            "jaccard_similarity": 1.0,
            "tokens_q1": sorted(tokens1_set),
            "tokens_q2": sorted(tokens2_set),
            "short_safeguard_applied": False,
            "reason": "Identical normalized text",
        }

    # 2. Near Duplicate via Token-set Jaccard
    jaccard = compute_token_jaccard(tokens1_set, tokens2_set)
    short_safeguard = (len(tokens1_set) < SHORT_QUESTION_TOKEN_LIMIT or
                       len(tokens2_set) < SHORT_QUESTION_TOKEN_LIMIT)

    if short_safeguard:
        is_near = (jaccard == 1.0)
        reason = "Short-question safeguard applied (< 3 tokens): requires Jaccard == 1.0" if is_near else None
    else:
        is_near = (jaccard >= NEAR_DUPLICATE_JACCARD_THRESHOLD)
        reason = f"Token Jaccard ({jaccard:.4f}) >= {NEAR_DUPLICATE_JACCARD_THRESHOLD}" if is_near else None

    return {
        "is_exact_duplicate": False,
        "is_near_duplicate": is_near,
        "is_duplicate": is_near,
        "duplicate_type": "NEAR" if is_near else None,
        "jaccard_similarity": round(jaccard, 4),
        "tokens_q1": sorted(tokens1_set),
        "tokens_q2": sorted(tokens2_set),
        "short_safeguard_applied": short_safeguard,
        "reason": reason,
    }


def check_question_duplicate(
    candidate_text: str | None,
    existing_questions: list[dict[str, Any]],
    candidate_id: int | None = None
) -> dict[str, Any]:
    """
    Validates a candidate question text against an inventory of existing questions.
    Ignores comparison with itself if candidate_id matches existing question's id.
    
    Returns:
    {
        "has_duplicate": bool,
        "duplicate_type": "EXACT" | "NEAR" | None,
        "conflicting_question_id": int | None,
        "conflicting_question_text": str | None,
        "jaccard_similarity": float,
        "matches": list[dict[str, Any]]
    }
    """
    matches = []
    has_exact = False
    has_near = False
    top_match = None
    max_jaccard = -1.0

    for q in existing_questions:
        q_id = q.get("id")
        if candidate_id is not None and q_id is not None and candidate_id == q_id:
            continue
        q_text = q.get("question", "")
        cmp = compare_questions(candidate_text, q_text)
        if cmp["is_duplicate"]:
            match_info = {
                "conflicting_id": q_id,
                "conflicting_text": q_text,
                "duplicate_type": cmp["duplicate_type"],
                "jaccard_similarity": cmp["jaccard_similarity"],
                "short_safeguard_applied": cmp["short_safeguard_applied"],
                "reason": cmp["reason"],
            }
            matches.append(match_info)
            if cmp["duplicate_type"] == "EXACT":
                has_exact = True
            elif cmp["duplicate_type"] == "NEAR":
                has_near = True

            if cmp["jaccard_similarity"] > max_jaccard:
                max_jaccard = cmp["jaccard_similarity"]
                top_match = match_info

    dup_type = "EXACT" if has_exact else ("NEAR" if has_near else None)
    return {
        "has_duplicate": (dup_type is not None),
        "duplicate_type": dup_type,
        "conflicting_question_id": top_match["conflicting_id"] if top_match else None,
        "conflicting_question_text": top_match["conflicting_text"] if top_match else None,
        "jaccard_similarity": max_jaccard if top_match else 0.0,
        "matches": matches,
    }


def find_all_bank_duplicates(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Scans a list of questions and finds all duplicate/near-duplicate pairs (i < j).
    Returns list of conflict records.
    """
    conflicts = []
    n = len(questions)
    for i in range(n):
        q1 = questions[i]
        q1_id = q1.get("id")
        q1_text = q1.get("question", "")
        for j in range(i + 1, n):
            q2 = questions[j]
            q2_id = q2.get("id")
            q2_text = q2.get("question", "")
            cmp = compare_questions(q1_text, q2_text)
            if cmp["is_duplicate"]:
                conflicts.append({
                    "question_id_a": q1_id,
                    "question_text_a": q1_text,
                    "question_id_b": q2_id,
                    "question_text_b": q2_text,
                    "duplicate_type": cmp["duplicate_type"],
                    "jaccard_similarity": cmp["jaccard_similarity"],
                    "short_safeguard_applied": cmp["short_safeguard_applied"],
                    "reason": cmp["reason"],
                })
    return conflicts


# ---------------------------------------------------------------------------
# 8. Deterministic Diversity Scoring & Candidate Ordering
# ---------------------------------------------------------------------------

BASE_DIVERSITY_SCORE = 100.0

# Diversity Penalty Weights
TOPIC_RECENT_1_PENALTY = 40.0       # Same topic as most recent bank question
TOPIC_RECENT_2_PENALTY = 20.0       # Same topic as second-most-recent bank question
SUBTOPIC_RECENT_PENALTY = 30.0      # Same subtopic as any of the recent 3 bank questions
QUESTION_TYPE_RECENT_PENALTY = 15.0 # Same question type as most recent bank question
SKILL_TYPE_RECENT_PENALTY = 10.0    # Same skill type as most recent bank question
MAX_CONCEPT_PENALTY = 20.0          # Maximum concept penalty
CONCEPT_PENALTY_MULTIPLIER = 20.0   # Concept penalty = 20.0 * overlap


def calculate_diversity_breakdown(
    candidate: dict[str, Any],
    recent_bank_questions: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """
    Calculates detailed diversity breakdown for a candidate question against
    the bounded history of up to 3 recent bank questions.
    
    Empty/NULL metadata means NO DATA and never triggers an artificial repetition penalty.
    """
    history = recent_bank_questions or []
    
    topic_penalty = 0.0
    subtopic_penalty = 0.0
    question_type_penalty = 0.0
    skill_type_penalty = 0.0
    concept_penalty = 0.0
    concept_overlap = 0.0

    # 1. Topic Repetition Penalties
    cand_topic = candidate.get("topic")
    if cand_topic is not None and str(cand_topic).strip():
        ct = str(cand_topic).strip().lower()
        if len(history) >= 1:
            rec1_t = history[-1].get("topic")
            if rec1_t is not None and str(rec1_t).strip().lower() == ct:
                topic_penalty += TOPIC_RECENT_1_PENALTY
        if len(history) >= 2:
            rec2_t = history[-2].get("topic")
            if rec2_t is not None and str(rec2_t).strip().lower() == ct:
                topic_penalty += TOPIC_RECENT_2_PENALTY

    # 2. Subtopic Repetition Penalty (any of the recent 3)
    cand_subtopic = candidate.get("subtopic")
    if cand_subtopic is not None and str(cand_subtopic).strip():
        cs = str(cand_subtopic).strip().lower()
        for q in history[-3:]:
            rec_s = q.get("subtopic")
            if rec_s is not None and str(rec_s).strip().lower() == cs:
                subtopic_penalty = SUBTOPIC_RECENT_PENALTY
                break

    # 3. Question-Type Repetition Penalty (most recent bank question)
    cand_qt = candidate.get("question_type")
    if cand_qt is not None and str(cand_qt).strip() and len(history) >= 1:
        cqt = str(cand_qt).strip().lower()
        rec1_qt = history[-1].get("question_type")
        if rec1_qt is not None and str(rec1_qt).strip().lower() == cqt:
            question_type_penalty = QUESTION_TYPE_RECENT_PENALTY

    # 4. Skill-Type Repetition Penalty (most recent bank question)
    cand_st = candidate.get("skill_type")
    if cand_st is not None and str(cand_st).strip() and len(history) >= 1:
        cst = str(cand_st).strip().lower()
        rec1_st = history[-1].get("skill_type")
        if rec1_st is not None and str(rec1_st).strip().lower() == cst:
            skill_type_penalty = SKILL_TYPE_RECENT_PENALTY

    # 5. Concept Overlap Penalty (against union of expected_concepts from recent questions)
    cand_concepts_raw = candidate.get("expected_concepts") or []
    cand_concepts, _, _ = parse_string_list(cand_concepts_raw, "expected_concepts")
    
    cand_concept_tokens: set[str] = set()
    for c in cand_concepts:
        cand_concept_tokens.update(extract_meaningful_tokens(c))

    recent_concept_tokens: set[str] = set()
    for q in history[-3:]:
        q_concepts_raw = q.get("expected_concepts") or []
        q_concepts, _, _ = parse_string_list(q_concepts_raw, "expected_concepts")
        for c in q_concepts:
            recent_concept_tokens.update(extract_meaningful_tokens(c))

    if cand_concept_tokens and recent_concept_tokens:
        concept_overlap = compute_token_jaccard(cand_concept_tokens, recent_concept_tokens)
        concept_penalty = min(MAX_CONCEPT_PENALTY, CONCEPT_PENALTY_MULTIPLIER * concept_overlap)

    # Total Score
    total_score = (
        BASE_DIVERSITY_SCORE
        - topic_penalty
        - subtopic_penalty
        - question_type_penalty
        - skill_type_penalty
        - concept_penalty
    )
    clamped_score = max(0.0, min(BASE_DIVERSITY_SCORE, total_score))

    return {
        "diversity_score": round(clamped_score, 2),
        "topic_penalty": topic_penalty,
        "subtopic_penalty": subtopic_penalty,
        "question_type_penalty": question_type_penalty,
        "skill_type_penalty": skill_type_penalty,
        "concept_penalty": round(concept_penalty, 2),
        "concept_overlap": round(concept_overlap, 4),
    }


def calculate_diversity_score(
    candidate: dict[str, Any],
    recent_bank_questions: list[dict[str, Any]] | None
) -> float:
    """Calculates final clamped diversity score (0.0 to 100.0) for a candidate question."""
    breakdown = calculate_diversity_breakdown(candidate, recent_bank_questions)
    return breakdown["diversity_score"]


def rank_candidates_by_diversity(
    candidates: list[dict[str, Any]],
    recent_bank_questions: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """
    Ranks candidate questions deterministically:
    Primary: diversity_score DESC
    Secondary: question_id ASC
    """
    if not candidates:
        return []
    history = recent_bank_questions or []
    scored = []
    for cand in candidates:
        c_copy = dict(cand)
        score = calculate_diversity_score(c_copy, history)
        c_copy["diversity_score"] = score
        scored.append(c_copy)

    # Deterministic sort: diversity_score DESC, id ASC
    scored.sort(key=lambda q: (-q["diversity_score"], q.get("id") or 0))
    return scored

