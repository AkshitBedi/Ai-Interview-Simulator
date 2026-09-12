"""
Computer Vision & Nonverbal Telemetry Analyzer.
Extracts objective camera-relative geometry, head pose, gaze deviation, and motion energy.
Zero trait or emotion inference: measures purely observable physical cues.
Provides capability-aware fallback between MediaPipe and OpenCV.
"""

import os
import math
import logging
import tempfile
import urllib.request
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

try:
    from .inference_gate import inference_guard, InferenceCapacityError
except (ImportError, ValueError):
    from inference_gate import inference_guard, InferenceCapacityError

# Constants
IDEAL_CENTER_X = 0.5
IDEAL_CENTER_Y = 0.4
DEFAULT_TARGET_FPS = 8.0

# Official MediaPipe Face Landmarker model URL and default cache path
MEDIAPIPE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "mediapipe"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "face_landmarker.task"

# Cached detector instance & backend status
_cached_detector = None
_vision_backend_active: Optional[str] = None
_init_attempted = False


class VisionProcessingError(Exception):
    """Raised when video decoding or frame analysis fails."""
    pass


@dataclass
class VisionTelemetryMetrics:
    """Quantitative measurements derived from video frames."""
    video_duration_seconds: float
    frames_analyzed: int
    face_detected_ratio: float
    centering_offset: float
    gaze_deviation_ratio: Optional[float]
    avg_yaw_degrees: Optional[float]
    avg_pitch_degrees: Optional[float]
    avg_roll_degrees: Optional[float]
    yaw_variance: Optional[float]
    pitch_variance: Optional[float]
    roll_variance: Optional[float]
    head_motion_frequency_hz: Optional[float]
    motion_energy: float
    camera_quality_flags: List[str] = field(default_factory=list)
    vision_backend: str = "mediapipe"


@dataclass
class NonverbalAnalysisResult:
    """Consolidated nonverbal telemetry report with deterministic score and neutral feedback."""
    video_duration_seconds: float
    frames_analyzed: int
    face_detected_ratio: float
    centering_offset: float
    gaze_deviation_ratio: Optional[float]
    avg_yaw_degrees: Optional[float]
    avg_pitch_degrees: Optional[float]
    avg_roll_degrees: Optional[float]
    yaw_variance: Optional[float]
    pitch_variance: Optional[float]
    roll_variance: Optional[float]
    head_motion_frequency_hz: Optional[float]
    motion_energy: float
    camera_quality_flags: List[str]
    nonverbal_telemetry_score: int
    nonverbal_feedback: str
    vision_backend: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_duration_seconds": self.video_duration_seconds,
            "frames_analyzed": self.frames_analyzed,
            "face_detected_ratio": self.face_detected_ratio,
            "centering_offset": self.centering_offset,
            "gaze_deviation_ratio": self.gaze_deviation_ratio,
            "avg_yaw_degrees": self.avg_yaw_degrees,
            "avg_pitch_degrees": self.avg_pitch_degrees,
            "avg_roll_degrees": self.avg_roll_degrees,
            "yaw_variance": self.yaw_variance,
            "pitch_variance": self.pitch_variance,
            "roll_variance": self.roll_variance,
            "head_motion_frequency_hz": self.head_motion_frequency_hz,
            "motion_energy": self.motion_energy,
            "camera_quality_flags": self.camera_quality_flags,
            "nonverbal_telemetry_score": self.nonverbal_telemetry_score,
            "nonverbal_feedback": self.nonverbal_feedback,
            "vision_backend": self.vision_backend
        }


# ---------------------------------------------------------------------------
# 1. MediaPipe Detector Management & Fallback
# ---------------------------------------------------------------------------

def ensure_model_file(model_path: Path = DEFAULT_MODEL_PATH) -> Optional[str]:
    """Ensures the face_landmarker.task model file is present, downloading if necessary."""
    if model_path.exists() and model_path.stat().st_size > 100_000:
        return str(model_path)

    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading MediaPipe FaceLandmarker model from {MEDIAPIPE_MODEL_URL}...")
        urllib.request.urlretrieve(MEDIAPIPE_MODEL_URL, str(model_path))
        if model_path.exists() and model_path.stat().st_size > 100_000:
            logger.info("FaceLandmarker model downloaded successfully.")
            return str(model_path)
    except Exception as e:
        logger.warning(f"Failed to download MediaPipe model: {e}")

    return None


def get_face_landmarker():
    """Lazily initializes the MediaPipe FaceLandmarker detector."""
    global _cached_detector, _vision_backend_active, _init_attempted
    if _cached_detector is not None:
        return _cached_detector

    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        model_path_str = ensure_model_file()
        if not model_path_str:
            raise RuntimeError("MediaPipe model file unavailable")

        base_options = python.BaseOptions(model_asset_path=model_path_str)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
            num_faces=1
        )
        _cached_detector = vision.FaceLandmarker.create_from_options(options)
        _vision_backend_active = "mediapipe"
        logger.info("MediaPipe FaceLandmarker initialized successfully.")
        return _cached_detector
    except Exception as e:
        logger.warning(f"MediaPipe FaceLandmarker unavailable ({e}). Falling back to OpenCV.")
        _cached_detector = None
        _vision_backend_active = "opencv_fallback"
        return None


def get_vision_status() -> Dict[str, Any]:
    """Returns the current vision backend status and capabilities."""
    detector = get_face_landmarker()
    backend = "mediapipe" if detector is not None else "opencv_fallback"
    return {
        "available": True,
        "vision_backend": backend,
        "capabilities": {
            "face_presence": True,
            "centering": True,
            "motion_energy": True,
            "gaze_deviation": (backend == "mediapipe"),
            "head_pose_angles": (backend == "mediapipe"),
            "head_motion_frequency": (backend == "mediapipe"),
        }
    }


# ---------------------------------------------------------------------------
# 2. Video Frame Extraction (Dual Engine: OpenCV + PyAV)
# ---------------------------------------------------------------------------

def extract_video_frames(
    video_bytes_or_path,
    target_fps: float = DEFAULT_TARGET_FPS
) -> Tuple[List[np.ndarray], float, float]:
    """
    Extracts RGB video frames from a file path or raw bytes.
    Subsamples frames to target_fps to ensure responsive processing.
    Uses cv2.VideoCapture with automatic fallback to PyAV (av) for robust decoding.

    Returns:
        (frames_rgb, sampled_fps, duration_seconds)
    """
    temp_file_created = False
    video_path = None

    if isinstance(video_bytes_or_path, (str, Path)):
        video_path = str(video_bytes_or_path)
    elif isinstance(video_bytes_or_path, (bytes, bytearray)):
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(video_bytes_or_path)
            video_path = tmp.name
            temp_file_created = True
    elif hasattr(video_bytes_or_path, "read"):
        content = video_bytes_or_path.read()
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(content)
            video_path = tmp.name
            temp_file_created = True
    else:
        raise VisionProcessingError("Unsupported video input type.")

    try:
        frames_rgb = []
        duration_seconds = 0.0
        fps = 0.0

        # Attempt 1: cv2.VideoCapture
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            native_fps = cap.get(cv2.CAP_PROP_FPS)
            if native_fps <= 0 or math.isnan(native_fps):
                native_fps = 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                duration_seconds = total_frames / native_fps

            step = max(1, int(round(native_fps / target_fps)))
            frame_idx = 0

            while cap.isOpened():
                ret, bgr_frame = cap.read()
                if not ret or bgr_frame is None:
                    break
                if frame_idx % step == 0:
                    rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
                    frames_rgb.append(rgb_frame)
                frame_idx += 1

            cap.release()

            if frame_idx > 0 and duration_seconds == 0.0:
                duration_seconds = frame_idx / native_fps

        # Attempt 2: PyAV (av) fallback if OpenCV returned 0 frames
        if len(frames_rgb) == 0:
            try:
                import av
                container = av.open(video_path)
                video_stream = next((s for s in container.streams if s.type == 'video'), None)
                if video_stream is not None:
                    native_fps = float(video_stream.average_rate or 25.0)
                    step = max(1, int(round(native_fps / target_fps)))
                    frame_idx = 0

                    for packet in container.demux(video_stream):
                        for frame in packet.decode():
                            if frame_idx % step == 0:
                                rgb_frame = frame.to_ndarray(format='rgb24')
                                frames_rgb.append(rgb_frame)
                            frame_idx += 1

                    container.close()
                    if frame_idx > 0:
                        duration_seconds = frame_idx / native_fps
            except Exception as e:
                logger.warning(f"PyAV fallback decoding failed: {e}")

        if not frames_rgb:
            raise VisionProcessingError("Could not extract any valid video frames from the upload.")

        effective_fps = len(frames_rgb) / max(0.1, duration_seconds)
        return frames_rgb, effective_fps, duration_seconds

    finally:
        if temp_file_created and video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 3. Geometric Telemetry Math Helpers
# ---------------------------------------------------------------------------

def rotation_matrix_to_euler_angles(R: np.ndarray) -> Tuple[float, float, float]:
    """
    Extracts Tait-Bryan Euler angles in degrees (pitch, yaw, roll) from a 3x3 rotation matrix.
    Pitch (X-axis, nodding up/down), Yaw (Y-axis, turning left/right), Roll (Z-axis, tilt).
    """
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6

    if not singular:
        pitch = math.atan2(R[2, 1], R[2, 2])
        yaw = math.atan2(-R[2, 0], sy)
        roll = math.atan2(R[1, 0], R[0, 0])
    else:
        pitch = math.atan2(-R[1, 2], R[1, 1])
        yaw = math.atan2(-R[2, 0], sy)
        roll = 0.0

    return math.degrees(pitch), math.degrees(yaw), math.degrees(roll)


def compute_centering_offset(x: float, y: float) -> float:
    """Computes Euclidean distance between face landmark coordinate and ideal frame center (0.5, 0.4)."""
    dx = x - IDEAL_CENTER_X
    dy = y - IDEAL_CENTER_Y
    return float(math.sqrt(dx * dx + dy * dy))


def compute_gaze_deviation_sample(landmarks) -> float:
    """
    Calculates normalized gaze deviation ratio for a single frame using iris landmarks.
    Left iris: 468, corners: 33 (outer), 133 (inner).
    Right iris: 473, corners: 362 (inner), 263 (outer).
    Returns value in [0.0, 1.0], where 0.0 is looking directly ahead and >0.25 indicates deviation.
    """
    try:
        # Landmarks 468 and 473 are iris centers
        if len(landmarks) < 478:
            return 0.0

        # Left eye horizontal ratio
        x_iris_l = landmarks[468].x
        x_corner_l1 = landmarks[33].x
        x_corner_l2 = landmarks[133].x
        eye_width_l = abs(x_corner_l2 - x_corner_l1)
        if eye_width_l > 1e-5:
            ratio_l = abs((x_iris_l - min(x_corner_l1, x_corner_l2)) / eye_width_l - 0.5)
        else:
            ratio_l = 0.0

        # Right eye horizontal ratio
        x_iris_r = landmarks[473].x
        x_corner_r1 = landmarks[362].x
        x_corner_r2 = landmarks[263].x
        eye_width_r = abs(x_corner_r2 - x_corner_r1)
        if eye_width_r > 1e-5:
            ratio_r = abs((x_iris_r - min(x_corner_r1, x_corner_r2)) / eye_width_r - 0.5)
        else:
            ratio_r = 0.0

        # Average horizontal iris deviation from center (scaled to [0.0, 1.0])
        h_dev = (ratio_l + ratio_r) / 2.0
        # Normalize: offset from center is usually in range [0.0, 0.4]. Scale by 2.5
        norm_dev = min(1.0, h_dev * 2.5)
        return float(norm_dev)
    except Exception:
        return 0.0


def compute_head_motion_frequency(
    angles: List[Tuple[float, float, float]],
    fps: float
) -> float:
    """
    Calculates head motion direction changes per second (Hz) via peak detection.
    """
    if len(angles) < 3 or fps <= 0:
        return 0.0

    # Compute angular velocity magnitude between successive frames
    dt = 1.0 / fps
    velocities = []
    for i in range(1, len(angles)):
        dp = angles[i][0] - angles[i-1][0]
        dy = angles[i][1] - angles[i-1][1]
        dr = angles[i][2] - angles[i-1][2]
        dist = math.sqrt(dp * dp + dy * dy + dr * dr)
        velocities.append(dist / dt)

    if len(velocities) < 3:
        return 0.0

    # Count direction peaks where velocity exceeds motion threshold (e.g. 10 deg/s)
    peaks = 0
    thresh = 10.0
    for i in range(1, len(velocities) - 1):
        if velocities[i] > thresh and velocities[i] > velocities[i-1] and velocities[i] > velocities[i+1]:
            peaks += 1

    duration = len(angles) / fps
    frequency = peaks / max(1.0, duration)
    return float(round(frequency, 2))


def compute_frame_motion_energy(frames_rgb: List[np.ndarray]) -> float:
    """
    Computes mean pixel intensity delta across consecutive grayscale frames.
    Downsamples frames to 160x120 for fast calculation.
    """
    if len(frames_rgb) < 2:
        return 0.0

    diffs = []
    prev_gray = None

    for frame in frames_rgb:
        small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            diffs.append(float(np.mean(diff)))
        prev_gray = gray

    if not diffs:
        return 0.0
    return float(round(float(np.mean(diffs)), 2))


# ---------------------------------------------------------------------------
# 4. OpenCV Fallback Detection (Skin Color & Contour Centroid)
# ---------------------------------------------------------------------------

def detect_face_opencv_fallback(rgb_frame: np.ndarray) -> Tuple[bool, Optional[Tuple[float, float]]]:
    """
    OpenCV fallback for presence and centering using YCrCb skin-color segmentation.
    Returns (detected, (center_x, center_y)).
    """
    h, w = rgb_frame.shape[:2]
    bgr = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)

    # Standard skin tone range in YCrCb
    lower = np.array([0, 133, 77], dtype=np.uint8)
    upper = np.array([255, 173, 127], dtype=np.uint8)
    mask = cv2.inRange(ycrcb, lower, upper)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = 0.02 * (h * w)

    best_cnt = None
    max_area = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > min_area and area > max_area:
            best_cnt = cnt
            max_area = area

    if best_cnt is not None:
        bx, by, bw, bh = cv2.boundingRect(best_cnt)
        cx = (bx + bw / 2.0) / float(w)
        cy = (by + bh / 2.0) / float(h)
        return True, (cx, cy)

    return False, None


# ---------------------------------------------------------------------------
# 5. Core Video Frame Analysis Pipeline
# ---------------------------------------------------------------------------

def analyze_video_frames(
    frames_rgb: List[np.ndarray],
    fps: float,
    duration_seconds: float,
    force_backend: Optional[str] = None
) -> VisionTelemetryMetrics:
    """
    Processes video frames and extracts quantitative telemetry metrics.
    Operates using MediaPipe FaceLandmarker with automatic fallback to OpenCV.
    """
    detector = None
    backend = "opencv_fallback"

    if force_backend != "opencv_fallback":
        detector = get_face_landmarker()
        if detector is not None:
            backend = "mediapipe"

    frames_analyzed = len(frames_rgb)
    if frames_analyzed == 0:
        raise VisionProcessingError("No frames provided for telemetry analysis.")

    # Lighting check
    brightnesses = [float(np.mean(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY))) for f in frames_rgb]
    avg_brightness = float(np.mean(brightnesses))

    camera_quality_flags = []
    if avg_brightness < 40.0:
        camera_quality_flags.append("low_lighting")
    elif avg_brightness > 220.0:
        camera_quality_flags.append("overexposed")

    motion_energy = compute_frame_motion_energy(frames_rgb)
    if motion_energy > 22.0:
        camera_quality_flags.append("high_motion_energy")

    # Run Detection
    face_detected_count = 0
    centering_offsets = []

    if backend == "mediapipe":
        import mediapipe as mp
        gaze_deviations = []
        euler_angles: List[Tuple[float, float, float]] = []

        for frame in frames_rgb:
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            result = detector.detect(mp_img)

            if result.face_landmarks and len(result.face_landmarks) > 0:
                face_detected_count += 1
                landmarks = result.face_landmarks[0]

                # Centering from nose tip (landmark 1)
                nose = landmarks[1]
                centering_offsets.append(compute_centering_offset(nose.x, nose.y))

                # Gaze deviation
                gaze_dev = compute_gaze_deviation_sample(landmarks)
                gaze_deviations.append(gaze_dev)

                # Head pose from facial transformation matrix
                if result.facial_transformation_matrixes and len(result.facial_transformation_matrixes) > 0:
                    mat = result.facial_transformation_matrixes[0]
                    R = mat[:3, :3]
                    p, y, r = rotation_matrix_to_euler_angles(R)
                    euler_angles.append((p, y, r))

        face_detected_ratio = round(face_detected_count / max(1, frames_analyzed), 3)
        avg_centering = round(float(np.mean(centering_offsets)), 3) if centering_offsets else 0.50

        if face_detected_ratio < 0.70:
            camera_quality_flags.append("low_face_presence")
        if avg_centering > 0.22:
            camera_quality_flags.append("off_center")

        # Gaze ratio: fraction of frames where gaze deviated significantly (>0.25)
        if gaze_deviations:
            deviated_count = sum(1 for d in gaze_deviations if d > 0.25)
            gaze_dev_ratio = round(deviated_count / len(gaze_deviations), 3)
        else:
            gaze_dev_ratio = 1.0 if face_detected_count == 0 else 0.0

        # Head Pose Statistics
        if euler_angles:
            pitches = [a[0] for a in euler_angles]
            yaws = [a[1] for a in euler_angles]
            rolls = [a[2] for a in euler_angles]

            avg_p = round(float(np.mean(pitches)), 1)
            avg_y = round(float(np.mean(yaws)), 1)
            avg_r = round(float(np.mean(rolls)), 1)

            var_p = round(float(np.var(pitches)), 1) if len(pitches) > 1 else 0.0
            var_y = round(float(np.var(yaws)), 1) if len(yaws) > 1 else 0.0
            var_r = round(float(np.var(rolls)), 1) if len(rolls) > 1 else 0.0

            motion_freq = compute_head_motion_frequency(euler_angles, fps)
        else:
            avg_p, avg_y, avg_r = None, None, None
            var_p, var_y, var_r = None, None, None
            motion_freq = None

        return VisionTelemetryMetrics(
            video_duration_seconds=round(duration_seconds, 2),
            frames_analyzed=frames_analyzed,
            face_detected_ratio=face_detected_ratio,
            centering_offset=avg_centering,
            gaze_deviation_ratio=gaze_dev_ratio,
            avg_yaw_degrees=avg_y,
            avg_pitch_degrees=avg_p,
            avg_roll_degrees=avg_r,
            yaw_variance=var_y,
            pitch_variance=var_p,
            roll_variance=var_r,
            head_motion_frequency_hz=motion_freq,
            motion_energy=motion_energy,
            camera_quality_flags=camera_quality_flags,
            vision_backend="mediapipe"
        )

    else:
        # OpenCV Fallback Mode
        for frame in frames_rgb:
            detected, center = detect_face_opencv_fallback(frame)
            if detected and center is not None:
                face_detected_count += 1
                centering_offsets.append(compute_centering_offset(center[0], center[1]))

        face_detected_ratio = round(face_detected_count / max(1, frames_analyzed), 3)
        avg_centering = round(float(np.mean(centering_offsets)), 3) if centering_offsets else 0.50

        if face_detected_ratio < 0.70:
            camera_quality_flags.append("low_face_presence")
        if avg_centering > 0.22:
            camera_quality_flags.append("off_center")

        return VisionTelemetryMetrics(
            video_duration_seconds=round(duration_seconds, 2),
            frames_analyzed=frames_analyzed,
            face_detected_ratio=face_detected_ratio,
            centering_offset=avg_centering,
            gaze_deviation_ratio=None,
            avg_yaw_degrees=None,
            avg_pitch_degrees=None,
            avg_roll_degrees=None,
            yaw_variance=None,
            pitch_variance=None,
            roll_variance=None,
            head_motion_frequency_hz=None,
            motion_energy=motion_energy,
            camera_quality_flags=camera_quality_flags,
            vision_backend="opencv_fallback"
        )


# ---------------------------------------------------------------------------
# 6. Capability-Aware Deterministic Scoring & Descriptive Feedback
# ---------------------------------------------------------------------------

def calculate_nonverbal_score(
    face_detected_ratio: float,
    centering_offset: float,
    motion_energy: float,
    gaze_deviation_ratio: Optional[float] = None,
    yaw_variance: Optional[float] = None,
    pitch_variance: Optional[float] = None,
    roll_variance: Optional[float] = None,
    head_motion_frequency_hz: Optional[float] = None,
    camera_quality_flags: Optional[List[str]] = None,
    vision_backend: str = "mediapipe"
) -> Tuple[int, str]:
    """
    Computes deterministic Nonverbal Telemetry Score (1-10) and purely descriptive feedback.
    Strict rule: ZERO trait inference (never infer confidence, stress, nervousness, emotion, or personality).
    Capability-aware: Does not penalize if gaze or pose measurements are None in fallback mode.
    """
    score = 10.0
    feedback_notes = []

    # 1. Face Presence & Centering
    if face_detected_ratio >= 0.85:
        feedback_notes.append(f"Consistent camera presence ({int(face_detected_ratio * 100)}% of frames).")
    elif 0.60 <= face_detected_ratio < 0.85:
        deduction = 1.5 if vision_backend == "mediapipe" else 2.0
        score -= deduction
        feedback_notes.append(f"Face was not detected in {int((1.0 - face_detected_ratio) * 100)}% of frames.")
    else:
        deduction = 3.0 if vision_backend == "mediapipe" else 4.0
        score -= deduction
        feedback_notes.append(f"Candidate was frequently out of camera view ({int(face_detected_ratio * 100)}% presence).")

    if centering_offset <= 0.15:
        feedback_notes.append(f"Well-centered framing (offset {centering_offset:.2f}).")
    elif 0.15 < centering_offset <= 0.25:
        deduction = 1.0 if vision_backend == "mediapipe" else 1.5
        score -= deduction
        feedback_notes.append(f"Positioned moderately off-center (offset {centering_offset:.2f}).")
    else:
        deduction = 2.0 if vision_backend == "mediapipe" else 3.0
        score -= deduction
        feedback_notes.append(f"Positioned substantially off-center (offset {centering_offset:.2f}). Adjust camera framing.")

    # 2. Gaze Orientation (MediaPipe Only)
    if gaze_deviation_ratio is not None:
        if gaze_deviation_ratio <= 0.30:
            feedback_notes.append(f"Maintained forward gaze orientation toward the camera ({int((1.0 - gaze_deviation_ratio) * 100)}% of time).")
        elif 0.30 < gaze_deviation_ratio <= 0.55:
            score -= 1.0
            feedback_notes.append(f"Gaze shifted away from the camera for {int(gaze_deviation_ratio * 100)}% of the response.")
        else:
            score -= 2.0
            feedback_notes.append(f"Frequent downward or sideways gaze shifts ({int(gaze_deviation_ratio * 100)}% deviation). Focus more consistently on the lens.")

    # 3. Head Pose Stability (MediaPipe Only)
    if yaw_variance is not None and pitch_variance is not None and roll_variance is not None:
        total_variance = yaw_variance + pitch_variance + roll_variance
        if total_variance <= 100.0:
            feedback_notes.append(f"Head posture was steady (variance {total_variance:.1f} deg^2).")
        elif 100.0 < total_variance <= 300.0:
            score -= 1.0
            feedback_notes.append(f"Moderate head angular movement observed (variance {total_variance:.1f} deg^2).")
        else:
            score -= 2.0
            feedback_notes.append(f"Substantial head movement/tilting observed (variance {total_variance:.1f} deg^2). Aim for steady orientation.")

    if head_motion_frequency_hz is not None and head_motion_frequency_hz > 1.8:
        score -= 0.5
        feedback_notes.append(f"Frequent head motion transitions detected ({head_motion_frequency_hz} Hz).")

    # 4. Motion Energy
    if motion_energy <= 10.0:
        feedback_notes.append("Stable torso and background stillness.")
    elif 10.0 < motion_energy <= 20.0:
        deduction = 0.5 if vision_backend == "mediapipe" else 1.0
        score -= deduction
        feedback_notes.append(f"Moderate frame motion detected (energy {motion_energy:.1f}).")
    else:
        deduction = 1.5 if vision_backend == "mediapipe" else 2.0
        score -= deduction
        feedback_notes.append(f"Elevated movement or swaying detected (motion energy {motion_energy:.1f}).")

    # 5. Quality Notices (Informational)
    if camera_quality_flags:
        notices = []
        if "low_lighting" in camera_quality_flags:
            notices.append("dim lighting environment")
        if "overexposed" in camera_quality_flags:
            notices.append("bright backlight/overexposure")
        if notices:
            feedback_notes.append(f"Note: Video quality indicates {', '.join(notices)}.")

    if vision_backend == "opencv_fallback":
        feedback_notes.append("Limited telemetry mode (OpenCV fallback): evaluated on presence, framing, and stillness only.")

    final_score = int(max(1, min(10, round(score))))
    feedback_str = " ".join(feedback_notes)

    return final_score, feedback_str


# ---------------------------------------------------------------------------
# 7. Master Video Analysis Pipeline
# ---------------------------------------------------------------------------

def process_video(
    video_bytes_or_path,
    target_fps: float = DEFAULT_TARGET_FPS,
    force_backend: Optional[str] = None
) -> NonverbalAnalysisResult:
    """
    Main entry point for Phase 5 computer vision and nonverbal telemetry:
    1. Extracts and subsamples frames using OpenCV / PyAV.
    2. Runs geometric feature extraction (MediaPipe FaceLandmarker or OpenCV fallback).
    3. Calculates deterministic nonverbal score and objective descriptive feedback.
    """
    with inference_guard():
        frames_rgb, fps, duration = extract_video_frames(video_bytes_or_path, target_fps=target_fps)

        metrics = analyze_video_frames(
            frames_rgb=frames_rgb,
            fps=fps,
            duration_seconds=duration,
            force_backend=force_backend
        )

        score, feedback = calculate_nonverbal_score(
            face_detected_ratio=metrics.face_detected_ratio,
            centering_offset=metrics.centering_offset,
            motion_energy=metrics.motion_energy,
            gaze_deviation_ratio=metrics.gaze_deviation_ratio,
            yaw_variance=metrics.yaw_variance,
            pitch_variance=metrics.pitch_variance,
            roll_variance=metrics.roll_variance,
            head_motion_frequency_hz=metrics.head_motion_frequency_hz,
            camera_quality_flags=metrics.camera_quality_flags,
            vision_backend=metrics.vision_backend
        )

        return NonverbalAnalysisResult(
            video_duration_seconds=metrics.video_duration_seconds,
            frames_analyzed=metrics.frames_analyzed,
            face_detected_ratio=metrics.face_detected_ratio,
            centering_offset=metrics.centering_offset,
            gaze_deviation_ratio=metrics.gaze_deviation_ratio,
            avg_yaw_degrees=metrics.avg_yaw_degrees,
            avg_pitch_degrees=metrics.avg_pitch_degrees,
            avg_roll_degrees=metrics.avg_roll_degrees,
            yaw_variance=metrics.yaw_variance,
            pitch_variance=metrics.pitch_variance,
            roll_variance=metrics.roll_variance,
            head_motion_frequency_hz=metrics.head_motion_frequency_hz,
            motion_energy=metrics.motion_energy,
            camera_quality_flags=metrics.camera_quality_flags,
            nonverbal_telemetry_score=score,
            nonverbal_feedback=feedback,
            vision_backend=metrics.vision_backend
        )
