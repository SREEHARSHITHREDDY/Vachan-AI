"""
FastAPI dependency for protected routes — extracts and validates the
JWT from the Authorization header, returns the authenticated user_id.

Deliberately NOT wired into the existing commitments/contacts routes yet
— see the module docstring in app/routers/auth.py for why that's an
explicit, separate follow-up rather than bundled into this pass.
"""

import jwt
from fastapi import Header, HTTPException

from app.core.security import decode_access_token


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        return decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
