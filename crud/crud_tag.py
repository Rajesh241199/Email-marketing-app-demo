from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.subscriber import Tag, SubscriberTag
from schemas.subscriber import TagCreate


def get_tag(db: Session, tag_id: int) -> Optional[Tag]:
    return db.query(Tag).filter(Tag.id == tag_id).first()


def get_tags_by_account(db: Session, account_id: int) -> Sequence[Tag]:
    return db.query(Tag).filter(Tag.account_id == account_id).all()


def get_tag_by_name(db: Session, account_id: int, name: str) -> Optional[Tag]:
    return (
        db.query(Tag)
        .filter(Tag.account_id == account_id, Tag.name == name)
        .first()
    )


def create_tag(db: Session, account_id: int, data: TagCreate) -> Tag:
    tag = Tag(account_id=account_id, name=data.name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag_id: int) -> bool:
    tag = get_tag(db, tag_id)
    if not tag:
        return False
    db.delete(tag)
    db.commit()
    return True


def apply_tag_to_subscriber(db: Session, tag_id: int, subscriber_id: int) -> bool:
    existing = (
        db.query(SubscriberTag)
        .filter(SubscriberTag.tag_id == tag_id, SubscriberTag.subscriber_id == subscriber_id)
        .first()
    )
    if existing:
        return False
    db.add(SubscriberTag(tag_id=tag_id, subscriber_id=subscriber_id))
    db.commit()
    return True


def remove_tag_from_subscriber(db: Session, tag_id: int, subscriber_id: int) -> bool:
    assoc = (
        db.query(SubscriberTag)
        .filter(SubscriberTag.tag_id == tag_id, SubscriberTag.subscriber_id == subscriber_id)
        .first()
    )
    if not assoc:
        return False
    db.delete(assoc)
    db.commit()
    return True
