from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.accounts.schemas import AccountRead, AccountUpdate, OnboardingStatus
from app.core.deps import get_current_account_id, get_db
from app.senders.models import Sender, SenderStatus

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


def _get_account(db: Session, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id)
    assert account is not None, "account_id comes from a valid access token"
    return account


@router.get("/me", response_model=AccountRead)
def get_my_account(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> Account:
    return _get_account(db, account_id)


@router.patch("/me", response_model=AccountRead)
def update_my_account(
    body: AccountUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Account:
    account = _get_account(db, account_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


@router.get("/me/onboarding-status", response_model=OnboardingStatus)
def get_onboarding_status(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> OnboardingStatus:
    account = _get_account(db, account_id)
    has_verified_sender = (
        db.query(Sender)
        .filter(Sender.account_id == account_id, Sender.status == SenderStatus.VERIFIED)
        .first()
        is not None
    )
    if has_verified_sender and account.onboarding_completed_at is None:
        account.onboarding_completed_at = datetime.now(UTC)
        db.commit()
    return OnboardingStatus(
        onboarding_completed=account.onboarding_completed_at is not None,
        has_verified_sender=has_verified_sender,
        send_ready=has_verified_sender,
    )
