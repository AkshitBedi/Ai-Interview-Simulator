"""
Comprehensive Phase 4 Verification Suite:
Speech-to-Text, Audio Signal Processing, Delivery Scoring, and Interview Session Audio Flow.
"""

import os
import io
import sys
import wave
import json
import tempfile
import unittest
import numpy as np

from pathlib import Path
REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.database import get_db, create_tables
from backend.audio_analyzer import (
    parse_wav_samples,
    analyze_audio_waveform,
    analyze_transcript_delivery,
    calculate_delivery_score,
    process_audio_and_transcript,
    AudioSignalMetrics,
    TranscriptDeliveryMetrics
)
from backend.speech_engine import (
    is_stt_available,
    transcribe_audio,
    TranscriptionError
)
from backend.interview_engine import (
    start_session,
    get_session_details,
    record_answer_and_advance,
    get_session_summary
)
from backend.evaluator import EvaluationResult
from backend.main import app
from fastapi.testclient import TestClient


def generate_synthetic_wav(
    tone_duration: float = 1.0,
    silence_duration: float = 1.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
    amplitude: float = 0.5
) -> bytes:
    """
    Generates a synthetic 16kHz 16-bit mono PCM WAV in memory.
    Structure: [Tone 1] -> [Silence] -> [Tone 2]
    Known properties:
      - Total duration = 2 * tone_duration + silence_duration
      - Speaking duration = 2 * tone_duration
      - Pause duration = silence_duration
      - Pause count = 1
    """
    t_tone = np.linspace(0, tone_duration, int(sample_rate * tone_duration), endpoint=False)
    tone_samples = (np.sin(2 * np.pi * frequency * t_tone) * amplitude).astype(np.float32)

    silence_samples = np.zeros(int(sample_rate * silence_duration), dtype=np.float32)

    all_samples = np.concatenate([tone_samples, silence_samples, tone_samples])
    pcm16 = (all_samples * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())

    return buf.getvalue()


class TestAudioSignalProcessing(unittest.TestCase):
    """Unit tests for acoustic signal processing and pause detection."""

    def test_synthetic_wav_pause_detection(self):
        wav_bytes = generate_synthetic_wav(tone_duration=1.0, silence_duration=1.0, sample_rate=16000)
        samples, sr = parse_wav_samples(wav_bytes)

        self.assertEqual(sr, 16000)
        self.assertAlmostEqual(len(samples) / sr, 3.0, places=1)

        metrics = analyze_audio_waveform(samples, sr, min_pause_ms=300.0, long_pause_ms=1500.0)

        # Total duration ~ 3.0s
        self.assertAlmostEqual(metrics.audio_duration_seconds, 3.0, delta=0.1)
        # Speaking duration ~ 2.0s
        self.assertAlmostEqual(metrics.speaking_duration_seconds, 2.0, delta=0.2)
        # Pause duration ~ 1.0s
        self.assertAlmostEqual(metrics.pause_duration_seconds, 1.0, delta=0.2)
        # Exactly 1 pause
        self.assertEqual(metrics.pause_count, 1)
        # No long pause since pause is 1.0s < 1.5s
        self.assertEqual(metrics.long_pause_count, 0)
        # Phonation ratio ~ 2.0 / 3.0 = 0.67
        self.assertAlmostEqual(metrics.phonation_ratio, 0.67, delta=0.1)

    def test_long_pause_detection(self):
        wav_bytes = generate_synthetic_wav(tone_duration=0.5, silence_duration=2.0, sample_rate=16000)
        samples, sr = parse_wav_samples(wav_bytes)
        metrics = analyze_audio_waveform(samples, sr, min_pause_ms=300.0, long_pause_ms=1500.0)

        self.assertEqual(metrics.pause_count, 1)
        self.assertEqual(metrics.long_pause_count, 1)  # 2.0s > 1.5s
        self.assertAlmostEqual(metrics.pause_duration_seconds, 2.0, delta=0.2)


class TestTranscriptDeliveryNLP(unittest.TestCase):
    """Unit tests for lexical pacing, filler detection, and deterministic delivery scoring."""

    def test_filler_word_detection(self):
        transcript = "Um, basically, a hash table is, like, an efficient key-value store, you know, with O(1) lookups."
        metrics = analyze_transcript_delivery(transcript, audio_duration_seconds=10.0, speaking_duration_seconds=8.0)

        self.assertIn("um", metrics.filler_breakdown)
        self.assertIn("basically", metrics.filler_breakdown)
        self.assertIn("like", metrics.filler_breakdown)
        self.assertIn("you know", metrics.filler_breakdown)
        self.assertEqual(metrics.filler_word_count, 4)
        self.assertGreater(metrics.filler_rate, 10.0)

    def test_repeated_word_stutters(self):
        transcript = "The the main advantage of of indexing is speed."
        metrics = analyze_transcript_delivery(transcript, audio_duration_seconds=5.0, speaking_duration_seconds=4.0)

        self.assertEqual(metrics.repeated_words_count, 2)

    def test_deterministic_scoring_formula(self):
        # Perfect response: 140 WPM, 1.5% fillers, 0 long pauses, 0.75 phonation ratio, 0 repetitions
        score, feedback = calculate_delivery_score(
            speaking_rate_wpm=140.0,
            filler_rate=1.5,
            long_pause_count=0,
            phonation_ratio=0.75,
            repeated_words_count=0,
            word_count=50
        )
        self.assertEqual(score, 10)
        self.assertIn("Ideal speaking pace", feedback)
        self.assertIn("Clear delivery", feedback)

        # Response with flaws: slow pace (80 WPM), heavy fillers (9%), 2 long pauses, 2 repetitions
        score_flawed, feedback_flawed = calculate_delivery_score(
            speaking_rate_wpm=80.0,
            filler_rate=9.0,
            long_pause_count=2,
            phonation_ratio=0.45,
            repeated_words_count=2,
            word_count=40
        )
        # Base 10 - 2.5 (WPM < 90) - 3.0 (fillers > 8%) - 1.5 (long pauses) - 1.5 (silence < 0.5) - 1.0 (reps) = 0.5 -> clamped to 1
        self.assertLessEqual(score_flawed, 3)
        self.assertIn("slow", feedback_flawed)
        self.assertIn("filler", feedback_flawed.lower())


class TestDatabaseSpeechAnalytics(unittest.TestCase):
    """Tests SQLite persistence of speech analytics and foreign key constraints."""

    def test_speech_analytics_persistence(self):
        conn = get_db()
        create_tables()

        # Insert question and answer
        q_row = conn.execute("SELECT id FROM questions LIMIT 1").fetchone()
        self.assertIsNotNone(q_row)

        cursor = conn.execute(
            "INSERT INTO answers (question_id, answer) VALUES (?, ?)",
            (q_row["id"], "This is a test spoken answer for speech analytics.")
        )
        answer_id = cursor.lastrowid

        # Insert speech analytics
        conn.execute(
            """
            INSERT INTO speech_analytics (
                answer_id, audio_duration_seconds, speaking_duration_seconds,
                pause_duration_seconds, pause_count, average_pause_duration,
                long_pause_count, phonation_ratio, speaking_rate_wpm,
                articulation_rate_wpm, filler_word_count, filler_rate,
                filler_breakdown, repeated_words_count, delivery_score,
                delivery_feedback
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                answer_id, 12.5, 9.8, 2.7, 3, 0.9, 0, 0.784,
                135.0, 160.0, 2, 2.4, json.dumps({"um": 2}), 0, 9,
                "Clear and confident delivery."
            )
        )
        conn.commit()

        # Retrieve and verify
        row = conn.execute("SELECT * FROM speech_analytics WHERE answer_id = ?", (answer_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["answer_id"], answer_id)
        self.assertEqual(row["delivery_score"], 9)
        self.assertEqual(row["filler_word_count"], 2)
        breakdown = json.loads(row["filler_breakdown"])
        self.assertEqual(breakdown.get("um"), 2)

        conn.close()


class TestFastAPISpeechEndpoints(unittest.TestCase):
    """Tests FastAPI HTTP routes for speech status, standalone analysis, and audio sessions."""

    def setUp(self):
        self.client = TestClient(app)

    def test_speech_status_endpoint(self):
        resp = self.client.get("/speech/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stt_available", data)
        self.assertEqual(data["engine"], "faster-whisper")
        self.assertTrue(data["stt_available"])

    def test_speech_analyze_standalone_with_provided_transcript(self):
        wav_bytes = generate_synthetic_wav(tone_duration=1.0, silence_duration=1.0, sample_rate=16000)
        files = {"file": ("test.wav", wav_bytes, "audio/wav")}
        data = {"expected_transcript": "A binary search tree maintains sorted keys for logarithmic search time."}

        resp = self.client.post("/speech/analyze", files=files, data=data)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertIn("delivery_score", body)
        self.assertIn("acoustic_signal", body)
        self.assertIn("transcript_delivery", body)
        self.assertEqual(body["acoustic_signal"]["pause_count"], 1)
        self.assertGreater(body["delivery_score"], 0)

    def test_session_audio_answer_flow(self):
        # 1. Create a session
        create_resp = self.client.post("/sessions", json={"max_turns": 3})
        self.assertEqual(create_resp.status_code, 201)
        session_id = create_resp.json()["session_id"]

        # 2. Submit audio answer via multipart form
        wav_bytes = generate_synthetic_wav(tone_duration=1.5, silence_duration=0.5, sample_rate=16000)
        files = {"file": ("answer.wav", wav_bytes, "audio/wav")}

        # Since synthetic tones do not contain English words, Whisper would return empty/music transcript.
        # We test that the endpoint rejects empty speech with 422:
        resp_empty = self.client.post(f"/sessions/{session_id}/answer-audio", files=files)
        self.assertEqual(resp_empty.status_code, 422)
        self.assertIn("No intelligible speech", resp_empty.json()["detail"])

        # 3. Test text answer still works in parallel
        text_resp = self.client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "A binary search tree has left children less than parent and right children greater than parent."}
        )
        self.assertEqual(text_resp.status_code, 200)
        eval_data = text_resp.json()["evaluated_turn"]
        self.assertIn("score", eval_data)
        self.assertIn("feedback", eval_data)

        # 4. Check session details
        details_resp = self.client.get(f"/sessions/{session_id}")
        self.assertEqual(details_resp.status_code, 200)
        self.assertEqual(len(details_resp.json()["turns"]), 2)


if __name__ == "__main__":
    unittest.main()
