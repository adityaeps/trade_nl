import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12


def _prehash(password: str) -> bytes:
    """SHA-256 -> base64 before bcrypt.

    bcrypt silently ignores anything past 72 bytes (and raises outright in
    bcrypt 5.x), which would make two long passwords sharing a 72-byte
    prefix interchangeable. Pre-hashing to a fixed 44-byte digest makes any
    password length safe. Same approach as passlib's `bcrypt_sha256`.

    NOTE: bcrypt is used directly rather than via passlib - passlib 1.7.4
    (last release 2020) is incompatible with bcrypt 5.x and raises a
    spurious "password cannot be longer than 72 bytes" on short passwords.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed/legacy hash in the DB - treat as a failed login rather
        # than a 500, so one bad row can't break the login endpoint.
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
