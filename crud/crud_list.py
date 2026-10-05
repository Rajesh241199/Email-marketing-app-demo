from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.subscriber import SubscriberList, SubscriberListMembership, Subscriber
from schemas.subscriber import ListCreate, ListUpdate


def get_list(db: Session, list_id: int) -> Optional[SubscriberList]:
    return db.query(SubscriberList).filter(SubscriberList.id == list_id).first()


def get_lists_by_account(db: Session, account_id: int) -> Sequence[SubscriberList]:
    return db.query(SubscriberList).filter(SubscriberList.account_id == account_id).all()


def create_list(db: Session, account_id: int, data: ListCreate) -> SubscriberList:
    lst = SubscriberList(account_id=account_id, **data.model_dump())
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return lst


def update_list(db: Session, list_id: int, data: ListUpdate) -> Optional[SubscriberList]:
    lst = get_list(db, list_id)
    if not lst:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(lst, key, value)
    db.commit()
    db.refresh(lst)
    return lst


def delete_list(db: Session, list_id: int) -> bool:
    lst = get_list(db, list_id)
    if not lst:
        return False
    db.delete(lst)
    db.commit()
    return True


def add_subscriber_to_list(db: Session, list_id: int, subscriber_id: int) -> bool:
    existing = (
        db.query(SubscriberListMembership)
        .filter(
            SubscriberListMembership.list_id == list_id,
            SubscriberListMembership.subscriber_id == subscriber_id,
        )
        .first()
    )
    if existing:
        return False
    db.add(SubscriberListMembership(list_id=list_id, subscriber_id=subscriber_id))
    db.commit()
    return True


def remove_subscriber_from_list(db: Session, list_id: int, subscriber_id: int) -> bool:
    m = (
        db.query(SubscriberListMembership)
        .filter(
            SubscriberListMembership.list_id == list_id,
            SubscriberListMembership.subscriber_id == subscriber_id,
        )
        .first()
    )
    if not m:
        return False
    db.delete(m)
    db.commit()
    return True


def get_list_subscribers(db: Session, list_id: int, page: int = 1, per_page: int = 50):
    query = (
        db.query(Subscriber)
        .join(SubscriberListMembership, SubscriberListMembership.subscriber_id == Subscriber.id)
        .filter(SubscriberListMembership.list_id == list_id)
    )
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return total, items
