"""
Auth routes — signup, login, and a "who am I" check.

SCOPE NOTE (important): these routes create and authenticate real User
rows with real password hashes, and issuing a real, working JWT. What
they do NOT yet do is get consumed by the rest of the app — commitments,
contacts, and the digest all still run against the single shared demo
user (_get_demo_user_id in message_processor.py), same as before this
file existed. Wiring every existing route to require and use the real
authenticated user (via app.core.deps.get_current_user_id) instead of the
demo user is a deliberate, separate follow-up — it touches every existing
endpoint and every existing test, and doing it in the same pass as
standing up auth for the first time risks breaking a working, tested,
presentation-ready build. This file is the real foundation that follow-up
will plug into, not a shortcut around it.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.security import create_access_token, hash_password, verify_password
from app.models.database import get_db
from app.models.db_models import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserOut

router = APIRouter()


@router.post("/auth/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        persona_mode=payload.persona_mode,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.user_id)
    return TokenResponse(access_token=token, persona_mode=user.persona_mode, user_id=user.user_id)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # Deliberately identical error for "no such user" and "wrong password"
    # — a different message for each would let an attacker enumerate
    # which emails have accounts on this system.
    invalid_credentials = HTTPException(status_code=401, detail="Incorrect email or password")

    if user is None or user.password_hash is None:
        raise invalid_credentials
    if not verify_password(payload.password, user.password_hash):
        raise invalid_credentials

    token = create_access_token(user.user_id)
    return TokenResponse(access_token=token, persona_mode=user.persona_mode, user_id=user.user_id)


@router.get("/auth/me", response_model=UserOut)
def get_me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)
