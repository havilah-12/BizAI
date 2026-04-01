"""Auth helpers backed by the shared database layer."""

from __future__ import annotations

import os
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.db import create_user as db_create_user
from app.db import ensure_user, get_user, hash_password, init_db, verify_password


def init_auth_db() -> None:
    init_db()


def create_user(email: str, password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Enter a valid email")
    pwd_hash = hash_password(password)
    db_create_user(normalized, pwd_hash)


def authenticate_user(email: str, password: str) -> str:
    normalized = email.strip().lower()
    row = get_user(normalized)
    if row is None or not verify_password(password, str(row["password_hash"])):
        raise ValueError("Invalid email or password")
    return str(row["email"])


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("APP_SECRET_KEY", "dev-change-me")
    return URLSafeTimedSerializer(secret, salt="bizai-auth")


def create_access_token(email: str) -> str:
    return _serializer().dumps({"email": email})


def create_oauth_state(provider: str) -> str:
    return _serializer().dumps({"provider": provider, "nonce": secrets.token_urlsafe(16)})


def verify_oauth_state(state: str, max_age_seconds: int = 600) -> str:
    try:
        payload = _serializer().loads(state, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise ValueError("OAuth session expired. Please try again.") from e
    except BadSignature as e:
        raise ValueError("Invalid OAuth state") from e
    provider = str(payload.get("provider", "")).strip().lower()
    if not provider:
        raise ValueError("Invalid OAuth state payload")
    return provider


def ensure_oauth_user(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("OAuth provider did not return a valid email")
    ensure_user(normalized, hash_password(secrets.token_urlsafe(32)))
    return normalized


def verify_access_token(token: str, max_age_seconds: int = 60 * 60 * 24 * 7) -> str:
    try:
        payload = _serializer().loads(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise ValueError("Session expired. Please sign in again.") from e
    except BadSignature as e:
        raise ValueError("Invalid token") from e
    email = str(payload.get("email", "")).strip().lower()
    if not email:
        raise ValueError("Invalid token payload")
    return email
