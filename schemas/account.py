from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from models.account import OnboardingStatus, UserRole, UserStatus


class AccountBase(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    business_address: Optional[str] = None
    timezone: str = "UTC"
    date_format: str = "MM/DD/YYYY"


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    onboarding_status: Optional[OnboardingStatus] = None


class AccountOut(AccountBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    onboarding_status: OnboardingStatus


# ── User ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    account_id: Optional[int] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    email_verified: bool
    first_name: Optional[str]
    last_name: Optional[str]
    role: Optional[UserRole]
    status: UserStatus
    account_id: Optional[int]
