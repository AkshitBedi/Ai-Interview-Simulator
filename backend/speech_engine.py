"""
Speech-to-Text Engine for Interview Answer Transcription.
Uses faster-whisper for fast, local, offline CPU/GPU transcription.
Handles model loading, caching, and graceful failure recovery.
"""

import os
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Default model configuration
DEFAULT_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base.en")
DEFAULT_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
DEFAULT_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# Global cached model instance
_cached_model = None
_model_load_error: Optional[str] = None


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""
    pass


def get_whisper_model(
    model_size: str = DEFAULT_MODEL_SIZE,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE_TYPE
):
    """
    Get or lazily initialize the cached WhisperModel instance.
    Raises TranscriptionError if faster-whisper fails to load or download.
    """
    global _cached_model, _model_load_error
    if _cached_model is not None:
        return _cached_model

    try:
        from faster_whisper import WhisperModel

        logger.info(f"Loading faster-whisper model '{model_size}' on device '{device}' ({compute_type})...")
        _cached_model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_load_error = None
        logger.info("faster-whisper model loaded successfully.")
        return _cached_model
    except Exception as e:
        _model_load_error = str(e)
        logger.error(f"Failed to load faster-whisper model '{model_size}': {e}", exc_info=True)
        raise TranscriptionError(
            f"Speech-to-Text engine unavailable. Could not load model '{model_size}': {e}"
        ) from e


def is_stt_available() -> bool:
    """Check if the STT engine can be initialized."""
    try:
        get_whisper_model()
        return True
    except Exception:
        return False


def transcribe_audio(
    audio_path: str,
    model_size: str = DEFAULT_MODEL_SIZE,
    beam_size: int = 5,
    vad_filter: bool = True
) -> Dict[str, Any]:
    """
    Transcribe an audio file using faster-whisper.

    Args:
        audio_path: Absolute or relative path to the audio file (e.g. 16kHz WAV).
        model_size: Model size string (default: 'base.en').
        beam_size: Beam search width (default: 5).
        vad_filter: Whether to apply faster-whisper's internal VAD filter.

    Returns:
        Dict containing:
            - text: Consolidated transcript string.
            - language: Detected language code.
            - language_probability: Confidence of detected language.
            - duration: Total duration reported by Whisper.
            - segments: List of segment dicts with start, end, text, and avg_logprob.

    Raises:
        TranscriptionError: On missing file, decoding failure, or model inference error.
    """
    if not os.path.exists(audio_path):
        raise TranscriptionError(f"Audio file not found: {audio_path}")

    model = get_whisper_model(model_size=model_size)

    try:
        segments_gen, info = model.transcribe(
            audio_path,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=False
        )

        segments: List[Dict[str, Any]] = []
        transcript_parts: List[str] = []

        for seg in segments_gen:
            clean_text = seg.text.strip()
            if clean_text:
                transcript_parts.append(clean_text)
            segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": clean_text,
                "avg_logprob": round(seg.avg_logprob, 3)
            })

        consolidated_text = " ".join(transcript_parts).strip()

        return {
            "text": consolidated_text,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
            "segments": segments
        }
    except Exception as e:
        logger.error(f"Error transcribing audio {audio_path}: {e}", exc_info=True)
        raise TranscriptionError(f"Transcription failed: {str(e)}") from e
