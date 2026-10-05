"""Sending domains and sender identities. ONB-04, ONB-05, BR-02.

Note: route order matters here. The literal ``/domains`` paths are registered before the
``/{sender_id}`` paths so a request to ``/api/v1/senders/domains`` doesn't get swallowed by
the ``{sender_id}`` path parameter.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_account_id, get_db
from app.senders.models import Sender, SenderStatus, SendingDomain
from app.senders.schemas import (
    SenderCreate,
    SenderRead,
    SenderUpdate,
    SendingDomainCreate,
    SendingDomainRead,
)

router = APIRouter(prefix="/api/v1/senders", tags=["senders"])


def _get_domain(db: Session, account_id: uuid.UUID, domain_id: uuid.UUID) -> SendingDomain:
    domain = db.get(SendingDomain, domain_id)
    if domain is None or domain.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sending domain not found")
    return domain


def _get_sender(db: Session, account_id: uuid.UUID, sender_id: uuid.UUID) -> Sender:
    sender = db.get(Sender, sender_id)
    if sender is None or sender.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sender not found")
    return sender


def _unset_other_defaults(db: Session, account_id: uuid.UUID, keep_id: uuid.UUID | None) -> None:
    """Only one sender per account may be default; clear it on every other sender."""
    query = db.query(Sender).filter(Sender.account_id == account_id, Sender.is_default.is_(True))
    if keep_id is not None:
        query = query.filter(Sender.id != keep_id)
    query.update({"is_default": False})


# --- Sending domains --------------------------------------------------------


@router.post("/domains", response_model=SendingDomainRead, status_code=status.HTTP_201_CREATED)
def create_sending_domain(
    body: SendingDomainCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> SendingDomain:
    domain = SendingDomain(account_id=account_id, domain=body.domain)
    db.add(domain)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Domain already added") from exc
    db.refresh(domain)
    return domain


@router.get("/domains", response_model=list[SendingDomainRead])
def list_sending_domains(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[SendingDomain]:
    return db.query(SendingDomain).filter(SendingDomain.account_id == account_id).all()


@router.get("/domains/{domain_id}", response_model=SendingDomainRead)
def get_sending_domain(
    domain_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> SendingDomain:
    return _get_domain(db, account_id, domain_id)


@router.delete("/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sending_domain(
    domain_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    domain = _get_domain(db, account_id, domain_id)
    db.delete(domain)
    db.commit()


# --- Senders -----------------------------------------------------------------


@router.post("", response_model=SenderRead, status_code=status.HTTP_201_CREATED)
def create_sender(
    body: SenderCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Sender:
    if body.sending_domain_id is not None:
        _get_domain(db, account_id, body.sending_domain_id)

    if body.is_default:
        _unset_other_defaults(db, account_id, keep_id=None)

    sender = Sender(
        account_id=account_id,
        sending_domain_id=body.sending_domain_id,
        from_name=body.from_name,
        from_email=body.from_email,
        reply_to_email=body.reply_to_email,
        is_default=body.is_default,
    )
    db.add(sender)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A sender with this from_email already exists"
        ) from exc
    db.refresh(sender)
    return sender


@router.get("", response_model=list[SenderRead])
def list_senders(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[Sender]:
    return db.query(Sender).filter(Sender.account_id == account_id).all()


@router.get("/{sender_id}", response_model=SenderRead)
def get_sender(
    sender_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Sender:
    return _get_sender(db, account_id, sender_id)


@router.patch("/{sender_id}", response_model=SenderRead)
def update_sender(
    sender_id: uuid.UUID,
    body: SenderUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Sender:
    sender = _get_sender(db, account_id, sender_id)
    data = body.model_dump(exclude_unset=True)

    if data.get("is_default"):
        _unset_other_defaults(db, account_id, keep_id=sender.id)

    for field, value in data.items():
        setattr(sender, field, value)

    db.commit()
    db.refresh(sender)
    return sender


@router.delete("/{sender_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sender(
    sender_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    sender = _get_sender(db, account_id, sender_id)
    db.delete(sender)
    db.commit()


@router.patch("/{sender_id}/verify", response_model=SenderRead)
def verify_sender(
    sender_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Sender:
    # TODO: dev-only stand-in for the real email-provider verification flow (e.g. an SES
    # identity-verification callback); there's no provider integration in this bootstrap pass.
    sender = _get_sender(db, account_id, sender_id)
    sender.status = SenderStatus.VERIFIED
    sender.verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(sender)
    return sender
