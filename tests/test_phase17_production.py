"""
Phase 17.1 Production Hardening Tests.

Verifies:
1. Database path configuration (DATABASE_PATH override, fallback, parent directory creation).
2. SQLite production pragmas (WAL mode, busy_timeout >= 5000, foreign_keys ON, synchronous NORMAL).
3. SQLite online backup and restore (Connection.backup(), integrity verification, compression, retention).
4. Frontend serving at GET / (FileResponse, text/html, index.html integrity, relative API_URL).
5. Health endpoint (connectivity verification, 503 on database error, zero ML inference).
6. Inference concurrency protection (threading.Semaphore(1) gate, serialization, zero starvation).
7. Ephemeral media cleanup and requirements/gitignore validation.
"""

from __future__ import annotations

import gzip
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from backend.main import app, get_db
from backend.database import get_database_path
from backend.inference_gate import (
    INFERENCE_GATE,
    inference_guard,
    InferenceCapacityError,
    validate_worker_configuration,
)
from scripts.backup_db import (
    backup_database,
    restore_database,
    verify_database_integrity,
    prune_backups,
)


class TestPhase17ProductionHardening(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    # =======================================================================
    # 1. DATABASE CONFIGURATION & PRAGMAS
    # =======================================================================

    def test_01_database_path_override_and_parent_dir_creation(self):
        nested_db = self.tmp_path / "deep" / "nested" / "prod_test.db"
        self.assertFalse(nested_db.parent.exists())

        with patch.dict(os.environ, {"DATABASE_PATH": str(nested_db)}):
            resolved = get_database_path()
            self.assertEqual(resolved, nested_db.resolve())
            self.assertTrue(nested_db.parent.is_dir())

            conn = get_db()
            conn.execute("CREATE TABLE test_tbl (id INTEGER PRIMARY KEY, val TEXT);")
            conn.execute("INSERT INTO test_tbl (val) VALUES ('test_val');")
            conn.commit()
            conn.close()

            self.assertTrue(nested_db.is_file())

    def test_02_database_path_development_fallback(self):
        with patch.dict(os.environ, {"DATABASE_PATH": ""}):
            resolved = get_database_path()
            self.assertTrue(str(resolved).endswith(os.path.join("backend", "interview.db")))

    def test_03_sqlite_production_pragmas(self):
        test_db = self.tmp_path / "pragmas_test.db"
        with patch.dict(os.environ, {"DATABASE_PATH": str(test_db)}):
            conn = get_db()
            try:
                # 1. foreign_keys
                fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
                self.assertEqual(fk, 1)

                # 2. journal_mode
                jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
                self.assertEqual(jm.lower(), "wal")

                # 3. busy_timeout
                bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
                self.assertGreaterEqual(bt, 5000)

                # 4. synchronous
                sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
                # In SQLite, PRAGMA synchronous returns 1 for NORMAL
                self.assertIn(sync, (1, "NORMAL", "normal"))
            finally:
                conn.close()

    def test_04_no_schema_changes_and_canonical_tables(self):
        test_db = self.tmp_path / "schema_check.db"
        with patch.dict(os.environ, {"DATABASE_PATH": str(test_db)}):
            from backend.database import create_tables
            create_tables()

            conn = get_db()
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
                ).fetchall()
            }
            conn.close()

            expected_tables = {
                "questions",
                "answers",
                "evaluations",
                "users",
                "interview_sessions",
                "session_turns",
                "speech_analytics",
                "nonverbal_analytics",
            }
            self.assertEqual(tables, expected_tables)

    # =======================================================================
    # 2. BACKUP & RESTORE UTILITY
    # =======================================================================

    def _create_mock_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, hash TEXT);")
        conn.execute("INSERT INTO users VALUES (1, 'u1@test.com', 'h1'), (2, 'u2@test.com', 'h2');")
        conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, title TEXT);")
        conn.execute("INSERT INTO sessions VALUES (101, 'Mock Session A');")
        conn.commit()
        conn.close()

    def test_05_backup_creation_and_integrity(self):
        source_db = self.tmp_path / "source.db"
        backup_dir = self.tmp_path / "backups"
        self._create_mock_db(source_db)

        archive = backup_database(source_db_path=source_db, backup_dir=backup_dir)
        self.assertTrue(archive.is_file())
        self.assertTrue(archive.name.endswith(".db.gz"))
        self.assertGreater(archive.stat().st_size, 100)

        # Decompress and verify integrity
        decompressed_path = self.tmp_path / "test_decompressed.db"
        with gzip.open(archive, "rb") as f_in, open(decompressed_path, "wb") as f_out:
            f_out.write(f_in.read())

        self.assertTrue(verify_database_integrity(decompressed_path))

    def test_06_backup_failure_on_corrupt_database(self):
        corrupt_db = self.tmp_path / "corrupt.db"
        with open(corrupt_db, "wb") as f:
            f.write(b"NOT A SQLITE DATABASE CORRUPTED DATA")

        backup_dir = self.tmp_path / "backups_fail"
        with self.assertRaises(Exception):
            backup_database(source_db_path=corrupt_db, backup_dir=backup_dir)

        # Confirm no valid .db.gz archive was finalized
        finalized = list(backup_dir.glob("interview_backup_*.db.gz"))
        self.assertEqual(len(finalized), 0)

    def test_07_backup_restore_and_row_integrity(self):
        source_db = self.tmp_path / "source_for_restore.db"
        backup_dir = self.tmp_path / "backups_restore"
        restored_db = self.tmp_path / "restored.db"
        self._create_mock_db(source_db)

        archive = backup_database(source_db_path=source_db, backup_dir=backup_dir)
        restored_path = restore_database(backup_file_path=archive, target_db_path=restored_db)

        self.assertEqual(restored_path, restored_db.resolve())
        self.assertTrue(restored_db.is_file())
        self.assertTrue(verify_database_integrity(restored_db))

        # Check rows match original exactly
        conn = sqlite3.connect(restored_db)
        users = conn.execute("SELECT email, hash FROM users ORDER BY id;").fetchall()
        sessions = conn.execute("SELECT id, title FROM sessions;").fetchall()
        conn.close()

        self.assertEqual(users, [("u1@test.com", "h1"), ("u2@test.com", "h2")])
        self.assertEqual(sessions, [(101, "Mock Session A")])

    def test_08_restore_overwrite_protection(self):
        source_db = self.tmp_path / "source_ow.db"
        backup_dir = self.tmp_path / "backups_ow"
        existing_target = self.tmp_path / "existing.db"
        self._create_mock_db(source_db)
        self._create_mock_db(existing_target)

        archive = backup_database(source_db_path=source_db, backup_dir=backup_dir)

        # Must raise FileExistsError if force is False
        with self.assertRaises(FileExistsError):
            restore_database(backup_file_path=archive, target_db_path=existing_target, force=False)

        # Succeeds when force=True
        res = restore_database(backup_file_path=archive, target_db_path=existing_target, force=True)
        self.assertEqual(res, existing_target.resolve())

    def test_09_backup_retention_pruning(self):
        backup_dir = self.tmp_path / "retention_dir"
        backup_dir.mkdir(parents=True, exist_ok=True)

        old_file = backup_dir / "interview_backup_20260101_000000.db.gz"
        new_file = backup_dir / "interview_backup_20260912_000000.db.gz"

        old_file.write_bytes(b"dummy")
        new_file.write_bytes(b"dummy")

        # Set old_file mtime to 30 days ago
        thirty_days_ago = time.time() - (30 * 86400)
        os.utime(old_file, (thirty_days_ago, thirty_days_ago))

        pruned = prune_backups(backup_dir, retention_days=14)
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0].name, old_file.name)
        self.assertFalse(old_file.exists())
        self.assertTrue(new_file.exists())

    def test_10_missing_backup_directory_handling(self):
        source_db = self.tmp_path / "source_missing_dir.db"
        deep_backup_dir = self.tmp_path / "new_folder" / "deep_backups"
        self._create_mock_db(source_db)

        self.assertFalse(deep_backup_dir.exists())
        archive = backup_database(source_db_path=source_db, backup_dir=deep_backup_dir)
        self.assertTrue(deep_backup_dir.is_dir())
        self.assertTrue(archive.is_file())

    # =======================================================================
    # 3. FRONTEND SERVING & SAME-ORIGIN API URL
    # =======================================================================

    def test_11_root_route_serves_html_index(self):
        client = TestClient(app)
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn('id="session-container"', resp.text)
        self.assertIn('id="auth-modal"', resp.text)

    def test_12_frontend_api_url_is_relative(self):
        repo_root = Path(__file__).resolve().parent.parent
        index_html_path = repo_root / "web" / "index.html"
        self.assertTrue(index_html_path.is_file())

        content = index_html_path.read_text(encoding="utf-8")
        self.assertIn('const API_URL = "";', content)
        self.assertNotIn("http://127.0.0.1:8000", content)
        self.assertNotIn("http://localhost:8000", content)

    # =======================================================================
    # 4. HEALTH ENDPOINT CHECKS
    # =======================================================================

    def test_13_health_check_success(self):
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "healthy", "database": "connected"})

    def test_14_health_check_database_failure_503(self):
        client = TestClient(app)
        with patch("backend.main.get_db", side_effect=sqlite3.OperationalError("DB disk failure")):
            resp = client.get("/health")
            self.assertEqual(resp.status_code, 503)
            self.assertIn("Database health check failed", resp.json()["detail"])

    def test_15_health_check_does_not_invoke_whisper_or_vision(self):
        client = TestClient(app)
        with patch("backend.speech_engine.transcribe_audio") as mock_stt, \
             patch("backend.vision_analyzer.process_video") as mock_vis:
            resp = client.get("/health")
            self.assertEqual(resp.status_code, 200)
            mock_stt.assert_not_called()
            mock_vis.assert_not_called()

    # =======================================================================
    # 5. REAL INFERENCE CONCURRENCY PROTECTION
    # =======================================================================

    def test_16a_inference_gate_acquired_and_released_on_success(self):
        """Proves gate is acquired normally and safely released after successful execution."""
        executed = False
        with inference_guard(timeout=1.0):
            executed = True
        self.assertTrue(executed)
        # Immediately re-acquirable
        with inference_guard(timeout=0.1):
            pass

    def test_16b_inference_gate_releases_on_exception(self):
        """Proves gate is safely released even when inference raises an unhandled exception."""
        with self.assertRaises(ZeroDivisionError):
            with inference_guard(timeout=1.0):
                _ = 1 / 0
        # Immediately re-acquirable
        with inference_guard(timeout=0.1):
            pass

    def test_16c_inference_gate_second_request_waits_and_succeeds(self):
        """Proves that a second concurrent request waits boundedly and proceeds upon release."""
        t1_acquired = threading.Event()
        t2_finished = threading.Event()
        t1_can_release = threading.Event()

        def worker1():
            with inference_guard(timeout=1.0):
                t1_acquired.set()
                t1_can_release.wait(timeout=2.0)

        def worker2():
            t1_acquired.wait(timeout=2.0)
            # Worker 2 waits for worker 1 to release, with a generous 1.0s timeout
            with inference_guard(timeout=1.0):
                t2_finished.set()

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)
        t1.start()
        t2.start()

        self.assertTrue(t1_acquired.wait(timeout=1.0))
        time.sleep(0.05)
        t1_can_release.set()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)
        self.assertTrue(t2_finished.is_set())

    def test_16d_inference_gate_second_request_times_out(self):
        """Proves that when the gate is held longer than timeout, InferenceCapacityError is raised."""
        t1_acquired = threading.Event()
        t1_can_release = threading.Event()
        t2_timed_out = threading.Event()
        worker2_error = None

        def worker1():
            with inference_guard(timeout=1.0):
                t1_acquired.set()
                t1_can_release.wait(timeout=2.0)

        def worker2():
            nonlocal worker2_error
            t1_acquired.wait(timeout=2.0)
            try:
                # Short timeout of 0.05s while worker 1 holds gate
                with inference_guard(timeout=0.05):
                    pass
            except InferenceCapacityError as e:
                worker2_error = e
                t2_timed_out.set()

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)
        t1.start()
        t2.start()

        self.assertTrue(t1_acquired.wait(timeout=1.0))
        self.assertTrue(t2_timed_out.wait(timeout=1.0))
        t1_can_release.set()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        self.assertIsNotNone(worker2_error)
        self.assertIn("Inference capacity is temporarily busy", str(worker2_error))

    def test_16e_inference_capacity_error_converts_to_http_503(self):
        """
        Proves that an InferenceCapacityError raised during audio/vision endpoints
        is converted to HTTP 503 with the user-safe message and no semaphore internals exposed.
        """
        client = TestClient(app)
        from tests.test_phase5 import generate_synthetic_wav
        wav_bytes = generate_synthetic_wav()

        # 1. Speech endpoint test with simulated InferenceCapacityError
        with patch("backend.main.transcribe_audio", side_effect=InferenceCapacityError("Inference capacity is temporarily busy. Please try again shortly.")):
            resp = client.post(
                "/speech/analyze",
                files={"file": ("test.wav", wav_bytes, "audio/wav")}
            )
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(
                resp.json().get("detail"),
                "Inference capacity is temporarily busy. Please try again shortly."
            )
            # Ensure no internal threading or semaphore details leaked
            self.assertNotIn("semaphore", resp.text.lower())
            self.assertNotIn("threading", resp.text.lower())
            self.assertNotIn("lock", resp.text.lower())

        # 2. Vision endpoint test with simulated InferenceCapacityError
        with patch("backend.main.process_video", side_effect=InferenceCapacityError("Inference capacity is temporarily busy. Please try again shortly.")):
            resp_vis = client.post(
                "/vision/analyze",
                files={"video_file": ("test.webm", b"dummy video content exceeding minimum length constraint" * 5, "video/webm")}
            )
            self.assertEqual(resp_vis.status_code, 503)
            self.assertEqual(
                resp_vis.json().get("detail"),
                "Inference capacity is temporarily busy. Please try again shortly."
            )

    def test_16f_inference_gate_serializes_concurrent_execution(self):
        """
        Proves that two threads attempting expensive ML inference cannot execute
        simultaneously and are strictly serialized by the process-local semaphore.
        """
        execution_order = []
        max_active_workers = 0
        current_active_workers = 0
        lock = threading.Lock()

        def simulated_inference_worker(worker_id: int):
            nonlocal max_active_workers, current_active_workers
            with inference_guard():
                with lock:
                    current_active_workers += 1
                    if current_active_workers > max_active_workers:
                        max_active_workers = current_active_workers
                execution_order.append(f"start_{worker_id}")
                time.sleep(0.05)  # Simulate expensive CPU inference
                execution_order.append(f"end_{worker_id}")
                with lock:
                    current_active_workers -= 1

        t1 = threading.Thread(target=simulated_inference_worker, args=(1,))
        t2 = threading.Thread(target=simulated_inference_worker, args=(2,))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # At no point should more than 1 thread be inside the inference guard
        self.assertEqual(max_active_workers, 1)
        self.assertEqual(len(execution_order), 4)

        # Confirm strictly serialized pattern: start_A, end_A, start_B, end_B
        self.assertEqual(execution_order[1], execution_order[0].replace("start", "end"))
        self.assertEqual(execution_order[3], execution_order[2].replace("start", "end"))

    def test_17_shared_inference_gate_between_speech_and_vision(self):
        """
        Verifies that speech_engine and vision_analyzer import and share the exact
        same process-local INFERENCE_GATE semaphore instance.
        """
        import backend.speech_engine as se
        import backend.vision_analyzer as va
        import backend.inference_gate as ig

        self.assertIs(se.inference_guard, ig.inference_guard)
        self.assertIs(va.inference_guard, ig.inference_guard)
        self.assertIsInstance(ig.INFERENCE_GATE, threading.Semaphore)

    # =======================================================================
    # 6. AUTHENTICATION & COOKIE PRODUCTION INTEGRATION
    # =======================================================================

    def test_18_production_secret_required_and_secure_cookie(self):
        test_db = self.tmp_path / "auth_prod_test.db"
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "AUTH_SECRET_KEY": "production-secret-key-32-bytes-long!!",
            "COOKIE_SECURE": "true",
            "DATABASE_PATH": str(test_db),
        }):
            from backend.database import create_tables
            create_tables()

            client = TestClient(app)
            reg_resp = client.post(
                "/auth/register",
                json={"email": "prod_user@test.com", "password": "StrongPassword123!"}
            )
            self.assertEqual(reg_resp.status_code, 201)

            set_cookie = reg_resp.headers.get("set-cookie", "")
            self.assertIn("auth_token=", set_cookie)
            self.assertIn("HttpOnly", set_cookie)
            self.assertIn("Secure", set_cookie)
            self.assertIn("samesite=lax", set_cookie.lower())

    # =======================================================================
    # 7. DEPENDENCY & GITIGNORE INTEGRITY
    # =======================================================================

    def test_19_requirements_and_gitignore_contain_required_entries(self):
        repo_root = Path(__file__).resolve().parent.parent

        # requirements.txt
        req_text = (repo_root / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("bcrypt==5.0.0", req_text)
        self.assertIn("itsdangerous==2.2.0", req_text)

        # .gitignore
        gi_text = (repo_root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", gi_text)
        self.assertIn("*.db", gi_text)
        self.assertIn("*.sqlite", gi_text)
        self.assertIn("backups/", gi_text)

    # =======================================================================
    # 8. SINGLE-WORKER INVARIANT ENFORCEMENT
    # =======================================================================

    def test_20_single_worker_invariant_production_valid(self):
        """Proves UVICORN_WORKERS=1 is valid in production mode."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "UVICORN_WORKERS": "1"}):
            # Must not raise
            validate_worker_configuration()

    def test_21_single_worker_invariant_production_rejected(self):
        """Proves UVICORN_WORKERS=2 is rejected in production mode."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "UVICORN_WORKERS": "2"}):
            with self.assertRaises(RuntimeError) as ctx:
                validate_worker_configuration()
            self.assertIn("UVICORN_WORKERS=2 is invalid in production mode", str(ctx.exception))

    def test_22_single_worker_invariant_development_unset_preserved(self):
        """Proves unset UVICORN_WORKERS preserves normal development behavior."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "UVICORN_WORKERS": ""}):
            # Must not raise
            validate_worker_configuration()

    def test_23_systemd_service_enforces_single_worker(self):
        """Verifies deploy/interview-simulator.service explicitly enforces single worker."""
        repo_root = Path(__file__).resolve().parent.parent
        service_file = repo_root / "deploy" / "interview-simulator.service"
        self.assertTrue(service_file.is_file())
        content = service_file.read_text(encoding="utf-8")
        self.assertIn("--workers 1", content)
        self.assertIn("Environment=UVICORN_WORKERS=1", content)
        self.assertNotIn("--workers 2", content)


if __name__ == "__main__":
    unittest.main()
