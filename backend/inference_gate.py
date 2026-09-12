"""
Process-local inference concurrency gate.

Protects expensive CPU-bound Machine Learning inference (faster-whisper and MediaPipe/OpenCV)
from running concurrently in Starlette's threadpool within a single Uvicorn worker process.

Why this is required:
- Uvicorn --workers 1 limits the application to a single OS process.
- However, FastAPI synchronous endpoints execute concurrently inside an anyio threadpool.
- On a resource-constrained VM (e.g., Azure Standard_B1s with 1 GB RAM), simultaneous
  execution of Whisper STT and/or MediaPipe vision inference would exceed available physical RAM
  and cause an Out-Of-Memory (OOM) kernel crash.
- This semaphore ensures that at most ONE expensive ML inference operation executes at any given time,
  serializing heavy ML operations while allowing all other lightweight API endpoints (auth, sessions,
  questions, stats, health) to proceed concurrently without blocking.
"""

import threading
from contextlib import contextmanager

# Global process-local semaphore limiting expensive ML inference concurrency to 1
INFERENCE_GATE = threading.Semaphore(1)

# Default acquisition timeout in seconds (bounded wait to prevent thread starvation)
DEFAULT_INFERENCE_TIMEOUT: float = 30.0


class InferenceCapacityError(Exception):
    """Raised when inference gate acquisition times out due to concurrent load."""

    def __init__(self, message: str = "Inference capacity is temporarily busy. Please try again shortly."):
        super().__init__(message)
        self.message = message


def get_inference_timeout() -> float:
    """Returns the configured inference gate timeout in seconds."""
    import os
    env_val = os.environ.get("INFERENCE_GATE_TIMEOUT")
    if env_val:
        try:
            return float(env_val.strip())
        except (ValueError, TypeError):
            pass
    return DEFAULT_INFERENCE_TIMEOUT


@contextmanager
def inference_guard(timeout: Optional[float] = None):
    """
    Context manager that acquires the inference semaphore with a bounded timeout
    and guarantees its release in a finally block.

    If acquisition exceeds the timeout, raises InferenceCapacityError.
    """
    wait_time = timeout if timeout is not None else get_inference_timeout()
    acquired = INFERENCE_GATE.acquire(timeout=wait_time)
    if not acquired:
        raise InferenceCapacityError("Inference capacity is temporarily busy. Please try again shortly.")
    try:
        yield
    finally:
        INFERENCE_GATE.release()


def validate_worker_configuration() -> None:
    """
    Validates that the Uvicorn worker count does not violate the process-local
    inference gate invariant in production mode.

    The inference gate relies on a process-local semaphore (INFERENCE_GATE). Running
    multiple worker processes would create multiple independent semaphores, defeating
    inference concurrency protection on resource-constrained systems.

    - In production mode, if UVICORN_WORKERS or WORKERS is set, it must be <= 1 (typically 1).
      If set to > 1, raises RuntimeError to prevent startup.
    - If unset, preserves development / default compatibility.
    """
    import os
    workers_str = os.environ.get("UVICORN_WORKERS") or os.environ.get("WORKERS")
    if workers_str and workers_str.strip():
        try:
            worker_count = int(workers_str.strip())
        except ValueError:
            raise RuntimeError(
                f"Invalid UVICORN_WORKERS value: {workers_str!r}. Must be an integer."
            )

        env_val = (
            os.environ.get("ENVIRONMENT")
            or os.environ.get("APP_ENV")
            or os.environ.get("ENV")
            or ""
        ).strip().lower()
        is_prod = env_val in ("production", "prod") or os.environ.get("PRODUCTION", "").strip().lower() in ("true", "1", "yes")

        if is_prod and worker_count > 1:
            raise RuntimeError(
                f"UVICORN_WORKERS={worker_count} is invalid in production mode. "
                f"The AI Interview Simulator requires --workers 1 to enforce process-local "
                f"inference concurrency protection."
            )
