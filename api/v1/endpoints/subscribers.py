from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_subscriber
from models.subscriber import SubscriberStatus, SubscriberListMembership, SubscriberTag
from schemas.subscriber import (
    SubscriberCreate, SubscriberUpdate, SubscriberOut, SubscriberDetail,
    SubscriberListPage, BulkIdsRequest, PreferenceLogOut, TagOut, ListOut, CustomFieldValueOut
)

router = APIRouter()


@router.post("/", response_model=SubscriberOut, status_code=201)
def create_subscriber(account_id: int, data: SubscriberCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    subscriber, created = crud_subscriber.create_subscriber(db, account_id, data)
    if not created:
        raise HTTPException(status_code=409, detail="Subscriber with this email already exists")
    return subscriber


@router.get("/", response_model=SubscriberListPage)
def list_subscribers(
    account_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    status: Optional[SubscriberStatus] = None,
    list_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    consent_source: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    total, items = crud_subscriber.list_subscribers(
        db, account_id,
        page=page, per_page=per_page,
        q=q, status=status, list_id=list_id,
        tag_id=tag_id, consent_source=consent_source,
    )
    return SubscriberListPage(total=total, page=page, per_page=per_page, items=items)


@router.get("/{subscriber_id}", response_model=SubscriberDetail)
def get_subscriber(subscriber_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    subscriber = crud_subscriber.get_subscriber(db, subscriber_id)
    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    tags = [TagOut.model_validate(a.tag) for a in subscriber.tag_associations]
    lists = [ListOut.model_validate(a.subscriber_list) for a in subscriber.list_memberships]
    cfv = [CustomFieldValueOut.model_validate(v) for v in subscriber.custom_field_values]

    detail = SubscriberDetail.model_validate(subscriber)
    detail.tags = tags
    detail.lists = lists
    detail.custom_field_values = cfv
    return detail


@router.put("/{subscriber_id}", response_model=SubscriberOut)
def update_subscriber(subscriber_id: int, data: SubscriberUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    subscriber = crud_subscriber.update_subscriber(db, subscriber_id, data)
    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    return subscriber


@router.delete("/{subscriber_id}", status_code=204)
def delete_subscriber(subscriber_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_subscriber.delete_subscriber(db, subscriber_id):
        raise HTTPException(status_code=404, detail="Subscriber not found")


@router.post("/bulk-delete")
def bulk_delete(account_id: int, data: BulkIdsRequest, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    deleted = crud_subscriber.bulk_delete(db, account_id, data.ids)
    return {"deleted": deleted}


@router.post("/bulk-unsubscribe")
def bulk_unsubscribe(account_id: int, data: BulkIdsRequest, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    updated = crud_subscriber.bulk_unsubscribe(db, account_id, data.ids)
    return {"unsubscribed": updated}


@router.get("/{subscriber_id}/history", response_model=List[PreferenceLogOut])
def preference_history(subscriber_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_subscriber.get_preference_history(db, subscriber_id)
