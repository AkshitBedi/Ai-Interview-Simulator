"""
Centralized Google Gemini Model Configuration.

Provides a unified configuration point for the Gemini model identifier used across all
production AI-backed modules (evaluator, interviewer, document processor, coaching,
interview engine claim probing, and insights engine).

Supports dynamic override via the GEMINI_MODEL environment variable, defaulting to
'gemini-3.6-flash' for backward compatibility.
"""

from __future__ import annotations

import os

DEFAULT_GEMINI_MODEL: str = "gemini-3.6-flash"


def get_gemini_model() -> str:
    """
    Returns the configured Gemini model name.

    Reads from the GEMINI_MODEL environment variable if set and non-empty;
    otherwise defaults to DEFAULT_GEMINI_MODEL ('gemini-3.6-flash').
    """
    env_model = os.environ.get("GEMINI_MODEL")
    if env_model and env_model.strip():
        return env_model.strip()
    return DEFAULT_GEMINI_MODEL
