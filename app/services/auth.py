from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

import bcrypt
import jwt

from app.database import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(subject: str, extra_claims: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.auth_access_token_expire_minutes)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])


def generate_numeric_otp(length: int = 6) -> str:
    upper = 10**length
    value = secrets.randbelow(upper)
    return str(value).zfill(length)


def otp_expires_at(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def is_otp_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    return datetime.now(timezone.utc) >= expires_at
