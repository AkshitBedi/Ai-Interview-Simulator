"""
backend/auth.py
Phase 16: Authentication and Authorization Module.

Features:
- Self-managed authentication: bcrypt password hashing (min 8 chars), email normalization.
- Stateless signed cookies using itsdangerous:
  * Account cookie: 30 days lifetime, HttpOnly, SameSite=Lax, configurable Secure.
  * Guest cookie: 7 days lifetime, HttpOnly, SameSite=Lax, configurable Secure.
- Clean AuthContext and request authentication.
- Reusable session authorization enforcing:
  * Account session: session.user_id == authenticated user.id
  * Guest session: session.guest_id == authenticated guest_id from signed cookie
  * Legacy session: accessible only by unauthenticated callers (no cookie) for backward compatibility
  * Non-disclosing 404 on authorization failure.
- Zero plaintext password storage, zero password/hash/secret leakage.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import bcrypt
import itsdangerous
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

# Constants & Configuration
DEFAULT_DEV_SECRET = "dev-auth-secret-change-in-production-1234567890"
ACCOUNT_COOKIE_NAME = "auth_token"
GUEST_COOKIE_NAME = "guest_token"
ACCOUNT_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days
GUEST_COOKIE_MAX_AGE = 7 * 24 * 60 * 60     # 7 days


def is_production() -> bool:
    """
    Checks if the application is running in production/security mode.
    Inspects ENVIRONMENT, APP_ENV, ENV, or PRODUCTION environment variables.
    """
    env_val = (
        os.environ.get("ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or os.environ.get("ENV")
        or ""
    ).strip().lower()
    if env_val in ("production", "prod"):
        return True
    if os.environ.get("PRODUCTION", "").strip().lower() in ("true", "1", "yes"):
        return True
    return False


def get_auth_secret() -> str:
    """
    Retrieves the secret key for signing tokens.

    In production mode, AUTH_SECRET_KEY is strictly required. If missing or empty,
    raises RuntimeError to fail safely rather than using a predictable/default secret.
    In development mode, uses AUTH_SECRET_KEY if provided, or falls back to DEFAULT_DEV_SECRET.
    Never hardcodes a production secret and never prints secrets in errors/logs.
    """
    secret = os.environ.get("AUTH_SECRET_KEY", "").strip()
    if is_production():
        if not secret:
            raise RuntimeError(
                "AUTH_SECRET_KEY environment variable is required in production mode."
            )
        return secret

    return secret if secret else DEFAULT_DEV_SECRET


def validate_auth_configuration() -> None:
    """
    Validates that required auth secrets are present.
    Raises RuntimeError if in production mode without AUTH_SECRET_KEY.
    """
    get_auth_secret()


def is_cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Password & Email Utilities
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    """Strips surrounding whitespace and converts to lowercase."""
    if not email or not isinstance(email, str):
        return ""
    return email.strip().lower()


def hash_password(password: str) -> str:
    """Validates length >= 8 and returns a bcrypt hash string."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Signed Stateless Token / Cookie Utilities (itsdangerous)
# ---------------------------------------------------------------------------

def get_account_serializer() -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(get_auth_secret(), salt="account-session")


def get_guest_serializer() -> itsdangerous.URLSafeTimedSerializer:
    return itsdangerous.URLSafeTimedSerializer(get_auth_secret(), salt="guest-session")


def create_account_token(user_id: int) -> str:
    s = get_account_serializer()
    payload = {
        "user_id": user_id,
        "nonce": secrets.token_hex(8)
    }
    return s.dumps(payload)


def verify_account_token(token: str, max_age: Optional[int] = None) -> Optional[dict]:
    if max_age is None:
        max_age = ACCOUNT_COOKIE_MAX_AGE
    s = get_account_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        if isinstance(data, dict) and "user_id" in data:
            return data
        return None
    except (itsdangerous.BadSignature, itsdangerous.SignatureExpired, Exception):
        return None


def create_guest_token(guest_id: str) -> str:
    s = get_guest_serializer()
    payload = {
        "guest_id": guest_id
    }
    return s.dumps(payload)


def verify_guest_token(token: str, max_age: Optional[int] = None) -> Optional[dict]:
    if max_age is None:
        max_age = GUEST_COOKIE_MAX_AGE
    s = get_guest_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        if isinstance(data, dict) and "guest_id" in data:
            return data
        return None
    except (itsdangerous.BadSignature, itsdangerous.SignatureExpired, Exception):
        return None


def set_account_cookie(response: Response, user_id: int) -> str:
    token = create_account_token(user_id)
    response.set_cookie(
        key=ACCOUNT_COOKIE_NAME,
        value=token,
        max_age=ACCOUNT_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_cookie_secure(),
        path="/"
    )
    return token


def set_guest_cookie(response: Response, guest_id: str) -> str:
    token = create_guest_token(guest_id)
    response.set_cookie(
        key=GUEST_COOKIE_NAME,
        value=token,
        max_age=GUEST_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_cookie_secure(),
        path="/"
    )
    return token


def clear_account_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCOUNT_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax"
    )


# ---------------------------------------------------------------------------
# AuthContext & Request Authentication
# ---------------------------------------------------------------------------

class AuthContext:
    def __init__(
        self,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        guest_id: Optional[str] = None
    ):
        self.user_id = user_id
        self.email = email
        self.guest_id = guest_id

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


def authenticate_request(request: Request, connection: sqlite3.Connection) -> AuthContext:
    """
    Examines cookies on request:
    1. If a valid account cookie exists and user exists in DB, returns authenticated AuthContext.
    2. Else if a valid guest cookie exists, returns guest AuthContext with guest_id.
    3. Else returns unauthenticated AuthContext.
    """
    account_token = request.cookies.get(ACCOUNT_COOKIE_NAME)
    if account_token:
        payload = verify_account_token(account_token)
        if payload and "user_id" in payload:
            user_row = connection.execute(
                "SELECT id, email FROM users WHERE id = ?",
                (payload["user_id"],)
            ).fetchone()
            if user_row:
                return AuthContext(user_id=user_row["id"], email=user_row["email"])

    guest_token = request.cookies.get(GUEST_COOKIE_NAME)
    if guest_token:
        g_payload = verify_guest_token(guest_token)
        if g_payload and "guest_id" in g_payload:
            return AuthContext(guest_id=g_payload["guest_id"])

    return AuthContext()


# ---------------------------------------------------------------------------
# Reusable Session Authorization Layer
# ---------------------------------------------------------------------------

def authorize_session(
    connection: sqlite3.Connection,
    session_id: int,
    auth_context: AuthContext
) -> sqlite3.Row:
    """
    Validates that the session exists and caller has authorization to access it.
    Returns the session_row if authorized.

    Authorization rules:
    - Account session (user_id is NOT NULL):
        Only accessible if caller is authenticated and user_id matches.
    - Guest session (guest_id is NOT NULL and user_id IS NULL):
        Only accessible if caller presents valid guest cookie matching guest_id.
    - Legacy session (user_id IS NULL and guest_id IS NULL):
        Accessible only by unauthenticated (no-cookie) callers for backward compatibility.
        Denied to authenticated accounts and guests with specific guest_id to prevent claiming/exposure.

    On any mismatch or nonexistent session, raises non-disclosing HTTPException(404, "Interview session not found").
    """
    session_row = connection.execute(
        "SELECT * FROM interview_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if session_row is None:
        raise HTTPException(status_code=404, detail="Interview session not found")

    user_id = session_row["user_id"] if "user_id" in session_row.keys() else None
    guest_id = session_row["guest_id"] if "guest_id" in session_row.keys() else None

    # Case 1: Account session
    if user_id is not None:
        if auth_context.is_authenticated and auth_context.user_id == user_id:
            return session_row
        raise HTTPException(status_code=404, detail="Interview session not found")

    # Case 2: Guest session
    if guest_id is not None:
        if auth_context.guest_id is not None and auth_context.guest_id == guest_id:
            return session_row
        raise HTTPException(status_code=404, detail="Interview session not found")

    # Case 3: Legacy session (both user_id and guest_id are NULL)
    if auth_context.user_id is None and auth_context.guest_id is None:
        return session_row

    raise HTTPException(status_code=404, detail="Interview session not found")


# ---------------------------------------------------------------------------
# Pydantic Schemas for Auth Endpoints
# ---------------------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    email: str
    password: str


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserSafeResponse(BaseModel):
    id: int
    email: str
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None
