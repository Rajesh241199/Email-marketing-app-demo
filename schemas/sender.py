from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from models.sender import VerificationStatus, DomainAuthStatus


class SenderCreate(BaseModel):
    sender_name: str
    sender_email: EmailStr
    reply_to_email: Optional[EmailStr] = None
    is_default: bool = False


class SenderUpdate(BaseModel):
    sender_name: Optional[str] = None
    reply_to_email: Optional[EmailStr] = None
    is_default: Optional[bool] = None


class SenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    sender_name: str
    sender_email: str
    reply_to_email: Optional[str]
    verification_status: VerificationStatus
    domain_auth_status: DomainAuthStatus
    is_default: bool
