import time
from collections import defaultdict

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="asterisk-web-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    """Returns the user id encoded in the token, or None if missing/invalid/expired."""
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    return int(uid) if uid is not None else None


# ------------------------------------------------------------------ #
# Login rate limiting — simple in-memory sliding window per client IP.
# Fine for a single-process, single-user residential deployment; would
# need a shared store (Redis) behind multiple workers/instances.
# ------------------------------------------------------------------ #

_login_attempts: dict[str, list[float]] = defaultdict(list)


def check_login_rate_limit(client_ip: str) -> bool:
    """Returns True if this IP is still allowed to attempt a login."""
    now = time.monotonic()
    window_start = now - settings.login_rate_limit_window_seconds
    attempts = [t for t in _login_attempts[client_ip] if t > window_start]
    _login_attempts[client_ip] = attempts
    return len(attempts) < settings.login_rate_limit_attempts


def record_login_attempt(client_ip: str) -> None:
    _login_attempts[client_ip].append(time.monotonic())
