from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.subscriber import CustomField
from schemas.subscriber import CustomFieldCreate, CustomFieldUpdate


def get_custom_field(db: Session, field_id: int) -> Optional[CustomField]:
    return db.query(CustomField).filter(CustomField.id == field_id).first()


def get_custom_fields_by_account(db: Session, account_id: int) -> Sequence[CustomField]:
    return db.query(CustomField).filter(CustomField.account_id == account_id).all()


def get_field_by_slug(db: Session, account_id: int, slug: str) -> Optional[CustomField]:
    return (
        db.query(CustomField)
        .filter(CustomField.account_id == account_id, CustomField.field_slug == slug)
        .first()
    )


def create_custom_field(db: Session, account_id: int, data: CustomFieldCreate) -> CustomField:
    field = CustomField(account_id=account_id, **data.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


def update_custom_field(db: Session, field_id: int, data: CustomFieldUpdate) -> Optional[CustomField]:
    field = get_custom_field(db, field_id)
    if not field:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(field, key, value)
    db.commit()
    db.refresh(field)
    return field


def delete_custom_field(db: Session, field_id: int) -> bool:
    field = get_custom_field(db, field_id)
    if not field:
        return False
    db.delete(field)
    db.commit()
    return True
