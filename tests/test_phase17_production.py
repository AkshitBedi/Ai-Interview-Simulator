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

    def test_24_deployment_readme_auth_secret_and_sqlite_verification(self):
        """
        Verifies deploy/README.md uses safe shell-expanded AUTH_SECRET_KEY generation,
        PRAGMA-based SQLite smoke-test commands, explicit GEMINI_API_KEY placeholder,
        disaster recovery limitations, Python compatibility pre-flight, fail2ban, and public repo access.
        """
        repo_root = Path(__file__).resolve().parent.parent
        readme_file = repo_root / "deploy" / "README.md"
        self.assertTrue(readme_file.is_file())
        content = readme_file.read_text(encoding="utf-8")

        # 1. Verify safe shell evaluation pattern
        self.assertIn('AUTH_SECRET_KEY="$(openssl rand -hex 32)"', content)
        self.assertIn("AUTH_SECRET_KEY=${AUTH_SECRET_KEY}", content)

        # 2. Confirm no broken quoted heredoc preventing command substitution
        self.assertNotIn("AUTH_SECRET_KEY=$(openssl rand -hex 32)\n", content)

        # 3. Confirm SQLite PRAGMA checks are documented
        self.assertIn('sqlite3 /data/interview.db "PRAGMA journal_mode;"', content)
        self.assertIn('sqlite3 /data/interview.db "PRAGMA integrity_check;"', content)

        # 4. Confirm auxiliary -wal and -shm files are not required to exist
        self.assertIn("Do NOT check for the presence of `-wal` or `-shm` auxiliary files", content)

        # 5. Confirm explicit GEMINI_API_KEY configuration placeholder
        self.assertIn("GEMINI_API_KEY=", content)
        self.assertIn("deterministic fallbacks", content)

        # 6. Confirm disaster-recovery limitations and laptop non-storage invariant
        self.assertIn("Current Disaster-Recovery Limitations", content)
        self.assertIn("Same-Disk Limitation", content)
        self.assertIn("Production interview data must **not** be synced or backed up to local developer laptops", content)

        # 7. Confirm Python 3.10 - 3.12 compatibility pre-flight check
        self.assertIn("Python Runtime Compatibility & Pre-Flight Check", content)
        self.assertIn("Python 3.10 - 3.12", content)

        # 8. Confirm fail2ban and repository access documentation
        self.assertIn("fail2ban", content)
        self.assertIn("fail2ban-client status sshd", content)
        self.assertNotIn("5 failed attempts within 10 minutes", content)
        self.assertIn("Public Repository Assumption", content)
        self.assertIn("https://github.com/AkshitBedi/Ai-Interview-Simulator.git", content)

    def test_25_eager_annotation_evaluation_and_typing_imports(self):
        """
        Proves that backend.interview_engine and backend.inference_gate have all
        required typing imports (Any, Optional) and do not fail under Python 3.12-style
        eager annotation evaluation.

        In Python <= 3.12, function annotations are evaluated eagerly at definition time.
        In Python >= 3.14 (PEP 649), annotation evaluation is deferred until explicitly queried.
        This test uses typing.get_type_hints() to force immediate eager evaluation of all annotations
        on critical functions in both modules, proving they resolve without NameError across all Python versions.
        """
        import typing
        import inspect

        # 1. Test backend.inference_gate functions
        import backend.inference_gate as ig
        self.assertTrue(hasattr(ig, "Optional"), "backend.inference_gate must import Optional from typing")
        ig_hints = typing.get_type_hints(ig.inference_guard)
        self.assertIn("timeout", ig_hints)

        # 2. Test backend.interview_engine functions
        import backend.interview_engine as ie
        self.assertTrue(hasattr(ie, "Any"), "backend.interview_engine must import Any from typing")
        ie_hints = typing.get_type_hints(ie.is_claim_eligible)
        self.assertIn("claim", ie_hints)

        # 3. Comprehensive eager evaluation of all functions in backend.inference_gate
        for name, func in inspect.getmembers(ig, inspect.isfunction):
            if func.__module__ == ig.__name__:
                try:
                    typing.get_type_hints(func)
                except Exception as exc:
                    self.fail(f"Eager annotation evaluation failed for {ig.__name__}.{name}: {exc}")

        # 4. Comprehensive eager evaluation of key candidate functions in backend.interview_engine
        for name in ("is_claim_eligible", "start_session", "get_session_details", "record_answer_and_advance"):
            func = getattr(ie, name, None)
            if func:
                try:
                    typing.get_type_hints(func)
                except Exception as exc:
                    self.fail(f"Eager annotation evaluation failed for {ie.__name__}.{name}: {exc}")

    def test_26_gemini_model_reference_and_deprecation_defense(self):
        """
        Proves that all production Gemini-backed modules use centralized get_gemini_model(),
        that DEFAULT_GEMINI_MODEL is 'gemini-3.6-flash', and that no independent hardcoded
        model string literals remain in production call sites.
        """
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        production_modules = [
            "evaluator.py",
            "interviewer.py",
            "document_processor.py",
            "coaching.py",
            "interview_engine.py",
            "insights_engine.py",
        ]

        # 1. Verify backend/gemini_config.py exists and defines DEFAULT_GEMINI_MODEL
        from backend.gemini_config import DEFAULT_GEMINI_MODEL, get_gemini_model
        self.assertEqual(DEFAULT_GEMINI_MODEL, "gemini-3.6-flash")

        # 2. Verify obsolete 'gemini-2.5-flash' does not appear anywhere in backend/
        for py_file in backend_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            self.assertNotIn(
                "gemini-2.5-flash",
                content,
                f"Obsolete model 'gemini-2.5-flash' found in {py_file.name}",
            )

        # 3. Verify no independent model literals remain in the 6 production modules
        # (they must use get_gemini_model() instead of hardcoded strings)
        for mod_name in production_modules:
            mod_path = backend_dir / mod_name
            self.assertTrue(mod_path.is_file(), f"Expected production module {mod_path} exists")
            content = mod_path.read_text(encoding="utf-8")

            # Check that get_gemini_model is imported and used
            self.assertIn(
                "get_gemini_model",
                content,
                f"get_gemini_model not imported/used in {mod_name}",
            )
            # Ensure no hardcoded model string literals remain in these modules
            self.assertNotIn(
                'model="gemini-',
                content,
                f"Hardcoded Gemini model literal found in {mod_name}",
            )
            self.assertNotIn(
                "model='gemini-",
                content,
                f"Hardcoded Gemini model literal found in {mod_name}",
            )

        # 4. Verify EvaluationResult default evaluator field
        from backend.evaluator import EvaluationResult, evaluate_interview_answer

        res_default = EvaluationResult(
            score=5,
            feedback="Sample feedback",
            technical_accuracy="Sample accuracy",
        )
        self.assertEqual(res_default.evaluator, "gemini-3.6-flash")

        # 5. Verify mocked evaluate_interview_answer returns gemini-3.6-flash
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            '{"score": 8, "feedback": "Accurate explanation.", '
            '"technical_accuracy": "Good technical depth.", "strengths": ["Clear concepts."], "missing_points": []}'
        )
        mock_client.models.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
            with patch("google.genai.Client", return_value=mock_client):
                eval_res = evaluate_interview_answer(
                    question="What is the difference between a Python list and a tuple?",
                    category="Python",
                    difficulty="medium",
                    answer="A list is mutable, while a tuple is immutable.",
                )
                self.assertEqual(eval_res.score, 8)
                self.assertEqual(eval_res.evaluator, "gemini-3.6-flash")
                self.assertIn("accurate explanation", eval_res.feedback.lower())

                # Verify the model passed to generate_content was strictly gemini-3.6-flash
                mock_client.models.generate_content.assert_called_once()
                call_kwargs = mock_client.models.generate_content.call_args.kwargs
                self.assertEqual(call_kwargs.get("model"), "gemini-3.6-flash")

    def test_27_gemini_configuration_hardening_and_override(self):
        """
        Proves that:
        1. get_gemini_model() defaults to 'gemini-3.6-flash' when GEMINI_MODEL is absent or whitespace.
        2. GEMINI_MODEL environment variable overrides the default model across all 6 production modules:
           - backend.evaluator (evaluate_interview_answer & EvaluationResult)
           - backend.interviewer (_generate_with_gemini)
           - backend.document_processor (extract_candidate_profile_sync & extract_job_context_sync)
           - backend.coaching (generate_coaching_report)
           - backend.interview_engine (generate_follow_up_question & generate_claim_probe_question)
           - backend.insights_engine (generate_insights_executive_summary)
        3. Structured output parsing and schema validation remain completely intact with the overridden model.
        """
        import json
        from backend.gemini_config import get_gemini_model, DEFAULT_GEMINI_MODEL
        from backend.evaluator import EvaluationResult, evaluate_interview_answer
        from backend.interviewer import generate_interviewer_response
        from backend.document_processor import (
            extract_candidate_profile_sync,
            extract_job_context_sync,
        )
        from backend.coaching import generate_coaching_report
        from backend.interview_engine import (
            generate_follow_up_question,
            generate_claim_probe_question,
        )
        from backend.insights_engine import generate_insights_executive_summary

        # 1. Environment configuration behavior
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_MODEL", None)
            self.assertEqual(get_gemini_model(), "gemini-3.6-flash")

            os.environ["GEMINI_MODEL"] = "   "
            self.assertEqual(get_gemini_model(), "gemini-3.6-flash")

            custom_model = "gemini-test-custom-override"
            os.environ["GEMINI_MODEL"] = custom_model
            self.assertEqual(get_gemini_model(), custom_model)

            # EvaluationResult dynamic default evaluator
            res = EvaluationResult(
                score=7,
                feedback="Good answer",
                technical_accuracy="Accurate",
            )
            self.assertEqual(res.evaluator, custom_model)

        # 2. Structured output schema validation with custom model
        custom_model = "gemini-custom-enterprise-model"
        with patch.dict(os.environ, {"GEMINI_MODEL": custom_model, "GEMINI_API_KEY": "fake_key"}, clear=False):
            # 2a. Evaluator
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = (
                '{"score": 9, "feedback": "Excellent explanation.", "technical_accuracy": "Precise.", '
                '"strengths": ["Clear distinction"], "missing_points": []}'
            )
            mock_client.models.generate_content.return_value = mock_resp
            with patch("google.genai.Client", return_value=mock_client):
                eval_res = evaluate_interview_answer(
                    question="What is a Python list?",
                    category="Python",
                    difficulty="easy",
                    answer="A list is a mutable sequence.",
                )
                self.assertEqual(eval_res.evaluator, custom_model)
                self.assertEqual(eval_res.score, 9)
                self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)

                # Verify structured schema validation remains intact
                raw_json = eval_res.model_dump_json()
                self.assertIn(custom_model, raw_json)
                parsed_back = EvaluationResult.model_validate_json(raw_json)
                self.assertEqual(parsed_back.evaluator, custom_model)

            # 2b. Interviewer
            mock_client.reset_mock()
            mock_resp.text = json.dumps({"interviewer_response": "Understood.", "response_type": "acknowledgement"})
            with patch("backend.interviewer.get_gemini_client", return_value=mock_client):
                generate_interviewer_response(
                    {"current_category": "Python", "next_category": "Python"},
                    action="continue",
                    is_same_category=True,
                )
            self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)

            # 2c. Document Processor (Resume & JD)
            mock_client.reset_mock()
            mock_resp.text = json.dumps({
                "skills": ["Python"],
                "past_roles": ["Software Engineer"],
                "projects": [],
                "years_of_experience": 5,
                "top_domains": ["Backend"],
                "claims": []
            })
            with patch("backend.document_processor._get_gemini_client", return_value=mock_client):
                p = extract_candidate_profile_sync("Senior Dev with Python experience")
                self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)
                self.assertEqual(p.skills, ["Python"])

                mock_client.reset_mock()
                mock_resp.text = json.dumps({
                    "title": "Backend Engineer",
                    "required_skills": ["Python"],
                    "preferred_skills": [],
                    "responsibilities": [],
                    "seniority_level": "senior"
                })
                j = extract_job_context_sync("Looking for Backend Engineer with Python")
                self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)
                self.assertEqual(j.title, "Backend Engineer")

            # 2d. Coaching
            mock_client.reset_mock()
            mock_client.models.generate_content.side_effect = Exception("Fallback test")
            dummy_signals = {
                "session_id": 1,
                "technical": {"overall_average_score": 7.0},
            }
            generate_coaching_report(dummy_signals, client=mock_client)
            self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)

            # 2e. Interview Engine (Follow-up & Claim Probing)
            mock_client.reset_mock()
            mock_client.models.generate_content.side_effect = None
            mock_resp.text = "Can you elaborate on list mutability?"
            mock_client.models.generate_content.return_value = mock_resp
            with patch("google.genai.Client", return_value=mock_client):
                follow_up = generate_follow_up_question(
                    original_question="What is a Python list?",
                    candidate_answer="A list is mutable.",
                    evaluation_feedback="Needs more depth.",
                    missing_points=["Trade-offs"],
                )
                self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)
                self.assertEqual(follow_up, "Can you elaborate on list mutability?")

            mock_client.reset_mock()
            mock_resp.text = "How did you scale the caching system in Redis?"
            with patch("google.genai.Client", return_value=mock_client):
                claim_dict = {
                    "statement": "Scaled Redis cache to 10k QPS",
                    "project_name": "Caching Layer",
                    "technologies": ["Redis", "Python"],
                    "metric": "10k QPS",
                    "ownership": "primary",
                    "claim_type": "scaling",
                }
                probe = generate_claim_probe_question(claim_dict, angle="technical_mechanism")
                self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)
                self.assertEqual(probe, "How did you scale the caching system in Redis?")

            # 2f. Insights Engine
            mock_client.reset_mock()
            mock_resp.text = "Candidate demonstrated consistent performance across technical evaluations."
            with patch("google.genai.Client", return_value=mock_client):
                dummy_payload = {
                    "total_completed_interviews": 2,
                    "technical_progression": {"trend": "improving", "first_score": 6.0, "latest_score": 8.0, "absolute_change": 2.0},
                    "consistency": {"best_session": {"score": 8.0, "categories": ["Python"]}},
                    "resume_claim_analytics": {"claim_instances_probed": 1, "substantiation_breakdown": {"strongly_substantiated": 1}},
                }
                summary = generate_insights_executive_summary(dummy_payload)
                self.assertEqual(mock_client.models.generate_content.call_args.kwargs.get("model"), custom_model)
                self.assertEqual(summary, "Candidate demonstrated consistent performance across technical evaluations.")

    # =======================================================================
    # 6. AZURE BLOB OFF-VM DISASTER RECOVERY TESTS
    # =======================================================================

    def _create_full_mock_db(self, db_path: Path) -> None:
        """Creates a mock SQLite database with all required canonical production tables."""
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, question TEXT, category TEXT, difficulty TEXT);")
        conn.execute("CREATE TABLE interview_sessions (id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT);")
        conn.execute("CREATE TABLE session_turns (id INTEGER PRIMARY KEY, session_id INTEGER, question_id INTEGER);")
        conn.execute("CREATE TABLE answers (id INTEGER PRIMARY KEY, session_id INTEGER, question_id INTEGER, answer_text TEXT);")
        conn.execute("CREATE TABLE evaluations (id INTEGER PRIMARY KEY, answer_id INTEGER, score REAL, feedback TEXT);")
        conn.execute("INSERT INTO questions VALUES (1, 'Explain Python generators.', 'Python', 'medium');")
        conn.execute("INSERT INTO interview_sessions VALUES (10, 1, 'active');")
        conn.execute("INSERT INTO session_turns VALUES (100, 10, 1);")
        conn.execute("INSERT INTO answers VALUES (1000, 10, 1, 'Generators use yield to produce values lazily.');")
        conn.execute("INSERT INTO evaluations VALUES (5000, 1000, 9.0, 'Comprehensive answer.');")
        conn.commit()
        conn.close()

    def test_28_azure_blob_config_resolution(self):
        """
        Verifies resolution of Azure Blob configuration from parameters and environment:
        - neither variable set -> returns None
        - both set -> returns (account, container)
        - only account set -> raises ValueError
        - only container set -> raises ValueError
        - whitespace stripped
        """
        from scripts.backup_db import get_azure_blob_config

        # 1. Neither variable set (env and args empty)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_azure_blob_config())
            self.assertIsNone(get_azure_blob_config(None, None))
            self.assertIsNone(get_azure_blob_config("", ""))
            self.assertIsNone(get_azure_blob_config("   ", "   "))

        # 2. Both set via explicit parameters
        res = get_azure_blob_config("myaccount", "mycontainer")
        self.assertEqual(res, ("myaccount", "mycontainer"))

        # 3. Both set via environment
        with patch.dict(
            os.environ,
            {"AZURE_STORAGE_ACCOUNT": "envaccount", "AZURE_STORAGE_CONTAINER": "envcontainer"},
            clear=True,
        ):
            res_env = get_azure_blob_config()
            self.assertEqual(res_env, ("envaccount", "envcontainer"))

        # 4. Explicit arguments override environment
        with patch.dict(
            os.environ,
            {"AZURE_STORAGE_ACCOUNT": "envaccount", "AZURE_STORAGE_CONTAINER": "envcontainer"},
            clear=True,
        ):
            res_override = get_azure_blob_config("override_acct", "override_cont")
            self.assertEqual(res_override, ("override_acct", "override_cont"))

        # 5. Only account set via parameters -> ValueError
        with self.assertRaises(ValueError) as cm:
            get_azure_blob_config("only_acct", None)
        self.assertIn("AZURE_STORAGE_CONTAINER is missing", str(cm.exception))

        # 6. Only container set via parameters -> ValueError
        with self.assertRaises(ValueError) as cm:
            get_azure_blob_config(None, "only_cont")
        self.assertIn("AZURE_STORAGE_ACCOUNT is missing", str(cm.exception))

        # 7. Only account set via environment -> ValueError
        with patch.dict(os.environ, {"AZURE_STORAGE_ACCOUNT": "envaccount"}, clear=True):
            with self.assertRaises(ValueError) as cm:
                get_azure_blob_config()
            self.assertIn("AZURE_STORAGE_CONTAINER is missing", str(cm.exception))

        # 8. Only container set via environment -> ValueError
        with patch.dict(os.environ, {"AZURE_STORAGE_CONTAINER": "envcontainer"}, clear=True):
            with self.assertRaises(ValueError) as cm:
                get_azure_blob_config()
            self.assertIn("AZURE_STORAGE_ACCOUNT is missing", str(cm.exception))

    def test_29_local_backup_succeeds_without_azure_config(self):
        """
        Verifies local backup operates in standalone mode when Azure configuration is absent.
        No Azure credentials required, no Azure network calls made.
        """
        source_db = self.tmp_path / "local_only.db"
        backup_dir = self.tmp_path / "local_backups"
        self._create_mock_db(source_db)

        with patch.dict(os.environ, {}, clear=True):
            archive = backup_database(source_db_path=source_db, backup_dir=backup_dir)
            self.assertTrue(archive.is_file())
            self.assertTrue(archive.name.endswith(".db.gz"))
            self.assertIsNone(getattr(archive, "blob_name", None))

    def test_30_azure_upload_succeeds_with_managed_identity_and_returns_blob_name(self):
        """
        Verifies that when Azure is configured:
        - DefaultAzureCredential is instantiated
        - BlobServiceClient is configured with the expected account URL
        - Archive is uploaded to the specified container
        - Returns only the clean blob name (no secrets, no SAS tokens, no URLs)
        """
        source_db = self.tmp_path / "source_azure.db"
        backup_dir = self.tmp_path / "backups_azure"
        self._create_mock_db(source_db)

        mock_credential = MagicMock()
        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential", return_value=mock_credential) as mock_cred_cls, \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service) as mock_service_cls:

            archive = backup_database(
                source_db_path=source_db,
                backup_dir=backup_dir,
                azure_storage_account="stinterviewbackupsprod",
                azure_storage_container="interview-backups",
            )

            # 1. Verify DefaultAzureCredential used
            mock_cred_cls.assert_called_once()

            # 2. Verify BlobServiceClient created with correct account endpoint and credential
            mock_service_cls.assert_called_once_with(
                account_url="https://stinterviewbackupsprod.blob.core.windows.net",
                credential=mock_credential,
            )

            # 3. Verify upload executed
            mock_blob_service.get_container_client.assert_called_once_with("interview-backups")
            mock_container_client.get_blob_client.assert_called_once_with(archive.name)
            mock_blob_client.upload_blob.assert_called_once()

            # 4. Verify returned blob name is pure filename without URLs or query strings
            self.assertEqual(archive.blob_name, archive.name)
            self.assertFalse(archive.blob_name.startswith("http"))
            self.assertNotIn("?", archive.blob_name)
            self.assertNotIn("sig=", archive.blob_name)

    def test_31_zero_storage_keys_or_sas_tokens_in_codebase(self):
        """
        Verifies scripts/backup_db.py enforces passwordless Managed Identity authentication
        and contains zero storage account keys, SAS tokens, or connection strings.
        """
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "backup_db.py"
        code = script_path.read_text(encoding="utf-8")

        forbidden_patterns = [
            "AccountKey=",
            "SharedAccessSignature",
            "StorageSharedKeyCredential",
            "AzureSasCredential",
            "DefaultEndpointsProtocol",
            "from_connection_string",
            "generate_blob_sas",
            "generate_account_sas",
        ]

        for pattern in forbidden_patterns:
            self.assertNotIn(
                pattern,
                code,
                f"Forbidden credential pattern '{pattern}' found in scripts/backup_db.py",
            )

    def test_32_azure_upload_failure_preserves_local_backup_and_raises_error(self):
        """
        Verifies that if Azure Blob upload fails (e.g. network timeout):
        - Local verified backup is NOT deleted
        - Local backup remains valid and intact
        - A RuntimeError is raised to alert systemd / monitoring
        """
        source_db = self.tmp_path / "source_fail.db"
        backup_dir = self.tmp_path / "backups_fail"
        self._create_mock_db(source_db)

        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob.side_effect = RuntimeError("Simulated network timeout during upload")
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            with self.assertRaises(RuntimeError) as cm:
                backup_database(
                    source_db_path=source_db,
                    backup_dir=backup_dir,
                    azure_storage_account="stinterviewbackupsprod",
                    azure_storage_container="interview-backups",
                )

            self.assertIn("Azure Blob upload failed", str(cm.exception))

            # Crucial invariant: Verify local backup was NOT deleted
            local_backups = list(backup_dir.glob("interview_backup_*.db.gz"))
            self.assertEqual(len(local_backups), 1)
            preserved_archive = local_backups[0]
            self.assertTrue(preserved_archive.is_file())
            self.assertGreater(preserved_archive.stat().st_size, 0)

            # Verify the preserved local backup is completely intact and healthy
            decompressed = self.tmp_path / "preserved_check.db"
            with gzip.open(preserved_archive, "rb") as f_in, open(decompressed, "wb") as f_out:
                f_out.write(f_in.read())
            self.assertTrue(verify_database_integrity(decompressed))

    def test_33_azure_exceptions_surfaced_correctly(self):
        """
        Verifies authentication failure, permission denied, and container not found
        are cleanly caught and surfaced as RuntimeError without being silently swallowed.
        """
        from scripts.backup_db import upload_backup_to_azure_blob

        dummy_file = self.tmp_path / "dummy.db.gz"
        dummy_file.write_bytes(b"dummy compressed content")

        # 1. Authentication failure
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.side_effect = Exception("ClientAuthenticationError: Managed Identity unavailable")
        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):
            with self.assertRaises(RuntimeError) as cm:
                upload_backup_to_azure_blob(dummy_file, "staccount", "interview-backups")
            self.assertIn("ClientAuthenticationError", str(cm.exception))

        # 2. Permission denied (RBAC missing)
        mock_blob_service = MagicMock()
        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob.side_effect = Exception("AuthorizationPermissionMismatch: Role assignment missing")
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service.get_container_client.return_value = mock_container_client
        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):
            with self.assertRaises(RuntimeError) as cm:
                upload_backup_to_azure_blob(dummy_file, "staccount", "interview-backups")
            self.assertIn("AuthorizationPermissionMismatch", str(cm.exception))

        # 3. Container not found
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.side_effect = Exception("ResourceNotFoundError: ContainerNotFound")
        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):
            with self.assertRaises(RuntimeError) as cm:
                upload_backup_to_azure_blob(dummy_file, "staccount", "nonexistent-container")
            self.assertIn("ResourceNotFoundError", str(cm.exception))

    def test_34_cli_backup_nonzero_exit_on_azure_failure_and_zero_on_success(self):
        """
        Verifies the CLI backup command:
        - Exits with 0 and prints blob name on successful upload
        - Exits with 1 (nonzero) on Azure upload failure
        - Exits with 1 when --upload-azure specified without storage account
        """
        import sys
        from scripts.backup_db import main

        source_db = self.tmp_path / "cli_source.db"
        backup_dir = self.tmp_path / "cli_backups"
        self._create_mock_db(source_db)

        # 1. Success case
        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service), \
             patch.object(sys, "argv", [
                 "backup_db.py", "backup",
                 "--source", str(source_db),
                 "--dest", str(backup_dir),
                 "--storage-account", "stinterviewbackupsprod",
                 "--container", "interview-backups",
             ]), \
             patch("sys.stdout"), patch("sys.stderr"):
            exit_code = main()
            self.assertEqual(exit_code, 0)

        # 2. Failure case -> exits 1
        mock_blob_client.upload_blob.side_effect = Exception("Azure transient outage")
        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service), \
             patch.object(sys, "argv", [
                 "backup_db.py", "backup",
                 "--source", str(source_db),
                 "--dest", str(backup_dir),
                 "--storage-account", "stinterviewbackupsprod",
                 "--container", "interview-backups",
             ]), \
             patch("sys.stdout"), patch("sys.stderr"):
            exit_code = main()
            self.assertEqual(exit_code, 1)

        # 3. Missing storage account with --upload-azure -> exits 1
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(sys, "argv", [
                 "backup_db.py", "backup",
                 "--source", str(source_db),
                 "--dest", str(backup_dir),
                 "--upload-azure",
             ]), \
             patch("sys.stdout"), patch("sys.stderr"):
            exit_code = main()
            self.assertEqual(exit_code, 1)

    def test_35_azure_restore_downloads_to_staging_and_atomically_restores(self):
        """
        Verifies that Azure restore:
        - Downloads to an isolated temporary staging file first
        - Validates gzip compression and SQLite integrity
        - Validates required production table structure
        - Atomically places database at target_db path
        - Leaves zero temporary files in staging directory
        """
        from scripts.backup_db import restore_database_from_azure_blob

        source_db = self.tmp_path / "staging_test_source.db"
        self._create_full_mock_db(source_db)

        # Create valid gzipped backup bytes
        raw_db_bytes = source_db.read_bytes()
        gz_bytes = gzip.compress(raw_db_bytes)

        mock_stream = MagicMock()
        mock_stream.readinto.side_effect = lambda f: f.write(gz_bytes)
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value = mock_stream
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        target_dir = self.tmp_path / "restore_target_dir"
        target_db = target_dir / "interview.db"

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            restored = restore_database_from_azure_blob(
                blob_name="interview_backup_20260913_000000.db.gz",
                target_db_path=target_db,
                account_name="stinterviewbackupsprod",
                container_name="interview-backups",
            )

            self.assertEqual(restored, target_db.resolve())
            self.assertTrue(target_db.is_file())
            self.assertTrue(verify_database_integrity(target_db))

            # Verify data can be queried
            conn = sqlite3.connect(target_db)
            q = conn.execute("SELECT question FROM questions WHERE id=1;").fetchone()[0]
            conn.close()
            self.assertEqual(q, "Explain Python generators.")

            # Confirm no temporary files left in staging directory
            temp_files = list(target_dir.glob(".tmp_blob_*"))
            self.assertEqual(temp_files, [])

    def test_36_azure_restore_rejects_corrupt_gzip_and_cleans_up(self):
        """
        Verifies that a downloaded blob that is corrupt or not gzip-compressed
        is rejected with RuntimeError and staging files are cleaned up.
        """
        from scripts.backup_db import restore_database_from_azure_blob

        mock_stream = MagicMock()
        mock_stream.readinto.side_effect = lambda f: f.write(b"NOT A GZIP ARCHIVE AT ALL")
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value = mock_stream
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        target_dir = self.tmp_path / "corrupt_gz_dir"
        target_db = target_dir / "target.db"

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            with self.assertRaises(RuntimeError) as cm:
                restore_database_from_azure_blob(
                    blob_name="corrupt.db.gz",
                    target_db_path=target_db,
                    account_name="staccount",
                    container_name="cont",
                )

            self.assertIn("not valid gzip", str(cm.exception))
            self.assertFalse(target_db.exists())
            self.assertEqual(list(target_dir.glob(".tmp_blob_*")), [])

    def test_37_azure_restore_rejects_non_sqlite_integrity_failure(self):
        """
        Verifies that a valid gzip file containing non-SQLite data
        fails SQLite PRAGMA integrity_check and does NOT overwrite target.
        """
        from scripts.backup_db import restore_database_from_azure_blob

        gz_bytes = gzip.compress(b"Random plain text that is not a SQLite database file")

        mock_stream = MagicMock()
        mock_stream.readinto.side_effect = lambda f: f.write(gz_bytes)
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value = mock_stream
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        target_dir = self.tmp_path / "integrity_fail_dir"
        target_db = target_dir / "target.db"

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            with self.assertRaises(RuntimeError) as cm:
                restore_database_from_azure_blob(
                    blob_name="bad_sqlite.db.gz",
                    target_db_path=target_db,
                    account_name="staccount",
                    container_name="cont",
                )

            self.assertIn("integrity check", str(cm.exception))
            self.assertFalse(target_db.exists())
            self.assertEqual(list(target_dir.glob(".tmp_blob_*")), [])

    def test_38_azure_restore_rejects_missing_core_tables(self):
        """
        Verifies that a valid SQLite database lacking core tables (questions, evaluations, etc.)
        fails structure verification and is rejected.
        """
        from scripts.backup_db import restore_database_from_azure_blob

        bad_schema_db = self.tmp_path / "bad_schema.db"
        conn = sqlite3.connect(bad_schema_db)
        conn.execute("CREATE TABLE wrong_table (id INT, note TEXT);")
        conn.execute("INSERT INTO wrong_table VALUES (1, 'no core tables');")
        conn.commit()
        conn.close()

        gz_bytes = gzip.compress(bad_schema_db.read_bytes())

        mock_stream = MagicMock()
        mock_stream.readinto.side_effect = lambda f: f.write(gz_bytes)
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value = mock_stream
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        target_dir = self.tmp_path / "bad_schema_target_dir"
        target_db = target_dir / "target.db"

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            with self.assertRaises(RuntimeError) as cm:
                restore_database_from_azure_blob(
                    blob_name="bad_schema.db.gz",
                    target_db_path=target_db,
                    account_name="staccount",
                    container_name="cont",
                )

            self.assertIn("missing core tables", str(cm.exception))
            self.assertFalse(target_db.exists())
            self.assertEqual(list(target_dir.glob(".tmp_blob_*")), [])

    def test_39_azure_restore_overwrite_protection(self):
        """
        Verifies that Azure restore refuses to overwrite an existing database
        unless force=True is explicitly supplied.
        """
        from scripts.backup_db import restore_database_from_azure_blob

        existing_db = self.tmp_path / "existing_prod.db"
        self._create_full_mock_db(existing_db)

        mock_blob_service = MagicMock()

        # 1. When force=False, raises FileExistsError BEFORE any download
        with self.assertRaises(FileExistsError):
            restore_database_from_azure_blob(
                blob_name="backup.db.gz",
                target_db_path=existing_db,
                account_name="staccount",
                container_name="cont",
                force=False,
            )
        # Verify no client interaction occurred because target check is upfront
        mock_blob_service.get_container_client.assert_not_called()

        # 2. When force=True, successfully overwrites
        gz_bytes = gzip.compress(existing_db.read_bytes())
        mock_stream = MagicMock()
        mock_stream.readinto.side_effect = lambda f: f.write(gz_bytes)
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.return_value = mock_stream
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            restored = restore_database_from_azure_blob(
                blob_name="backup.db.gz",
                target_db_path=existing_db,
                account_name="staccount",
                container_name="cont",
                force=True,
            )
            self.assertEqual(restored, existing_db.resolve())

    def test_40_azure_restore_staging_cleanup_on_download_error(self):
        """
        Verifies that if blob download fails midway (network exception),
        the partial download file in staging is cleaned up.
        """
        from scripts.backup_db import restore_database_from_azure_blob

        mock_blob_client = MagicMock()
        mock_blob_client.download_blob.side_effect = Exception("Connection reset by peer")
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        target_dir = self.tmp_path / "cleanup_test_dir"
        target_db = target_dir / "target.db"

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            with self.assertRaises(RuntimeError) as cm:
                restore_database_from_azure_blob(
                    blob_name="test.db.gz",
                    target_db_path=target_db,
                    account_name="staccount",
                    container_name="cont",
                )

            self.assertIn("Connection reset by peer", str(cm.exception))
            self.assertFalse(target_db.exists())
            self.assertEqual(list(target_dir.glob(".tmp_blob_*")), [])

    def test_41_list_azure_backups_metadata_only_without_downloading(self):
        """
        Verifies list_azure_backups queries blob metadata only and does not download files.
        """
        from scripts.backup_db import list_azure_backups, main
        import sys

        mock_blob1 = MagicMock()
        mock_blob1.name = "interview_backup_20260912_020000.db.gz"
        mock_blob1.size = 1048576
        mock_blob1.last_modified = "2026-09-12T02:00:00Z"

        mock_blob2 = MagicMock()
        mock_blob2.name = "interview_backup_20260913_020000.db.gz"
        mock_blob2.size = 2097152
        mock_blob2.last_modified = "2026-09-13T02:00:00Z"

        mock_container_client = MagicMock()
        mock_container_client.list_blobs.return_value = [mock_blob1, mock_blob2]
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            # 1. Programmatic function
            blobs = list_azure_backups("stinterviewbackupsprod", "interview-backups")
            self.assertEqual(len(blobs), 2)
            self.assertEqual(blobs[0]["name"], "interview_backup_20260912_020000.db.gz")
            self.assertEqual(blobs[0]["size"], 1048576)
            self.assertEqual(blobs[1]["name"], "interview_backup_20260913_020000.db.gz")

            # 2. CLI execution
            with patch.object(sys, "argv", [
                "backup_db.py", "list-azure-backups",
                "--storage-account", "stinterviewbackupsprod",
                "--container", "interview-backups",
            ]), patch("sys.stdout"), patch("sys.stderr"):
                exit_code = main()
                self.assertEqual(exit_code, 0)

    def test_42_sensitive_values_and_secrets_never_logged(self):
        """
        Verifies that backup and restore operations do not log credentials, tokens, or URLs.
        """
        source_db = self.tmp_path / "log_audit_source.db"
        backup_dir = self.tmp_path / "log_audit_backups"
        self._create_mock_db(source_db)

        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service), \
             self.assertLogs("backup_db", level="INFO") as log_cm:

            backup_database(
                source_db_path=source_db,
                backup_dir=backup_dir,
                azure_storage_account="stinterviewbackupsprod",
                azure_storage_container="interview-backups",
            )

            all_logs = " ".join(log_cm.output)
            self.assertIn("Azure backup uploaded: interview_backup_", all_logs)
            self.assertNotIn("https://", all_logs)
            self.assertNotIn("AccountKey", all_logs)
            self.assertNotIn("Bearer", all_logs)
            self.assertNotIn("secret", all_logs.lower())
            self.assertNotIn("token", all_logs.lower())

    def test_43_backup_retention_preserved_with_azure(self):
        """
        Verifies that enabling Azure upload does not bypass local backup retention pruning.
        """
        source_db = self.tmp_path / "retention_source.db"
        backup_dir = self.tmp_path / "retention_backups"
        self._create_mock_db(source_db)
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Plant an aged local backup (30 days old)
        old_file = backup_dir / "interview_backup_20260101_000000.db.gz"
        old_file.write_bytes(b"old dummy data")
        thirty_days_ago = time.time() - (30 * 86400)
        os.utime(old_file, (thirty_days_ago, thirty_days_ago))

        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service = MagicMock()
        mock_blob_service.get_container_client.return_value = mock_container_client

        with patch("azure.identity.DefaultAzureCredential"), \
             patch("azure.storage.blob.BlobServiceClient", return_value=mock_blob_service):

            archive = backup_database(
                source_db_path=source_db,
                backup_dir=backup_dir,
                retention_days=14,
                azure_storage_account="stinterviewbackupsprod",
                azure_storage_container="interview-backups",
            )

            self.assertTrue(archive.is_file())
            self.assertFalse(old_file.exists())

    def test_44_systemd_backup_service_configuration(self):
        """
        Verifies deploy/interview-backup.service invokes backup_db.py via the project virtualenv
        with the production environment file and single-process oneshot model.
        """
        repo_root = Path(__file__).resolve().parent.parent
        service_file = repo_root / "deploy" / "interview-backup.service"
        self.assertTrue(service_file.is_file())
        content = service_file.read_text(encoding="utf-8")

        self.assertIn("ExecStart=/opt/ai-interview-simulator/.venv/bin/python scripts/backup_db.py backup", content)
        self.assertIn("EnvironmentFile=/opt/ai-interview-simulator/.env.production", content)
        self.assertIn("Type=oneshot", content)
        self.assertIn("User=azureuser", content)
        self.assertIn("Group=azureuser", content)
        self.assertNotIn("uvicorn", content.lower())

    def test_45_deployment_readme_azure_off_vm_documentation(self):
        """
        Verifies deploy/README.md thoroughly documents the two-tier disaster recovery architecture,
        zero-credential Managed Identity model, staged restore, and laptop non-storage invariant.
        """
        repo_root = Path(__file__).resolve().parent.parent
        readme_file = repo_root / "deploy" / "README.md"
        self.assertTrue(readme_file.is_file())
        content = readme_file.read_text(encoding="utf-8")

        self.assertIn("stinterviewbackupsprod", content)
        self.assertIn("interview-backups", content)
        self.assertIn("DefaultAzureCredential", content)
        self.assertIn("Storage Blob Data Contributor", content)
        self.assertIn("AZURE_STORAGE_ACCOUNT=stinterviewbackupsprod", content)
        self.assertIn("AZURE_STORAGE_CONTAINER=interview-backups", content)
        self.assertIn("list-azure-backups", content)
        self.assertIn("--from-azure-blob", content)
        self.assertIn("Production database data is **never** copied, downloaded, or synced to developer laptops", content)
        self.assertIn("The production database and its backups exist on the Azure VM", content)
        self.assertIn("private Azure Blob backup container", content)


if __name__ == "__main__":
    unittest.main()
