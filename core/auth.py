"""JWT-based authentication middleware."""

import hashlib
import hmac
import logging
import os
import threading
import time
from functools import wraps

from flask import jsonify, request

from core.config import config

logger = logging.getLogger(__name__)

# ── Simple user store (replace with DB in production) ────────────────────────
_users_lock = threading.Lock()
_users: dict[str, str] = {}  # username → hashed_password

# Seed default admin from env
_DEFAULT_USER = os.getenv("ADMIN_USER", "admin")
_DEFAULT_PASS = os.getenv("ADMIN_PASS", "admin123")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _init_default_user() -> None:
    with _users_lock:
        if _DEFAULT_USER not in _users:
            _users[_DEFAULT_USER] = _hash_password(_DEFAULT_PASS)


_init_default_user()


# ── JWT (manual implementation — avoids PyJWT dependency) ────────────────────

import base64
import json as _json


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _create_token(username: str, expires_in: int = 86400) -> str:
    header = _b64url_encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(_json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }).encode())
    msg = f"{header}.{payload}".encode()
    sig = hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"


def _verify_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        msg = f"{header}.{payload}".encode()
        expected_sig = hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig), expected_sig):
            return None
        data = _json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


# ── Public helpers ────────────────────────────────────────────────────────────

def login(username: str, password: str) -> str | None:
    with _users_lock:
        stored = _users.get(username)
    if stored and hmac.compare_digest(stored, _hash_password(password)):
        return _create_token(username)
    return None


def register(username: str, password: str) -> bool:
    if len(username) < 3 or len(password) < 6:
        return False
    with _users_lock:
        if username in _users:
            return False
        _users[username] = _hash_password(password)
    return True


def get_current_user() -> dict | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return _verify_token(auth[7:])
    return None


def require_auth(f):
    """Decorator — returns 401 if no valid JWT."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.getenv("AUTH_DISABLED", "false").lower() == "true":
            return f(*args, **kwargs)
        user = get_current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
