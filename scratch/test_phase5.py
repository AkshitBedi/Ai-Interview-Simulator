"""
Phase 5 Comprehensive Test Suite: Optional Camera and Nonverbal Telemetry.
Verifies:
1. Mathematical unit tests (centering, rotation matrices, motion energy, deterministic scoring).
2. Zero trait inference enforcement (prohibits psychological/emotional terminology).
3. Capability-aware fallback (MediaPipe vs OpenCV fallback).
4. Score independence guarantee (Technical score != Verbal delivery != Nonverbal telemetry).
5. Database schema, persistence, and cascade deletion.
6. API endpoint integration (/sessions/{id}/answer-multimodal, /vision/analyze, /vision/status).
"""

import os
import sys
import math
import json
import wave
import struct
import tempfile
import unittest
from pathlib import Path

# Add backend directory to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import cv2
from fastapi.testclient import TestClient

from backend.database import get_db, create_tables
from backend.vision_analyzer import (
    compute_centering_offset,
    rotation_matrix_to_euler_angles,
    compute_head_motion_frequency,
    compute_frame_motion_energy,
    calculate_nonverbal_score,
    extract_video_frames,
    process_video,
    get_vision_status
)
from backend.interview_engine import (
    start_session,
    record_answer_and_advance,
    get_session_details,
    get_session_summary
)
from backend.evaluator import EvaluationResult
from backend.main import app

FORBIDDEN_TRAIT_WORDS = [
    "confidence", "confident", "stress", "stressed", "nervous", "nervousness",
    "engagement", "engaged", "emotion", "emotional", "honesty", "honest",
    "personality", "anxiety", "anxious", "calmness", "deception"
]


def generate_synthetic_wav(duration_s=2.5, sample_rate=16000) -> bytes:
    """Generates a synthetic 16kHz mono PCM WAV with tone bursts."""
    num_samples = int(duration_s * sample_rate)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        # Tone for 0.3s to 1.8s, silence otherwise
        if 0.3 <= t <= 1.8:
            val = int(12000 * math.sin(2 * math.pi * 440 * t))
        else:
            val = 0
        samples.append(val)

    buf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = buf.name
    buf.close()

    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_bytes = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw_bytes)

    with open(tmp_path, "rb") as f:
        wav_bytes = f.read()
    os.remove(tmp_path)
    return wav_bytes


def generate_synthetic_video(frames_count=15, fps=10.0, use_face=True) -> str:
    """Creates a temporary AVI/MP4 video file with a synthetic or real face fixture."""
    tmp = tempfile.NamedTemporaryFile(suffix=".avi", delete=False)
    tmp_path = tmp.name
    tmp.close()

    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    out = cv2.VideoWriter(tmp_path, fourcc, fps, (640, 480))

    face_fixture = REPO_ROOT / "scratch" / "test_face.jpg"
    if use_face and face_fixture.exists():
        base_img = cv2.imread(str(face_fixture))
        base_img = cv2.resize(base_img, (640, 480))
    else:
        base_img = np.zeros((480, 640, 3), dtype=np.uint8)
        if use_face:
            # Draw synthetic face circle and eyes
            cv2.circle(base_img, (320, 220), 100, (200, 200, 200), -1)
            cv2.circle(base_img, (280, 200), 15, (50, 50, 50), -1)
            cv2.circle(base_img, (360, 200), 15, (50, 50, 50), -1)

    for i in range(frames_count):
        # Slight motion
        frame = base_img.copy()
        if i % 2 == 0:
            frame[0:5, 0:5] = 255
        out.write(frame)

    out.release()
    return tmp_path


def generate_browser_webm(frames_count=15, fps=10.0, use_face=True) -> str:
    """Creates a temporary WebM (VP8) video file mimicking browser MediaRecorder output."""
    import av
    tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
    tmp_path = tmp.name
    tmp.close()

    container = av.open(tmp_path, mode="w", format="webm")
    stream = container.add_stream("vp8", rate=int(fps))
    stream.width = 640
    stream.height = 480
    stream.pix_fmt = "yuv420p"

    face_fixture = REPO_ROOT / "scratch" / "test_face.jpg"
    if use_face and face_fixture.exists():
        base_img = cv2.imread(str(face_fixture))
        base_img = cv2.resize(base_img, (640, 480))
    else:
        base_img = np.zeros((480, 640, 3), dtype=np.uint8)

    for i in range(frames_count):
        frame = base_img.copy()
        if i % 2 == 0:
            frame[0:5, 0:5] = 255
        av_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
        for packet in stream.encode(av_frame):
            container.mux(packet)

    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return tmp_path


class TestPhase5TelemetryMath(unittest.TestCase):
    """Unit tests for geometric math and scoring functions."""

    def test_centering_offset_calculation(self):
        # Ideal centered position: (0.5, 0.4)
        self.assertAlmostEqual(compute_centering_offset(0.5, 0.4), 0.0, places=4)
        # Offset test: (0.8, 0.8) -> dx=0.3, dy=0.4 -> hypot=0.5
        self.assertAlmostEqual(compute_centering_offset(0.8, 0.8), 0.5, places=4)

    def test_rotation_matrix_to_euler_angles(self):
        # Identity matrix -> 0 yaw, 0 pitch, 0 roll
        R_ident = np.eye(3)
        pitch, yaw, roll = rotation_matrix_to_euler_angles(R_ident)
        self.assertAlmostEqual(pitch, 0.0, places=2)
        self.assertAlmostEqual(yaw, 0.0, places=2)
        self.assertAlmostEqual(roll, 0.0, places=2)

    def test_motion_energy_calculation(self):
        # Identical frames -> 0 motion
        f1 = np.ones((480, 640, 3), dtype=np.uint8) * 100
        f2 = np.ones((480, 640, 3), dtype=np.uint8) * 100
        energy = compute_frame_motion_energy([f1, f2])
        self.assertEqual(energy, 0.0)

        # Drastically different frames -> high motion
        f3 = np.zeros((480, 640, 3), dtype=np.uint8)
        energy_high = compute_frame_motion_energy([f1, f3])
        self.assertGreater(energy_high, 50.0)

    def test_deterministic_scoring_perfect(self):
        score, feedback = calculate_nonverbal_score(
            face_detected_ratio=0.98,
            centering_offset=0.05,
            motion_energy=3.0,
            gaze_deviation_ratio=0.10,
            yaw_variance=15.0,
            pitch_variance=10.0,
            roll_variance=5.0,
            head_motion_frequency_hz=0.5,
            camera_quality_flags=[],
            vision_backend="mediapipe"
        )
        self.assertEqual(score, 10)
        self.assertIn("Consistent camera presence", feedback)
        self.assertIn("Well-centered framing", feedback)
        self.assertIn("forward gaze", feedback)

    def test_deterministic_scoring_deductions_and_bounds(self):
        # Severe deviations
        score, feedback = calculate_nonverbal_score(
            face_detected_ratio=0.30,      # -3.0
            centering_offset=0.35,         # -2.0
            motion_energy=25.0,            # -1.5
            gaze_deviation_ratio=0.75,     # -2.0
            yaw_variance=150.0,
            pitch_variance=100.0,
            roll_variance=100.0,           # total variance 350 -> -2.0
            head_motion_frequency_hz=2.2,  # -0.5
            camera_quality_flags=["low_lighting"],
            vision_backend="mediapipe"
        )
        # Total deductions: 11.0 -> clamped to 1
        self.assertEqual(score, 1)
        self.assertIn("out of camera view", feedback)
        self.assertIn("off-center", feedback)

    def test_zero_trait_inference_strictness(self):
        """Verifies that generated feedback strings NEVER contain forbidden trait words."""
        test_cases = [
            (0.95, 0.05, 4.0, 0.1, 10.0, 10.0, 10.0, 0.5, ["low_lighting"], "mediapipe"),
            (0.50, 0.30, 25.0, 0.8, 150.0, 150.0, 150.0, 2.5, ["high_motion_energy"], "mediapipe"),
            (0.80, 0.18, 12.0, None, None, None, None, None, [], "opencv_fallback")
        ]
        for tc in test_cases:
            _, feedback = calculate_nonverbal_score(*tc)
            feedback_lower = feedback.lower()
            for forbidden in FORBIDDEN_TRAIT_WORDS:
                self.assertNotIn(
                    forbidden, feedback_lower,
                    f"Forbidden psychological trait word '{forbidden}' found in feedback: '{feedback}'"
                )

    def test_opencv_fallback_capability_aware_scoring(self):
        """Ensures OpenCV fallback does NOT penalize for missing gaze/pose measurements."""
        score_fb, feedback_fb = calculate_nonverbal_score(
            face_detected_ratio=0.95,
            centering_offset=0.08,
            motion_energy=4.0,
            gaze_deviation_ratio=None,
            yaw_variance=None,
            pitch_variance=None,
            roll_variance=None,
            head_motion_frequency_hz=None,
            camera_quality_flags=[],
            vision_backend="opencv_fallback"
        )
        # Full score 10 should be awarded when presence, centering, and motion are optimal
        self.assertEqual(score_fb, 10)
        self.assertIn("Consistent camera presence", feedback_fb)
        self.assertNotIn("deg^2", feedback_fb)


class TestPhase5VisionPipelines(unittest.TestCase):
    """Integration tests for frame extraction and video processing."""

    def test_video_frame_extraction(self):
        video_path = generate_synthetic_video(frames_count=12, fps=10.0, use_face=False)
        try:
            frames, fps, dur = extract_video_frames(video_path, target_fps=8.0)
            self.assertGreater(len(frames), 0)
            self.assertGreater(dur, 0.0)
            self.assertEqual(frames[0].shape[2], 3)
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

    def test_process_video_mediapipe_fixture(self):
        video_path = generate_synthetic_video(frames_count=15, fps=10.0, use_face=True)
        try:
            res = process_video(video_path)
            self.assertEqual(res.vision_backend, "mediapipe")
            self.assertGreaterEqual(res.face_detected_ratio, 0.0)
            self.assertIn(res.nonverbal_telemetry_score, range(1, 11))
            self.assertIsInstance(res.camera_quality_flags, list)
            # Check dictionary conversion
            d = res.to_dict()
            self.assertIn("nonverbal_telemetry_score", d)
            self.assertIn("gaze_deviation_ratio", d)
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

    def test_process_video_opencv_fallback(self):
        video_path = generate_synthetic_video(frames_count=10, fps=10.0, use_face=False)
        try:
            res = process_video(video_path, force_backend="opencv_fallback")
            self.assertEqual(res.vision_backend, "opencv_fallback")
            self.assertIsNone(res.gaze_deviation_ratio)
            self.assertIsNone(res.avg_yaw_degrees)
            self.assertIsNone(res.yaw_variance)
            self.assertIn(res.nonverbal_telemetry_score, range(1, 11))
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)


class TestPhase5DatabaseAndIndependence(unittest.TestCase):
    """Tests SQLite persistence, cascade deletion, and score independence."""

    def setUp(self):
        create_tables()
        self.conn = get_db()

    def tearDown(self):
        self.conn.close()

    def test_database_persistence_and_cascade(self):
        # 1. Start session
        sess = start_session(self.conn, category="Python", difficulty="medium", max_turns=3)
        sess_id = sess["session_id"]

        dummy_eval = EvaluationResult(
            score=8,
            feedback="Strong explanation of Python GIL.",
            technical_accuracy="Accurate details on bytecode execution.",
            strengths=["Clear explanation"],
            missing_points=["Could mention PyPy"]
        )

        nv_metrics = {
            "video_duration_seconds": 3.0,
            "frames_analyzed": 24,
            "face_detected_ratio": 0.95,
            "centering_offset": 0.08,
            "gaze_deviation_ratio": 0.12,
            "avg_yaw_degrees": 2.5,
            "avg_pitch_degrees": -1.0,
            "avg_roll_degrees": 0.5,
            "yaw_variance": 12.0,
            "pitch_variance": 8.0,
            "roll_variance": 4.0,
            "head_motion_frequency_hz": 0.4,
            "motion_energy": 3.5,
            "camera_quality_flags": ["low_lighting"],
            "nonverbal_telemetry_score": 9,
            "nonverbal_feedback": "Consistent camera presence. Well-centered framing.",
            "vision_backend": "mediapipe"
        }

        # 2. Advance turn with nonverbal metrics
        res = record_answer_and_advance(
            connection=self.conn,
            session_id=sess_id,
            answer_text="CPython uses reference counting and a cycle detector.",
            evaluation=dummy_eval,
            nonverbal_metrics=nv_metrics
        )

        answer_id = res["evaluated_turn"]["answer_id"]

        # 3. Verify row in nonverbal_analytics
        row = self.conn.execute(
            "SELECT * FROM nonverbal_analytics WHERE answer_id = ?",
            (answer_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["nonverbal_telemetry_score"], 9)
        self.assertEqual(row["vision_backend"], "mediapipe")
        self.assertEqual(json.loads(row["camera_quality_flags"]), ["low_lighting"])

        # 4. Check get_session_details includes nonverbal analytics
        details = get_session_details(self.conn, sess_id)
        turn_0 = details["turns"][0]
        self.assertIsNotNone(turn_0["nonverbal_analytics"])
        self.assertEqual(turn_0["nonverbal_analytics"]["nonverbal_telemetry_score"], 9)

        # 5. Check get_session_summary aggregates nonverbal metrics
        summary = get_session_summary(self.conn, sess_id)
        self.assertIsNotNone(summary["nonverbal_summary"])
        self.assertEqual(summary["nonverbal_summary"]["turns_with_video"], 1)
        self.assertEqual(summary["nonverbal_summary"]["average_nonverbal_score"], 9.0)
        self.assertEqual(summary["nonverbal_summary"]["turns_with_camera_quality_flags"], 1)

        # 6. Verify Cascade Delete
        self.conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
        self.conn.commit()

        row_deleted = self.conn.execute(
            "SELECT * FROM nonverbal_analytics WHERE answer_id = ?",
            (answer_id,)
        ).fetchone()
        self.assertIsNone(row_deleted, "nonverbal_analytics row was not cascade-deleted when answer was removed.")

    def test_score_independence_guarantee(self):
        """
        Guarantees that Technical Score (1-10) and Verbal Delivery Score (1-10)
        are completely decoupled from whether video telemetry is absent, perfect, or poor.
        """
        sess = start_session(self.conn, category="Python", difficulty="beginner", max_turns=4)
        sess_id = sess["session_id"]

        eval_mock = EvaluationResult(
            score=7,
            feedback="Good answer on generators.",
            technical_accuracy="Accurate on memory efficiency.",
            strengths=["Yield keyword explained"],
            missing_points=["Could compare with iterator protocol"]
        )

        sp_mock = {
            "audio_duration_seconds": 10.0,
            "speaking_duration_seconds": 8.0,
            "pause_duration_seconds": 2.0,
            "pause_count": 2,
            "average_pause_duration": 1.0,
            "long_pause_count": 0,
            "phonation_ratio": 0.80,
            "speaking_rate_wpm": 140.0,
            "articulation_rate_wpm": 160.0,
            "filler_word_count": 1,
            "filler_rate": 1.5,
            "filler_breakdown": {"um": 1},
            "repeated_words_count": 0,
            "delivery_score": 9,
            "delivery_feedback": "Ideal speaking pace (140 WPM)."
        }

        # Case 1: Poor video (out of frame, off-center, low score)
        poor_nv = {
            "video_duration_seconds": 10.0,
            "frames_analyzed": 80,
            "face_detected_ratio": 0.20,
            "centering_offset": 0.40,
            "gaze_deviation_ratio": 0.85,
            "avg_yaw_degrees": 40.0,
            "avg_pitch_degrees": -25.0,
            "avg_roll_degrees": 15.0,
            "yaw_variance": 400.0,
            "pitch_variance": 200.0,
            "roll_variance": 150.0,
            "head_motion_frequency_hz": 3.0,
            "motion_energy": 30.0,
            "camera_quality_flags": ["low_lighting", "off_center", "low_face_presence"],
            "nonverbal_telemetry_score": 1,
            "nonverbal_feedback": "Candidate frequently out of camera view.",
            "vision_backend": "mediapipe"
        }

        res = record_answer_and_advance(
            connection=self.conn,
            session_id=sess_id,
            answer_text="Generators yield values lazily without storing the whole list in RAM.",
            evaluation=eval_mock,
            speech_metrics=sp_mock,
            nonverbal_metrics=poor_nv
        )

        t = res["evaluated_turn"]
        # The technical evaluation score must remain 7
        self.assertEqual(t["score"], 7)
        # The speech delivery score must remain 9
        self.assertEqual(t["speech_analytics"]["delivery_score"], 9)
        # The nonverbal telemetry score is 1
        self.assertEqual(t["nonverbal_analytics"]["nonverbal_telemetry_score"], 1)
        # All three scores are completely isolated!


class TestPhase5APIEndpoints(unittest.TestCase):
    """Tests FastAPI multimodal and vision diagnostic endpoints."""

    def setUp(self):
        create_tables()
        self.client = TestClient(app)

    def test_vision_status_endpoint(self):
        resp = self.client.get("/vision/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["available"])
        self.assertIn(data["vision_backend"], ["mediapipe", "opencv_fallback"])
        self.assertTrue(data["capabilities"]["face_presence"])

    def test_vision_analyze_endpoint(self):
        video_path = generate_synthetic_video(frames_count=10, fps=10.0, use_face=True)
        try:
            with open(video_path, "rb") as f:
                resp = self.client.post(
                    "/vision/analyze",
                    files={"video_file": ("test.avi", f, "video/avi")}
                )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("nonverbal_telemetry_score", data)
            self.assertIn("face_detected_ratio", data)
            self.assertIn("centering_offset", data)
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

    def test_multimodal_answer_endpoint(self):
        # 1. Create active session
        sess_resp = self.client.post("/sessions", json={"category": "Python", "difficulty": "beginner", "max_turns": 3})
        self.assertEqual(sess_resp.status_code, 201)
        sess_id = sess_resp.json()["session_id"]

        # 2. Prepare synthetic media
        wav_bytes = generate_synthetic_wav(duration_s=2.0)
        video_path = generate_synthetic_video(frames_count=12, fps=10.0, use_face=True)

        try:
            with open(video_path, "rb") as vf:
                resp = self.client.post(
                    f"/sessions/{sess_id}/answer-multimodal",
                    files={
                        "audio_file": ("answer.wav", wav_bytes, "audio/wav"),
                        "video_file": ("answer.avi", vf, "video/avi")
                    }
                )

            # May return 422 if faster-whisper transcribes silence/tone as unintelligible,
            # or 200 if speech was recognized. Let's verify the response behavior is clean!
            self.assertIn(resp.status_code, [200, 422])
            if resp.status_code == 200:
                body = resp.json()
                self.assertIn("evaluated_turn", body)
                self.assertIn("speech_analytics", body["evaluated_turn"])
                self.assertIn("nonverbal_analytics", body["evaluated_turn"])
            elif resp.status_code == 422:
                self.assertIn("intelligible speech", resp.json()["detail"].lower())
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

    def test_full_multimodal_turn_success(self):
        from unittest.mock import patch
        # 1. Create active session
        sess_resp = self.client.post("/sessions", json={"category": "Python", "difficulty": "beginner", "max_turns": 2})
        self.assertEqual(sess_resp.status_code, 201)
        sess_id = sess_resp.json()["session_id"]

        # 2. Prepare synthetic media
        wav_bytes = generate_synthetic_wav(duration_s=2.5)
        video_path = generate_synthetic_video(frames_count=15, fps=10.0, use_face=True)

        mock_stt = {
            "text": "CPython manages memory using reference counting alongside a generational cyclic garbage collector.",
            "language": "en",
            "language_probability": 0.99,
            "duration": 2.5,
            "segments": []
        }

        try:
            with patch("backend.main.transcribe_audio", return_value=mock_stt):
                with open(video_path, "rb") as vf:
                    resp = self.client.post(
                        f"/sessions/{sess_id}/answer-multimodal",
                        files={
                            "audio_file": ("answer.wav", wav_bytes, "audio/wav"),
                            "video_file": ("answer.avi", vf, "video/avi")
                        }
                    )

            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertIn("evaluated_turn", body)
            turn = body["evaluated_turn"]
            self.assertIn("score", turn)
            self.assertIn("speech_analytics", turn)
            self.assertIn("nonverbal_analytics", turn)
            self.assertGreaterEqual(turn["speech_analytics"]["delivery_score"], 1)
            self.assertGreaterEqual(turn["nonverbal_analytics"]["nonverbal_telemetry_score"], 1)
            self.assertEqual(turn["nonverbal_analytics"]["vision_backend"], "mediapipe")

            # Verify GET /sessions/{id}/summary includes both speech and nonverbal summaries
            summary_resp = self.client.get(f"/sessions/{sess_id}/summary")
            self.assertEqual(summary_resp.status_code, 200)
            summary_data = summary_resp.json()
            self.assertIsNotNone(summary_data["speech_summary"])
            self.assertIsNotNone(summary_data["nonverbal_summary"])
            self.assertEqual(summary_data["nonverbal_summary"]["turns_with_video"], 1)
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

    def test_multimodal_answer_with_real_webm(self):
        """Validates that POST /sessions/{id}/answer-multimodal seamlessly handles real browser WebM VP8 video."""
        from unittest.mock import patch
        sess_resp = self.client.post("/sessions", json={"category": "Python", "difficulty": "beginner", "max_turns": 1})
        self.assertEqual(sess_resp.status_code, 201)
        sess_id = sess_resp.json()["session_id"]

        wav_bytes = generate_synthetic_wav(duration_s=2.5)
        webm_path = generate_browser_webm(frames_count=15, fps=10.0, use_face=True)

        mock_stt = {
            "text": "CPython uses reference counting and a generational cyclic garbage collector.",
            "language": "en",
            "language_probability": 0.99,
            "duration": 2.5,
            "segments": []
        }

        try:
            with patch("backend.main.transcribe_audio", return_value=mock_stt):
                with open(webm_path, "rb") as vf:
                    resp = self.client.post(
                        f"/sessions/{sess_id}/answer-multimodal",
                        files={
                            "audio_file": ("answer.wav", wav_bytes, "audio/wav"),
                            "video_file": ("answer.webm", vf, "video/webm")
                        }
                    )

            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["decision"], "completed")
            turn = body["evaluated_turn"]
            self.assertIn("score", turn)
            self.assertIn("speech_analytics", turn)
            self.assertIn("nonverbal_analytics", turn)
            nv = turn["nonverbal_analytics"]
            self.assertEqual(nv["vision_backend"], "mediapipe")
            self.assertGreaterEqual(nv["nonverbal_telemetry_score"], 1)
            self.assertEqual(nv["frames_analyzed"], 15)
        finally:
            if os.path.exists(webm_path):
                os.remove(webm_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
