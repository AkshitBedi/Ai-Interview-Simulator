import re
import math
import wave
import io
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np


@dataclass
class AudioSignalMetrics:
    """Acoustic measurements derived directly from raw audio waveform samples."""
    audio_duration_seconds: float
    speaking_duration_seconds: float
    pause_duration_seconds: float
    pause_count: int
    average_pause_duration: float
    long_pause_count: int
    phonation_ratio: float
    sample_rate: int
    num_samples: int


@dataclass
class TranscriptDeliveryMetrics:
    """Linguistic and pacing measurements derived from the transcribed text."""
    word_count: int
    speaking_rate_wpm: float
    articulation_rate_wpm: float
    filler_word_count: int
    filler_rate: float
    filler_breakdown: dict = field(default_factory=dict)
    repeated_words_count: int = 0


@dataclass
class CommunicationAnalysisResult:
    """Combined communication intelligence report with deterministic delivery score."""
    # Raw Signal Metrics
    audio_duration_seconds: float
    speaking_duration_seconds: float
    pause_duration_seconds: float
    pause_count: int
    average_pause_duration: float
    long_pause_count: int
    phonation_ratio: float
    
    # Raw Transcript Metrics
    word_count: int
    speaking_rate_wpm: float
    articulation_rate_wpm: float
    filler_word_count: int
    filler_rate: float
    filler_breakdown: dict
    repeated_words_count: int
    
    # Deterministic Scoring & Coaching
    delivery_score: int
    delivery_feedback: str


# ---------------------------------------------------------------------------
# 1. Raw Waveform Processing & Signal Analysis
# ---------------------------------------------------------------------------

def parse_wav_samples(audio_bytes_or_path) -> tuple[np.ndarray, int]:
    """
    Parses a standard RIFF PCM WAV file using Python's built-in wave module and numpy.
    Converts multi-channel to mono (if applicable) and normalizes samples to [-1.0, 1.0].
    
    Returns:
        (samples_float32, sample_rate)
    """
    if isinstance(audio_bytes_or_path, (str, Path)):
        wf = wave.open(str(audio_bytes_or_path), "rb")
    elif isinstance(audio_bytes_or_path, (bytes, bytearray)):
        wf = wave.open(io.BytesIO(audio_bytes_or_path), "rb")
    elif hasattr(audio_bytes_or_path, "read"):
        wf = wave.open(audio_bytes_or_path, "rb")
    else:
        raise ValueError("Unsupported audio input type for parse_wav_samples.")

    with wf:
        num_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        num_frames = wf.getnframes()
        raw_bytes = wf.readframes(num_frames)

    # Convert raw bytes based on sample width
    if sampwidth == 2:
        # 16-bit PCM
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 1:
        # 8-bit unsigned PCM
        samples = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 4:
        # 32-bit float or int
        samples = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes.")

    # Convert stereo/multi-channel to mono
    if num_channels > 1:
        samples = samples.reshape(-1, num_channels).mean(axis=1)

    return samples, sample_rate


def analyze_audio_waveform(
    samples: np.ndarray,
    sample_rate: int,
    frame_ms: float = 30.0,
    hop_ms: float = 10.0,
    min_pause_ms: float = 300.0,
    long_pause_ms: float = 1500.0
) -> AudioSignalMetrics:
    """
    Performs Voice Activity Detection (VAD) and silence/pause analysis on raw audio samples.
    
    1. Windows audio into short frames (default 30ms with 10ms hop).
    2. Calculates Root Mean Square (RMS) energy and decibels (dBFS) for each frame.
    3. Dynamically estimates room ambient noise floor from the 10th percentile energy.
    4. Identifies continuous silence intervals >= min_pause_ms.
    5. Calculates speaking time, pause durations, and phonation ratio.
    """
    num_samples = len(samples)
    total_duration = num_samples / max(sample_rate, 1)

    if total_duration <= 0.0 or num_samples == 0:
        return AudioSignalMetrics(
            audio_duration_seconds=0.0,
            speaking_duration_seconds=0.0,
            pause_duration_seconds=0.0,
            pause_count=0,
            average_pause_duration=0.0,
            long_pause_count=0,
            phonation_ratio=0.0,
            sample_rate=sample_rate,
            num_samples=0
        )

    frame_len = int((frame_ms / 1000.0) * sample_rate)
    hop_len = int((hop_ms / 1000.0) * sample_rate)

    if frame_len <= 0 or hop_len <= 0 or num_samples < frame_len:
        return AudioSignalMetrics(
            audio_duration_seconds=round(total_duration, 2),
            speaking_duration_seconds=round(total_duration, 2),
            pause_duration_seconds=0.0,
            pause_count=0,
            average_pause_duration=0.0,
            long_pause_count=0,
            phonation_ratio=1.0,
            sample_rate=sample_rate,
            num_samples=num_samples
        )

    # Window frames and compute frame RMS energy
    num_frames = 1 + (num_samples - frame_len) // hop_len
    # Create strided view of frames
    shape = (num_frames, frame_len)
    strides = (samples.strides[0] * hop_len, samples.strides[0])
    frames = np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides)

    # RMS of each frame
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    dbfs = 20.0 * np.log10(rms)

    # Adaptive noise floor: 15th percentile energy of the recording
    ambient_noise_floor = float(np.percentile(dbfs, 15))
    # Threshold: noise floor + 10 dBFS, bounded between [-55 dBFS, -30 dBFS]
    vad_threshold = max(-55.0, min(-30.0, ambient_noise_floor + 10.0))

    # Mark frames as voice (True) or silence (False)
    is_speech = dbfs >= vad_threshold

    # Group consecutive silence frames into intervals
    frame_step_sec = hop_ms / 1000.0
    min_pause_frames = int(min_pause_ms / hop_ms)
    long_pause_frames = int(long_pause_ms / hop_ms)

    pauses = []
    current_silence_len = 0

    for active in is_speech:
        if not active:
            current_silence_len += 1
        else:
            if current_silence_len >= min_pause_frames:
                pauses.append(current_silence_len * frame_step_sec)
            current_silence_len = 0

    # Catch trailing silence
    if current_silence_len >= min_pause_frames:
        pauses.append(current_silence_len * frame_step_sec)

    pause_count = len(pauses)
    pause_duration = sum(pauses)
    average_pause = (pause_duration / pause_count) if pause_count > 0 else 0.0
    long_pause_count = sum(1 for p in pauses if p >= (long_pause_ms / 1000.0))

    speaking_duration = max(0.0, total_duration - pause_duration)
    phonation_ratio = (speaking_duration / total_duration) if total_duration > 0 else 0.0

    return AudioSignalMetrics(
        audio_duration_seconds=round(total_duration, 2),
        speaking_duration_seconds=round(speaking_duration, 2),
        pause_duration_seconds=round(pause_duration, 2),
        pause_count=pause_count,
        average_pause_duration=round(average_pause, 2),
        long_pause_count=long_pause_count,
        phonation_ratio=round(phonation_ratio, 3),
        sample_rate=sample_rate,
        num_samples=num_samples
    )


# ---------------------------------------------------------------------------
# 2. Linguistic Transcript Delivery Analysis
# ---------------------------------------------------------------------------

# Single-token verbal fillers commonly observed in technical interviews
SINGLE_FILLERS = {
    "um", "umm", "uh", "uhh", "er", "err", "ah", "ahh",
    "like", "basically", "actually", "literally", "honestly"
}

# Multi-word filler expressions
MULTI_FILLERS = [
    r"\byou know\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\bi mean\b",
    r"\bas in\b"
]


def analyze_transcript_delivery(
    transcript: str,
    audio_duration_seconds: float,
    speaking_duration_seconds: float
) -> TranscriptDeliveryMetrics:
    """
    Computes linguistic pacing and delivery mechanics from the transcribed text:
    - Word count & words per minute (WPM)
    - Articulation rate (WPM over active speaking time)
    - Single and multi-word filler frequency and rates
    - Consecutive repeated words (hesitation stutters)
    """
    text = transcript.strip().lower()
    words = re.findall(r"\b[a-zA-Z']+\b", text)
    word_count = len(words)

    # 1. Speaking rate & Articulation rate
    speaking_rate_wpm = round((word_count / max(audio_duration_seconds, 1.0)) * 60.0, 1)
    articulation_rate_wpm = round((word_count / max(speaking_duration_seconds, 1.0)) * 60.0, 1)

    # 2. Filler word counts
    filler_breakdown = {}

    # Check multi-word fillers first
    for pattern in MULTI_FILLERS:
        matches = len(re.findall(pattern, text))
        if matches > 0:
            clean_name = pattern.replace(r"\b", "")
            filler_breakdown[clean_name] = matches

    # Check single-word fillers
    for word in words:
        if word in SINGLE_FILLERS:
            filler_breakdown[word] = filler_breakdown.get(word, 0) + 1

    filler_count = sum(filler_breakdown.values())
    filler_rate = round((filler_count / max(word_count, 1)) * 100.0, 1)

    # 3. Repeated consecutive words (e.g., "the the", "I I")
    repeated_words_count = 0
    for i in range(len(words) - 1):
        if words[i] == words[i + 1] and len(words[i]) > 1:
            repeated_words_count += 1

    return TranscriptDeliveryMetrics(
        word_count=word_count,
        speaking_rate_wpm=speaking_rate_wpm,
        articulation_rate_wpm=articulation_rate_wpm,
        filler_word_count=filler_count,
        filler_rate=filler_rate,
        filler_breakdown=filler_breakdown,
        repeated_words_count=repeated_words_count
    )


# ---------------------------------------------------------------------------
# 3. Deterministic Delivery Scoring Formula (Modification 3)
# ---------------------------------------------------------------------------

def calculate_delivery_score(
    speaking_rate_wpm: float,
    filler_rate: float,
    long_pause_count: int,
    phonation_ratio: float,
    repeated_words_count: int,
    word_count: int
) -> tuple[int, str]:
    """
    Calculates a deterministic delivery score (1 to 10) based on transparent penalties.
    
    FORMULA SPECIFICATION:
    -----------------------
    Base Score: 10.0 points
    
    1. Speaking Rate (WPM):
       - 115 <= WPM <= 165: 0 penalty (Ideal professional technical interview pace)
       - 90 <= WPM < 115 OR 165 < WPM <= 185: -1.0 point (Slightly slow or rushed)
       - WPM < 90 OR WPM > 185: -2.5 points (Significantly too slow or too fast)
       
    2. Filler Word Density (filler_rate %):
       - filler_rate <= 2.5%: 0 penalty (Clean speech)
       - 2.5% < filler_rate <= 5.0%: -1.0 point (Minor filler usage)
       - 5.0% < filler_rate <= 8.0%: -2.0 points (Frequent fillers, noticeable hesitation)
       - filler_rate > 8.0%: -3.0 points (Heavy filler dependency)
       
    3. Hesitation & Pauses:
       - -0.75 points per long pause (>= 1.5 seconds), capped at -2.0 points
       - Phonation Ratio:
         * 0.60 <= ratio <= 0.85: 0 penalty (Natural breathing and cadence)
         * ratio < 0.50: -1.5 points (Excessive silence, > 50% of time idle)
         * ratio > 0.95: -1.0 point (Rushed/breathless, no natural pauses)
         
    4. Stutters / Repeated Words:
       - -0.5 points per repeated word instance, capped at -1.5 points
       
    Clamp Range: [1, 10]
    """
    if word_count < 5:
        return 2, "Response was too brief or incomplete to measure communication delivery effectively."

    score = 10.0
    feedback_notes = []

    # 1. Pace penalty
    if 115.0 <= speaking_rate_wpm <= 165.0:
        feedback_notes.append(f"Ideal speaking pace ({speaking_rate_wpm} WPM).")
    elif 90.0 <= speaking_rate_wpm < 115.0:
        score -= 1.0
        feedback_notes.append(f"Pace is slightly slow ({speaking_rate_wpm} WPM). Aim for 120-160 WPM for technical flow.")
    elif 165.0 < speaking_rate_wpm <= 185.0:
        score -= 1.0
        feedback_notes.append(f"Pace is slightly fast ({speaking_rate_wpm} WPM). Slow down slightly to ensure clarity.")
    elif speaking_rate_wpm < 90.0:
        score -= 2.5
        feedback_notes.append(f"Speaking rate was slow ({speaking_rate_wpm} WPM), indicating hesitation.")
    else:
        score -= 2.5
        feedback_notes.append(f"Speaking rate was too fast ({speaking_rate_wpm} WPM), which can hinder comprehension.")

    # 2. Filler word penalty
    if filler_rate <= 2.5:
        feedback_notes.append("Clear delivery with minimal filler words.")
    elif filler_rate <= 5.0:
        score -= 1.0
        feedback_notes.append(f"Moderate filler words detected ({filler_rate}% of words). Try replacing 'um'/'uh' with brief silent pauses.")
    elif filler_rate <= 8.0:
        score -= 2.0
        feedback_notes.append(f"Frequent filler words ({filler_rate}%). Focus on conscious pauses rather than verbal placeholders.")
    else:
        score -= 3.0
        feedback_notes.append(f"High filler density ({filler_rate}%). Practice structured answering to reduce verbal hesitations.")

    # 3. Hesitation & Pauses
    if long_pause_count > 0:
        pause_penalty = min(2.0, long_pause_count * 0.75)
        score -= pause_penalty
        feedback_notes.append(f"Encountered {long_pause_count} long pause(s) (>1.5s).")

    if phonation_ratio < 0.50:
        score -= 1.5
        feedback_notes.append(f"Significant silent intervals ({round((1 - phonation_ratio) * 100)}% of duration was silence).")
    elif phonation_ratio > 0.95:
        score -= 1.0
        feedback_notes.append("Delivery was breathless with almost no pauses. Remember to pause naturally between thoughts.")

    # 4. Repeated words
    if repeated_words_count > 0:
        rep_penalty = min(1.5, repeated_words_count * 0.5)
        score -= rep_penalty
        feedback_notes.append(f"Detected {repeated_words_count} word repetition(s).")

    final_score = int(max(1, min(10, round(score))))
    feedback_str = " ".join(feedback_notes)

    return final_score, feedback_str


# ---------------------------------------------------------------------------
# 4. Master Analysis Pipeline
# ---------------------------------------------------------------------------

def process_audio_and_transcript(
    audio_bytes_or_path,
    transcript: str
) -> CommunicationAnalysisResult:
    """
    Main entry point for Phase 4 communication analysis:
    1. Parses audio waveform samples and sample rate.
    2. Runs acoustic signal processing for pause and speaking time extraction.
    3. Runs transcript NLP for filler and pacing metrics.
    4. Applies the deterministic delivery scoring rubric.
    """
    samples, sample_rate = parse_wav_samples(audio_bytes_or_path)

    sig = analyze_audio_waveform(samples, sample_rate)
    trn = analyze_transcript_delivery(
        transcript,
        audio_duration_seconds=sig.audio_duration_seconds,
        speaking_duration_seconds=sig.speaking_duration_seconds
    )

    score, feedback = calculate_delivery_score(
        speaking_rate_wpm=trn.speaking_rate_wpm,
        filler_rate=trn.filler_rate,
        long_pause_count=sig.long_pause_count,
        phonation_ratio=sig.phonation_ratio,
        repeated_words_count=trn.repeated_words_count,
        word_count=trn.word_count
    )

    return CommunicationAnalysisResult(
        audio_duration_seconds=sig.audio_duration_seconds,
        speaking_duration_seconds=sig.speaking_duration_seconds,
        pause_duration_seconds=sig.pause_duration_seconds,
        pause_count=sig.pause_count,
        average_pause_duration=sig.average_pause_duration,
        long_pause_count=sig.long_pause_count,
        phonation_ratio=sig.phonation_ratio,
        word_count=trn.word_count,
        speaking_rate_wpm=trn.speaking_rate_wpm,
        articulation_rate_wpm=trn.articulation_rate_wpm,
        filler_word_count=trn.filler_word_count,
        filler_rate=trn.filler_rate,
        filler_breakdown=trn.filler_breakdown,
        repeated_words_count=trn.repeated_words_count,
        delivery_score=score,
        delivery_feedback=feedback
    )
