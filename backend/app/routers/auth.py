"""
Auth routes — signup, email verification, login, and a "who am I" check.

Verification flow: signup creates the account (unverified) and emails a
link to app.core.deps... no — to GET /auth/verify-email?token=..., which
this file itself serves. Clicking that link is the actual "yes, it's me"
proof the user asked for. Login checks is_verified and rejects
unverified accounts with a clear message, rather than silently letting
an unverified account in.

SCOPE NOTE (still applies, carried over from before verification existed):
commitments, contacts, and the digest are now genuinely scoped to the
real authenticated user (see app/routers/commitments.py and contacts.py)
— that per-user isolation work is done. Persona-specific FEATURE
differences (a student account seeing something different from a
business account) are still not built — persona_mode is stored and
returned, but nothing in the app branches on it yet.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user_id
from app.core.email import EmailNotConfiguredError, send_verification_email
from app.core.security import (
    create_access_token,
    create_verification_token,
    decode_verification_token,
    hash_password,
    verify_password,
)
from app.models.database import get_db
from app.models.db_models import User
from app.schemas.auth import (
    LoginRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UpdateMeRequest,
    UserOut,
)

router = APIRouter()


@router.post("/auth/signup", response_model=SignupResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        persona_mode=payload.persona_mode,
        is_verified=False,  # explicit here — the column default (True)
        # only exists for pre-auth fixture/demo users; every real signup
        # starts unverified regardless of that default.
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    verification_token = create_verification_token(user.user_id)
    verification_link = f"{get_settings().backend_base_url}/api/v1/auth/verify-email?token={verification_token}"

    try:
        send_verification_email(user.email, verification_link)
    except EmailNotConfiguredError as e:
        # The account still exists — don't roll it back over an email
        # config problem — but the user needs to know verification isn't
        # actually possible yet rather than silently waiting on an email
        # that will never arrive.
        raise HTTPException(status_code=500, detail=str(e))

    return SignupResponse(user_id=user.user_id, email=user.email)


@router.get("/auth/verify-email", response_class=HTMLResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    """
    The link the user actually clicks, from their email client — returns
    a plain HTML page (not JSON) since a browser opens this directly, not
    the frontend app calling it as an API.
    """
    import jwt as jwt_lib

    def render(title: str, message: str) -> str:
        return f"""
        <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 60px 20px; background: #0d0f1a; color: #eef0f3;">
          <h2 style="color: #7c9eff;">{title}</h2>
          <p>{message}</p>
        </body></html>
        """

    try:
        user_id = decode_verification_token(token)
    except jwt_lib.ExpiredSignatureError:
        return render("Link Expired", "This verification link has expired. Please sign up again to receive a new one.")
    except jwt_lib.InvalidTokenError:
        return render("Invalid Link", "This verification link is invalid.")

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        return render("Account Not Found", "This account no longer exists.")

    if user.is_verified:
        return render("Already Verified", "Your email is already verified — you can log in.")

    user.is_verified = True
    db.commit()

    return render("Email Verified ✓", "Your account is now verified. You can close this tab and log in.")


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    invalid_credentials = HTTPException(status_code=401, detail="Incorrect email or password")

    if user is None or user.password_hash is None:
        raise invalid_credentials
    if not verify_password(payload.password, user.password_hash):
        raise invalid_credentials

    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in — check your inbox for the verification link.",
        )

    token = create_access_token(user.user_id)
    return TokenResponse(access_token=token, persona_mode=user.persona_mode, user_id=user.user_id)


@router.get("/auth/me", response_model=UserOut)
def get_me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


@router.patch("/auth/me", response_model=UserOut)
def update_me(
    payload: UpdateMeRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Currently only persona_mode is changeable here — email/password
    changes aren't built (no "confirm current password" or re-verification
    flow exists yet, and shipping that without it would be a real
    security gap, not just an unfinished feature). Letting someone
    switch which persona view they're in (e.g. a student who's since
    started freelancing) is safe to allow immediately since nothing
    currently branches on persona_mode beyond storing/displaying it.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.persona_mode is not None:
        user.persona_mode = payload.persona_mode

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
