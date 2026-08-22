"""
Auth-layer request/response schemas — separate from schemas/api.py since
these model account/identity concerns, not commitment/contact data.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

PersonaMode = Literal["student", "professional", "business"]


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters.")
    persona_mode: PersonaMode = "student"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    persona_mode: PersonaMode
    user_id: str


class UserOut(BaseModel):
    user_id: str
    email: str
    persona_mode: PersonaMode
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
