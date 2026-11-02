"""Password hashing and access tokens. Plain passwords are never stored or logged."""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 10
ALGORITHM = "HS256"
TOKEN_MINUTES = 8 * 60

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password-used-for-timing")


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def waste_verify_time(password: str) -> None:
    """Spend the same time as a real check, so unknown users are not revealed."""
    verify_password(password, _DUMMY_HASH)


def create_access_token(
    user_id: int, role: str, secret: str, now: datetime | None = None
) -> str:
    issued = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": issued,
        "exp": issued + timedelta(minutes=TOKEN_MINUTES),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError:
        return None