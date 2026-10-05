from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from crud import crud_suppression
from schemas.suppression import PreferenceCenterData, UnsubscribeRequest, PreferenceUpdateRequest

router = APIRouter()


@router.get("/")
def get_preference_center(token: str, db: Session = Depends(get_db)):
    """Return subscriber preference center data using a one-time token."""
    data = crud_suppression.get_preference_center_data(db, token)
    if not data:
        raise HTTPException(status_code=404, detail="Invalid or expired token")
    return data


@router.post("/unsubscribe")
def one_click_unsubscribe(data: UnsubscribeRequest, db: Session = Depends(get_db)):
    """RFC 8058-compatible one-click unsubscribe."""
    subscriber = crud_suppression.process_unsubscribe(db, data.token)
    if not subscriber:
        raise HTTPException(status_code=404, detail="Invalid or already-used token")
    return {
        "message": "You have been unsubscribed successfully.",
        "email": subscriber.email,
        "status": subscriber.status.value,
    }


@router.post("/update")
def update_preferences(data: PreferenceUpdateRequest, db: Session = Depends(get_db)):
    """Update subscriber list preferences or trigger full unsubscribe."""
    if data.unsubscribe_all:
        subscriber = crud_suppression.process_unsubscribe(db, data.token)
        if not subscriber:
            raise HTTPException(status_code=404, detail="Invalid or already-used token")
        return {"message": "Unsubscribed from all marketing emails.", "email": subscriber.email}

    token_obj = crud_suppression.get_token(db, data.token)
    if not token_obj:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    from models.subscriber import Subscriber, SubscriberListMembership
    subscriber = db.query(Subscriber).filter(Subscriber.id == token_obj.subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    if data.list_ids_to_keep is not None:
        db.query(SubscriberListMembership).filter(
            SubscriberListMembership.subscriber_id == subscriber.id,
            SubscriberListMembership.list_id.notin_(data.list_ids_to_keep),
        ).delete(synchronize_session=False)
        db.commit()

    from models.suppression import PreferenceAuditLog, PreferenceChangeType, PreferenceChangeSource
    db.add(PreferenceAuditLog(
        subscriber_id=subscriber.id,
        change_type=PreferenceChangeType.PREFERENCE_UPDATED,
        source=PreferenceChangeSource.PREFERENCE_CENTER,
        metadata_json={"list_ids_kept": data.list_ids_to_keep},
    ))
    db.commit()

    return {"message": "Preferences updated successfully.", "email": subscriber.email}
