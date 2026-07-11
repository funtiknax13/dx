from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITHM = "HS256"

# Token types embedded in the "type" claim so a token minted for one purpose
# (e.g. email verification) cannot be replayed as an access token.
ACCESS = "access"
REFRESH = "refresh"
VERIFY = "verify"
RESET = "reset"


def hash_password(password: str) -> str:
    return str(pwd_context.hash(password))


def verify_password(password: str, password_hash: str) -> bool:
    return bool(pwd_context.verify(password, password_hash))


def _create_token(subject: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(
        str(user_id), ACCESS, timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id), REFRESH, timedelta(days=settings.refresh_token_expire_days)
    )


def create_email_token(email: str, token_type: str, hours: int = 24) -> str:
    return _create_token(email, token_type, timedelta(hours=hours))


def decode_token(token: str, expected_type: str) -> str:
    """Return the token subject if valid and of the expected type, else raise jwt errors."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return str(payload["sub"])
