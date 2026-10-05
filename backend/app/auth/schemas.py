from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.auth.models import UserRole


class AccountCreate(BaseModel):
    name: str = Field(max_length=200)
    website: str | None = Field(default=None, max_length=255)
    country_code: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    address_line1: str = Field(max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str = Field(default="UTC", max_length=64)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    full_name: str | None = Field(default=None, max_length=200)


class RegisterRequest(BaseModel):
    account: AccountCreate
    user: UserCreate


class UserRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterResponse(TokenResponse):
    user: UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=255)
