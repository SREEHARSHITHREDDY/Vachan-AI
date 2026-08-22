"""
Auth security primitives — password hashing and JWT creation/verification.

Uses the `bcrypt` library directly rather than passlib. passlib's bcrypt
backend does an internal version-detection check against
`bcrypt.__about__.__version__`, which modern bcrypt releases (>=4.1) no
longer expose — that raises a real, confirmed-reproducible error on hash,
not a hypothetical one. Talking to bcrypt directly avoids the entire
broken compatibility layer instead of pinning to an old bcrypt version
that would just defer the same problem to the next dependency upgrade.

The JWT secret is read via app.core.config.get_settings(), NOT
os.getenv() directly — per that module's own docstring, it's the single
place in this codebase that's supposed to touch the environment. An
earlier version of this file read os.getenv("JWT_SECRET_KEY") directly,
which was doubly wrong: it broke Settings' strict validation (an
undeclared .env key raises on startup) once JWT_SECRET_KEY was actually
added to .env, AND even after that's fixed, pydantic-settings' env_file
loading doesn't export values into os.environ — so the direct os.getenv
call would have silently kept using the insecure fallback forever,
regardless of what was in .env.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24 * 7  # 7 days — reasonable for a demo-scope single-token setup with no refresh flow yet

# bcrypt's own hard limit — anything longer is silently truncated by some
# implementations, which is worse than just rejecting it outright.
_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {_MAX_PASSWORD_BYTES} bytes.")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {"sub": user_id, "exp": expire, "purpose": "access"}
    return jwt.encode(payload, get_settings().jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user_id from a valid ACCESS token specifically —
    rejects a verification token even if it's otherwise well-formed and
    unexpired, so a leaked/logged verification link can never be replayed
    as a login session."""
    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[JWT_ALGORITHM])
    if payload.get("purpose") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload["sub"]


VERIFICATION_TOKEN_EXPIRY_HOURS = 24


def create_verification_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_EXPIRY_HOURS)
    payload = {"sub": user_id, "exp": expire, "purpose": "email_verification"}
    return jwt.encode(payload, get_settings().jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_verification_token(token: str) -> str:
    """Returns the user_id from a valid verification token specifically —
    rejects a regular access token here too, for the same reason in
    reverse (a stolen session token shouldn't be able to (re-)verify an
    arbitrary account)."""
    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[JWT_ALGORITHM])
    if payload.get("purpose") != "email_verification":
        raise jwt.InvalidTokenError("Not a verification token")
    return payload["sub"]
