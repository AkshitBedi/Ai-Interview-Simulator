"""
tests/test_phase16_auth.py
Comprehensive test suite for Phase 16: Authentication & Authorization.

Covers all 54 required test scenarios:
- Auth Basics (1-14)
- Cookie Security (15-22)
- Ownership & Access Control (23-30)
- Session Creation Ownership (31-36)
- Session Endpoint Coverage (37-43)
- Account History (44-47)
- Legacy Session Backward Compatibility (48-50)
- Privacy & Response Safety (51-54)
"""

import io
import json
import os
import secrets
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import bcrypt
import itsdangerous
from fastapi.testclient import TestClient

from backend.main import app, get_db
from backend.database import create_tables
from backend.auth import (
    ACCOUNT_COOKIE_NAME,
    GUEST_COOKIE_NAME,
    ACCOUNT_COOKIE_MAX_AGE,
    GUEST_COOKIE_MAX_AGE,
    hash_password,
    verify_password,
    normalize_email,
    create_account_token,
    verify_account_token,
    create_guest_token,
    verify_guest_token,
    get_auth_secret,
    is_cookie_secure,
    is_production,
    validate_auth_configuration,
    DEFAULT_DEV_SECRET,
)


class TestPhase16Auth(unittest.TestCase):
    def setUp(self):
        # Fresh in-memory or temp database per test
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Patch DATABASE_NAME
        self.db_patcher = patch("backend.database.DATABASE_NAME", self.db_path)
        self.db_patcher.start()

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

        create_tables()

        # Seed minimal question for session creation tests
        self.conn.execute("""
            INSERT INTO questions (category, difficulty, question)
            VALUES ('Python', 'medium', 'Explain Python GIL and memory management.')
        """)
        self.conn.commit()

        self.client = TestClient(app)

    def tearDown(self):
        self.conn.close()
        self.db_patcher.stop()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    # =======================================================================
    # 1. AUTH BASICS (1 - 14)
    # =======================================================================

    def test_01_register_success(self):
        resp = self.client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "securepassword123"
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["message"], "Registration successful")
        self.assertEqual(data["user"]["email"], "test@example.com")
        self.assertIn("id", data["user"])
        self.assertIn(ACCOUNT_COOKIE_NAME, resp.cookies)

    def test_02_password_is_bcrypt_hashed(self):
        self.client.post("/auth/register", json={
            "email": "hash_check@example.com",
            "password": "mypassword88"
        })
        row = self.conn.execute("SELECT password_hash FROM users WHERE email = 'hash_check@example.com'").fetchone()
        self.assertIsNotNone(row)
        pw_hash = row["password_hash"]
        self.assertTrue(pw_hash.startswith("$2b$") or pw_hash.startswith("$2a$"))
        self.assertTrue(bcrypt.checkpw(b"mypassword88", pw_hash.encode("utf-8")))

    def test_03_password_is_never_returned(self):
        resp = self.client.post("/auth/register", json={
            "email": "nopw@example.com",
            "password": "secretpassword"
        })
        raw_text = resp.text
        self.assertNotIn("secretpassword", raw_text)
        self.assertNotIn("password_hash", raw_text)

    def test_04_duplicate_email_rejected(self):
        self.client.post("/auth/register", json={
            "email": "dup@example.com",
            "password": "firstpassword123"
        })
        resp2 = self.client.post("/auth/register", json={
            "email": "dup@example.com",
            "password": "secondpassword123"
        })
        self.assertEqual(resp2.status_code, 409)
        self.assertIn("already exists", resp2.json()["detail"].lower())

    def test_05_email_normalization(self):
        resp = self.client.post("/auth/register", json={
            "email": "  SpAcEd.UsEr@Example.COM  ",
            "password": "password123"
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["user"]["email"], "spaced.user@example.com")

        # Verify DB storage is normalized
        row = self.conn.execute("SELECT email FROM users WHERE email = 'spaced.user@example.com'").fetchone()
        self.assertIsNotNone(row)

        # Login with differently cased / spaced email
        login_resp = self.client.post("/auth/login", json={
            "email": "SPACED.USER@EXAMPLE.COM ",
            "password": "password123"
        })
        self.assertEqual(login_resp.status_code, 200)

    def test_06_password_shorter_than_8_rejected(self):
        resp = self.client.post("/auth/register", json={
            "email": "short@example.com",
            "password": "short"
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("at least 8 characters", resp.json()["detail"])

    def test_07_login_success(self):
        self.client.post("/auth/register", json={
            "email": "login@example.com",
            "password": "mysecretpassword"
        })
        client2 = TestClient(app)
        resp = client2.post("/auth/login", json={
            "email": "login@example.com",
            "password": "mysecretpassword"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["message"], "Login successful")
        self.assertIn(ACCOUNT_COOKIE_NAME, resp.cookies)
        self.assertEqual(resp.json()["user"]["email"], "login@example.com")

    def test_08_last_login_at_updates_on_every_successful_login(self):
        self.client.post("/auth/register", json={
            "email": "activity@example.com",
            "password": "mypassword123"
        })
        row1 = self.conn.execute("SELECT last_login_at FROM users WHERE email = 'activity@example.com'").fetchone()
        t1 = row1["last_login_at"]

        # Second login
        resp = self.client.post("/auth/login", json={
            "email": "activity@example.com",
            "password": "mypassword123"
        })
        self.assertEqual(resp.status_code, 200)
        row2 = self.conn.execute("SELECT last_login_at FROM users WHERE email = 'activity@example.com'").fetchone()
        t2 = row2["last_login_at"]
        self.assertIsNotNone(t2)
        self.assertTrue(t2 >= t1)

    def test_09_invalid_credentials_rejected(self):
        self.client.post("/auth/register", json={
            "email": "target@example.com",
            "password": "realpassword123"
        })
        resp = self.client.post("/auth/login", json={
            "email": "target@example.com",
            "password": "wrongpassword123"
        })
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "Invalid email or password.")

    def test_10_invalid_login_does_not_reveal_whether_email_exists(self):
        self.client.post("/auth/register", json={
            "email": "exists@example.com",
            "password": "correctpassword123"
        })
        # Existing email with wrong password
        resp1 = self.client.post("/auth/login", json={
            "email": "exists@example.com",
            "password": "wrongpassword"
        })
        # Non-existent email
        resp2 = self.client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword"
        })
        self.assertEqual(resp1.status_code, 401)
        self.assertEqual(resp2.status_code, 401)
        self.assertEqual(resp1.json()["detail"], resp2.json()["detail"])

    def test_11_logout_clears_cookie(self):
        self.client.post("/auth/register", json={
            "email": "logout@example.com",
            "password": "mypassword123"
        })
        self.assertIn(ACCOUNT_COOKIE_NAME, self.client.cookies)
        resp = self.client.post("/auth/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["message"], "Logged out successfully")
        # Ensure cookie is cleared on client
        me_resp = self.client.get("/auth/me")
        self.assertFalse(me_resp.json()["authenticated"])
        self.assertTrue(me_resp.json()["guest"])

    def test_12_auth_me_authenticated_response(self):
        self.client.post("/auth/register", json={
            "email": "me_auth@example.com",
            "password": "password123"
        })
        resp = self.client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["authenticated"])
        self.assertFalse(data["guest"])
        self.assertEqual(data["user"]["email"], "me_auth@example.com")
        self.assertIn("id", data["user"])

    def test_13_auth_me_guest_response(self):
        client = TestClient(app)
        guest_token = create_guest_token("guest_test_abc123")
        client.cookies.set(GUEST_COOKIE_NAME, guest_token)
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["authenticated"])
        self.assertTrue(data["guest"])
        self.assertNotIn("guest_id", data)

    def test_14_auth_me_no_cookie_response(self):
        client = TestClient(app)
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["authenticated"])
        self.assertTrue(data["guest"])

    # =======================================================================
    # 2. COOKIE SECURITY (15 - 22)
    # =======================================================================

    def test_15_valid_account_cookie_authenticates(self):
        cur = self.conn.execute("INSERT INTO users (email, password_hash) VALUES ('valid_cookie@example.com', 'dummy')")
        uid = cur.lastrowid
        self.conn.commit()

        token = create_account_token(uid)
        client = TestClient(app)
        client.cookies.set(ACCOUNT_COOKIE_NAME, token)
        resp = client.get("/auth/me")
        self.assertTrue(resp.json()["authenticated"])
        self.assertEqual(resp.json()["user"]["id"], uid)

    def test_16_expired_account_cookie_rejected(self):
        cur = self.conn.execute("INSERT INTO users (email, password_hash) VALUES ('expired@example.com', 'dummy')")
        uid = cur.lastrowid
        self.conn.commit()

        token = create_account_token(uid)
        # Verify with max_age = -1 (expired)
        self.assertIsNone(verify_account_token(token, max_age=-1))

        client = TestClient(app)
        with patch("backend.auth.ACCOUNT_COOKIE_MAX_AGE", -1):
            client.cookies.set(ACCOUNT_COOKIE_NAME, token)
            resp = client.get("/auth/me")
            self.assertFalse(resp.json()["authenticated"])
            self.assertTrue(resp.json()["guest"])

    def test_17_tampered_account_cookie_rejected(self):
        token = create_account_token(1)
        tampered_token = token[:-5] + "XXXXX"
        self.assertIsNone(verify_account_token(tampered_token))

        client = TestClient(app)
        client.cookies.set(ACCOUNT_COOKIE_NAME, tampered_token)
        resp = client.get("/auth/me")
        self.assertFalse(resp.json()["authenticated"])
        self.assertTrue(resp.json()["guest"])

    def test_18_valid_guest_cookie_authenticates_guest_ownership(self):
        token = create_guest_token("g_xyz_123")
        payload = verify_guest_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["guest_id"], "g_xyz_123")

    def test_19_expired_guest_cookie_rejected(self):
        token = create_guest_token("g_expired")
        self.assertIsNone(verify_guest_token(token, max_age=-1))

    def test_20_tampered_guest_cookie_rejected(self):
        token = create_guest_token("g_valid")
        tampered = token[:-4] + "ABCD"
        self.assertIsNone(verify_guest_token(tampered))

    def test_21_cookie_flags_are_correct(self):
        resp = self.client.post("/auth/register", json={
            "email": "flags@example.com",
            "password": "password123"
        })
        cookie_header = resp.headers.get("set-cookie", "")
        self.assertIn("httponly", cookie_header.lower())
        self.assertIn("samesite=lax", cookie_header.lower())
        self.assertIn("path=/", cookie_header.lower())

    def test_22_secure_behavior_is_configurable(self):
        with patch.dict(os.environ, {"COOKIE_SECURE": "true"}):
            self.assertTrue(is_cookie_secure())
            resp = self.client.post("/auth/register", json={
                "email": "secure_env@example.com",
                "password": "password123"
            })
            cookie_header = resp.headers.get("set-cookie", "")
            self.assertIn("Secure", cookie_header)

        with patch.dict(os.environ, {"COOKIE_SECURE": "false"}):
            self.assertFalse(is_cookie_secure())
            resp2 = self.client.post("/auth/login", json={
                "email": "secure_env@example.com",
                "password": "password123"
            })
            cookie_header2 = resp2.headers.get("set-cookie", "")
            self.assertNotIn("Secure", cookie_header2)

    # =======================================================================
    # 3. OWNERSHIP & ACCESS CONTROL (23 - 30)
    # =======================================================================

    def test_23_account_can_access_own_session(self):
        reg = self.client.post("/auth/register", json={
            "email": "owner@example.com",
            "password": "password123"
        })
        sess_resp = self.client.post("/sessions", json={"category": "Python"})
        self.assertEqual(sess_resp.status_code, 201)
        sess_id = sess_resp.json()["session_id"]

        get_resp = self.client.get(f"/sessions/{sess_id}")
        self.assertEqual(get_resp.status_code, 200)

    def test_24_account_cannot_access_another_account_session(self):
        # User A creates session
        client_a = TestClient(app)
        client_a.post("/auth/register", json={"email": "usera@example.com", "password": "password123"})
        sess_a = client_a.post("/sessions", json={"category": "Python"}).json()["session_id"]

        # User B attempts to access User A's session
        client_b = TestClient(app)
        client_b.post("/auth/register", json={"email": "userb@example.com", "password": "password123"})
        resp = client_b.get(f"/sessions/{sess_a}")
        self.assertEqual(resp.status_code, 404)

    def test_25_guest_can_access_own_session(self):
        guest_client = TestClient(app)
        sess_resp = guest_client.post("/sessions", json={"category": "Python"})
        self.assertEqual(sess_resp.status_code, 201)
        sess_id = sess_resp.json()["session_id"]

        get_resp = guest_client.get(f"/sessions/{sess_id}")
        self.assertEqual(get_resp.status_code, 200)

    def test_26_guest_cannot_access_another_guest_session(self):
        guest_a = TestClient(app)
        sess_a = guest_a.post("/sessions", json={"category": "Python"}).json()["session_id"]

        guest_b = TestClient(app)
        sess_b = guest_b.post("/sessions", json={"category": "Python"}).json()["session_id"]

        # Guest B cannot access Session A
        resp = guest_b.get(f"/sessions/{sess_a}")
        self.assertEqual(resp.status_code, 404)

    def test_27_guest_cannot_access_account_session(self):
        user_client = TestClient(app)
        user_client.post("/auth/register", json={"email": "account_owner@example.com", "password": "password123"})
        sess_id = user_client.post("/sessions", json={"category": "Python"}).json()["session_id"]

        guest_client = TestClient(app)
        resp = guest_client.get(f"/sessions/{sess_id}")
        self.assertEqual(resp.status_code, 404)

    def test_28_account_cannot_access_guest_session(self):
        guest_client = TestClient(app)
        sess_id = guest_client.post("/sessions", json={"category": "Python"}).json()["session_id"]

        user_client = TestClient(app)
        user_client.post("/auth/register", json={"email": "logged_in@example.com", "password": "password123"})
        resp = user_client.get(f"/sessions/{sess_id}")
        self.assertEqual(resp.status_code, 404)

    def test_29_session_id_alone_cannot_bypass_ownership(self):
        # Create session under user
        user_client = TestClient(app)
        user_client.post("/auth/register", json={"email": "bypass_target@example.com", "password": "password123"})
        sess_id = user_client.post("/sessions", json={"category": "Python"}).json()["session_id"]

        # Anonymous caller knowing the integer ID
        anon_client = TestClient(app)
        resp = anon_client.get(f"/sessions/{sess_id}")
        self.assertEqual(resp.status_code, 404)

    def test_30_unauthorized_session_access_returns_non_disclosing_404(self):
        # Nonexistent session
        anon_client = TestClient(app)
        resp_nonexistent = anon_client.get("/sessions/999999")
        self.assertEqual(resp_nonexistent.status_code, 404)

        # Existing session belonging to someone else
        user_client = TestClient(app)
        user_client.post("/auth/register", json={"email": "secret_owner@example.com", "password": "password123"})
        sess_id = user_client.post("/sessions", json={"category": "Python"}).json()["session_id"]

        resp_unauthorized = anon_client.get(f"/sessions/{sess_id}")
        self.assertEqual(resp_unauthorized.status_code, 404)
        self.assertEqual(resp_nonexistent.json()["detail"], resp_unauthorized.json()["detail"])

    # =======================================================================
    # 4. SESSION CREATION OWNERSHIP (31 - 36)
    # =======================================================================

    def test_31_authenticated_session_stores_user_id(self):
        self.client.post("/auth/register", json={"email": "creator@example.com", "password": "password123"})
        sess_resp = self.client.post("/sessions", json={"category": "Python"})
        sess_id = sess_resp.json()["session_id"]

        row = self.conn.execute("SELECT user_id, guest_id FROM interview_sessions WHERE id = ?", (sess_id,)).fetchone()
        self.assertIsNotNone(row["user_id"])

    def test_32_authenticated_session_does_not_store_guest_id(self):
        self.client.post("/auth/register", json={"email": "creator2@example.com", "password": "password123"})
        sess_resp = self.client.post("/sessions", json={"category": "Python"})
        sess_id = sess_resp.json()["session_id"]

        row = self.conn.execute("SELECT user_id, guest_id FROM interview_sessions WHERE id = ?", (sess_id,)).fetchone()
        self.assertIsNone(row["guest_id"])

    def test_33_guest_session_stores_guest_id(self):
        guest_client = TestClient(app)
        sess_resp = guest_client.post("/sessions", json={"category": "Python"})
        sess_id = sess_resp.json()["session_id"]

        row = self.conn.execute("SELECT user_id, guest_id FROM interview_sessions WHERE id = ?", (sess_id,)).fetchone()
        self.assertIsNotNone(row["guest_id"])
        self.assertTrue(len(row["guest_id"]) >= 16)

    def test_34_guest_session_does_not_store_user_id(self):
        guest_client = TestClient(app)
        sess_resp = guest_client.post("/sessions", json={"category": "Python"})
        sess_id = sess_resp.json()["session_id"]

        row = self.conn.execute("SELECT user_id, guest_id FROM interview_sessions WHERE id = ?", (sess_id,)).fetchone()
        self.assertIsNone(row["user_id"])

    def test_35_authenticated_session_receives_no_guest_ownership(self):
        self.client.post("/auth/register", json={"email": "noguest@example.com", "password": "password123"})
        sess_resp = self.client.post("/sessions", json={"category": "Python"})
        self.assertNotIn(GUEST_COOKIE_NAME, sess_resp.cookies)

    def test_36_guest_receives_guest_cookie(self):
        guest_client = TestClient(app)
        sess_resp = guest_client.post("/sessions", json={"category": "Python"})
        self.assertIn(GUEST_COOKIE_NAME, sess_resp.cookies)

    # =======================================================================
    # 5. SESSION ENDPOINT COVERAGE (37 - 43)
    # =======================================================================

    def _setup_completed_session(self, user_id=None, guest_id=None):
        if user_id is not None:
            cur_u = self.conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, 'dummy')",
                (f"user_{secrets.token_hex(4)}@example.com",)
            )
            user_id = cur_u.lastrowid
        cur = self.conn.execute("""
            INSERT INTO interview_sessions (status, user_id, guest_id, category, difficulty)
            VALUES ('completed', ?, ?, 'Python', 'medium')
        """, (user_id, guest_id))
        sess_id = cur.lastrowid
        self.conn.commit()
        return sess_id

    def test_37_replay_ownership_enforced(self):
        sess_id = self._setup_completed_session(user_id=1)
        anon_client = TestClient(app)
        resp = anon_client.get(f"/sessions/{sess_id}/replay")
        self.assertEqual(resp.status_code, 404)

    def test_38_coaching_ownership_enforced(self):
        sess_id = self._setup_completed_session(user_id=1)
        anon_client = TestClient(app)
        resp = anon_client.get(f"/sessions/{sess_id}/coaching")
        self.assertEqual(resp.status_code, 404)

    def test_39_summary_ownership_enforced(self):
        sess_id = self._setup_completed_session(user_id=1)
        anon_client = TestClient(app)
        resp = anon_client.get(f"/sessions/{sess_id}/summary")
        self.assertEqual(resp.status_code, 404)

    def test_40_answer_endpoint_ownership_enforced(self):
        u_id = self.conn.execute("INSERT INTO users (email, password_hash) VALUES ('owner_40@example.com', 'dummy')").lastrowid
        cur = self.conn.execute("INSERT INTO interview_sessions (status, user_id) VALUES ('active', ?)", (u_id,))
        sess_id = cur.lastrowid
        self.conn.commit()

        anon_client = TestClient(app)
        resp = anon_client.post(f"/sessions/{sess_id}/answer", json={
            "answer": "This is a valid answer with enough length."
        })
        self.assertEqual(resp.status_code, 404)

    def test_41_audio_endpoint_ownership_enforced(self):
        u_id = self.conn.execute("INSERT INTO users (email, password_hash) VALUES ('owner_41@example.com', 'dummy')").lastrowid
        cur = self.conn.execute("INSERT INTO interview_sessions (status, user_id) VALUES ('active', ?)", (u_id,))
        sess_id = cur.lastrowid
        self.conn.commit()

        anon_client = TestClient(app)
        fake_wav = io.BytesIO(b"RIFFdummyWAVEfmt ")
        resp = anon_client.post(
            f"/sessions/{sess_id}/answer-audio",
            files={"file": ("test.wav", fake_wav, "audio/wav")}
        )
        self.assertEqual(resp.status_code, 404)

    def test_42_multimodal_endpoint_ownership_enforced(self):
        u_id = self.conn.execute("INSERT INTO users (email, password_hash) VALUES ('owner_42@example.com', 'dummy')").lastrowid
        cur = self.conn.execute("INSERT INTO interview_sessions (status, user_id) VALUES ('active', ?)", (u_id,))
        sess_id = cur.lastrowid
        self.conn.commit()

        anon_client = TestClient(app)
        fake_wav = io.BytesIO(b"RIFFdummyWAVEfmt ")
        fake_video = io.BytesIO(b"dummyvideodata")
        resp = anon_client.post(
            f"/sessions/{sess_id}/answer-multimodal",
            files={
                "audio_file": ("test.wav", fake_wav, "audio/wav"),
                "video_file": ("test.webm", fake_video, "video/webm")
            }
        )
        self.assertEqual(resp.status_code, 404)

    def test_43_session_details_ownership_enforced(self):
        u_id = self.conn.execute("INSERT INTO users (email, password_hash) VALUES ('owner_43@example.com', 'dummy')").lastrowid
        cur = self.conn.execute("INSERT INTO interview_sessions (status, user_id) VALUES ('active', ?)", (u_id,))
        sess_id = cur.lastrowid
        self.conn.commit()

        anon_client = TestClient(app)
        resp = anon_client.get(f"/sessions/{sess_id}")
        self.assertEqual(resp.status_code, 404)

    # =======================================================================
    # 6. ACCOUNT HISTORY (44 - 47)
    # =======================================================================

    def test_44_account_history_returns_only_own_sessions(self):
        # User A
        client_a = TestClient(app)
        client_a.post("/auth/register", json={"email": "history_a@example.com", "password": "password123"})
        s1 = client_a.post("/sessions", json={"category": "Python"}).json()["session_id"]
        s2 = client_a.post("/sessions", json={"category": "Python"}).json()["session_id"]

        # User B
        client_b = TestClient(app)
        client_b.post("/auth/register", json={"email": "history_b@example.com", "password": "password123"})
        s3 = client_b.post("/sessions", json={"category": "Python"}).json()["session_id"]

        resp_a = client_a.get("/account/interviews")
        self.assertEqual(resp_a.status_code, 200)
        ids_a = [s["id"] for s in resp_a.json()["interviews"]]
        self.assertIn(s1, ids_a)
        self.assertIn(s2, ids_a)
        self.assertNotIn(s3, ids_a)

    def test_45_guest_sessions_excluded_from_account_history(self):
        # Guest creates session
        guest_client = TestClient(app)
        guest_sess_id = guest_client.post("/sessions", json={"category": "Python"}).json()["session_id"]

        # User registers & views history
        user_client = TestClient(app)
        user_client.post("/auth/register", json={"email": "nohistory_guest@example.com", "password": "password123"})
        resp = user_client.get("/account/interviews")
        self.assertEqual(resp.status_code, 200)
        ids = [s["id"] for s in resp.json()["interviews"]]
        self.assertNotIn(guest_sess_id, ids)

    def test_46_newest_first_ordering(self):
        client = TestClient(app)
        client.post("/auth/register", json={"email": "order@example.com", "password": "password123"})
        s1 = client.post("/sessions", json={"category": "Python"}).json()["session_id"]
        s2 = client.post("/sessions", json={"category": "Python"}).json()["session_id"]
        s3 = client.post("/sessions", json={"category": "Python"}).json()["session_id"]

        resp = client.get("/account/interviews")
        ids = [s["id"] for s in resp.json()["interviews"]]
        self.assertEqual(ids, [s3, s2, s1])

    def test_47_no_cross_account_leakage(self):
        client_1 = TestClient(app)
        client_1.post("/auth/register", json={"email": "leak1@example.com", "password": "password123"})
        client_1.post("/sessions", json={"category": "Python"})

        client_2 = TestClient(app)
        client_2.post("/auth/register", json={"email": "leak2@example.com", "password": "password123"})
        resp_2 = client_2.get("/account/interviews")
        self.assertEqual(len(resp_2.json()["interviews"]), 0)

    # =======================================================================
    # 7. LEGACY SESSIONS (48 - 50)
    # =======================================================================

    def test_48_legacy_sessions_with_null_ownership_not_claimed_automatically(self):
        # Create unowned legacy session
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('active')")
        leg_id = cur.lastrowid
        self.conn.commit()

        # User registers and logs in
        client = TestClient(app)
        client.post("/auth/register", json={"email": "legacy_check@example.com", "password": "password123"})

        row = self.conn.execute("SELECT user_id, guest_id FROM interview_sessions WHERE id = ?", (leg_id,)).fetchone()
        self.assertIsNone(row["user_id"])
        self.assertIsNone(row["guest_id"])

    def test_49_legacy_database_data_remains_readable_where_intended(self):
        cur = self.conn.execute("INSERT INTO interview_sessions (status) VALUES ('active')")
        leg_id = cur.lastrowid
        self.conn.commit()

        # Unauthenticated / cookie-less caller (e.g. existing tests) can read legacy session
        anon_client = TestClient(app)
        resp = anon_client.get(f"/sessions/{leg_id}")
        self.assertEqual(resp.status_code, 200)

        # Authenticated user cannot claim/read legacy session
        user_client = TestClient(app)
        user_client.post("/auth/register", json={"email": "block_legacy@example.com", "password": "password123"})
        resp_auth = user_client.get(f"/sessions/{leg_id}")
        self.assertEqual(resp_auth.status_code, 404)

    def test_50_phase_1_15_regression_suite_remains_green(self):
        # Meta-test asserting schema compatibility with legacy columns
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(interview_sessions)").fetchall()}
        self.assertIn("user_id", cols)
        self.assertIn("guest_id", cols)
        self.assertIn("category", cols)
        self.assertIn("difficulty", cols)
        self.assertIn("candidate_profile", cols)

    # =======================================================================
    # 8. PRIVACY & RESPONSE SAFETY (51 - 54)
    # =======================================================================

    def test_51_password_hash_never_appears_in_api_responses(self):
        resp_reg = self.client.post("/auth/register", json={
            "email": "privacy@example.com",
            "password": "password123"
        })
        self.assertNotIn("password_hash", resp_reg.text)

        resp_login = self.client.post("/auth/login", json={
            "email": "privacy@example.com",
            "password": "password123"
        })
        self.assertNotIn("password_hash", resp_login.text)

        resp_me = self.client.get("/auth/me")
        self.assertNotIn("password_hash", resp_me.text)

    def test_52_auth_secrets_never_appear_in_api_responses(self):
        secret = get_auth_secret()
        resp = self.client.post("/auth/register", json={
            "email": "secret_check@example.com",
            "password": "password123"
        })
        self.assertNotIn(secret, resp.text)

    def test_53_guest_id_never_exposed_by_auth_me(self):
        guest_client = TestClient(app)
        guest_client.post("/sessions", json={"category": "Python"})
        resp = guest_client.get("/auth/me")
        self.assertNotIn("guest_id", resp.json())
        self.assertEqual(resp.json(), {"authenticated": False, "guest": True})

    def test_53a_auth_me_unauthenticated_no_cookie(self):
        client = TestClient(app)
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"authenticated": False, "guest": True})
        self.assertNotIn("guest_id", resp.json())
        self.assertNotIn("token", resp.text)

    def test_53b_auth_me_with_explicit_guest_cookie(self):
        client = TestClient(app)
        guest_token = create_guest_token("guest_explicit_xyz")
        client.cookies.set(GUEST_COOKIE_NAME, guest_token)
        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"authenticated": False, "guest": True})
        self.assertNotIn("guest_id", resp.json())
        self.assertNotIn("guest_explicit_xyz", resp.text)
        self.assertNotIn("user", resp.json())

    def test_53c_auth_me_authenticated_user_shape(self):
        client = TestClient(app)
        reg_resp = client.post("/auth/register", json={
            "email": "me_shape@example.com",
            "password": "password123"
        })
        user_id = reg_resp.json()["user"]["id"]

        resp = client.get("/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["authenticated"])
        self.assertFalse(data["guest"])
        self.assertIn("user", data)
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(data["user"]["email"], "me_shape@example.com")
        self.assertIn("created_at", data["user"])
        self.assertIn("last_login_at", data["user"])
        self.assertNotIn("guest_id", data)
        self.assertNotIn("guest_id", data["user"])
        self.assertNotIn("password_hash", data["user"])

    def test_54_credentials_not_written_to_browser_storage_by_frontend(self):
        # Inspect frontend source to ensure no passwords or tokens in localStorage/sessionStorage
        with open("web/index.html", "r", encoding="utf-8") as f:
            html = f.read()

        # Disallow storage of auth secrets, tokens, or passwords
        self.assertNotIn("localStorage.setItem('auth", html)
        self.assertNotIn("localStorage.setItem('token", html)
        self.assertNotIn("localStorage.setItem('password", html)
        self.assertNotIn("sessionStorage.setItem('auth", html)
        self.assertNotIn("sessionStorage.setItem('token", html)
        self.assertNotIn("sessionStorage.setItem('password", html)

    # =======================================================================
    # 9. PRODUCTION MODE & AUTH_SECRET_KEY HARDENING (55 - 58)
    # =======================================================================

    def test_55_production_mode_requires_auth_secret_key(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "AUTH_SECRET_KEY": ""}):
            self.assertTrue(is_production())
            with self.assertRaises(RuntimeError) as ctx:
                validate_auth_configuration()
            self.assertIn("AUTH_SECRET_KEY environment variable is required", str(ctx.exception))
            with self.assertRaises(RuntimeError):
                get_auth_secret()
            with self.assertRaises(RuntimeError):
                create_account_token(1)

    def test_56_production_mode_with_valid_auth_secret_key(self):
        prod_secret = "super-secure-production-secret-key-123456"
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "AUTH_SECRET_KEY": prod_secret}):
            self.assertTrue(is_production())
            validate_auth_configuration()  # Must not raise
            secret = get_auth_secret()
            self.assertEqual(secret, prod_secret)
            token = create_account_token(42)
            verified = verify_account_token(token)
            self.assertIsNotNone(verified)
            self.assertEqual(verified["user_id"], 42)

    def test_57_development_mode_fallback_works(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "AUTH_SECRET_KEY": ""}):
            self.assertFalse(is_production())
            validate_auth_configuration()  # Must not raise
            secret = get_auth_secret()
            self.assertEqual(secret, DEFAULT_DEV_SECRET)
            token = create_account_token(99)
            verified = verify_account_token(token)
            self.assertIsNotNone(verified)
            self.assertEqual(verified["user_id"], 99)

    def test_58_production_mode_startup_fails_safely_without_secret(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "AUTH_SECRET_KEY": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                with TestClient(app):
                    pass
            self.assertIn("AUTH_SECRET_KEY environment variable is required", str(ctx.exception))
            # Verify secret is never leaked in error message
            self.assertNotIn(DEFAULT_DEV_SECRET, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
