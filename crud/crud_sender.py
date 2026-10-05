from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.sender import SenderIdentity, VerificationStatus
from schemas.sender import SenderCreate, SenderUpdate


def get_sender(db: Session, sender_id: int) -> Optional[SenderIdentity]:
    return db.query(SenderIdentity).filter(SenderIdentity.id == sender_id).first()


def get_senders_by_account(db: Session, account_id: int) -> Sequence[SenderIdentity]:
    return db.query(SenderIdentity).filter(SenderIdentity.account_id == account_id).all()


def create_sender(db: Session, account_id: int, data: SenderCreate) -> SenderIdentity:
    if data.is_default:
        db.query(SenderIdentity).filter(
            SenderIdentity.account_id == account_id
        ).update({"is_default": False})
    sender = SenderIdentity(account_id=account_id, **data.model_dump())
    db.add(sender)
    db.commit()
    db.refresh(sender)
    return sender


def update_sender(db: Session, sender_id: int, data: SenderUpdate) -> Optional[SenderIdentity]:
    sender = get_sender(db, sender_id)
    if not sender:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(sender, key, value)
    db.commit()
    db.refresh(sender)
    return sender


def delete_sender(db: Session, sender_id: int) -> bool:
    sender = get_sender(db, sender_id)
    if not sender:
        return False
    db.delete(sender)
    db.commit()
    return True


def mark_sender_verified(db: Session, sender_id: int) -> Optional[SenderIdentity]:
    sender = get_sender(db, sender_id)
    if not sender:
        return None
    sender.verification_status = VerificationStatus.VERIFIED
    db.commit()
    db.refresh(sender)
    return sender
