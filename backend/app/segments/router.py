from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_account_id, get_current_user, get_db
from app.segments.evaluator import resolve_segment_subscriber_ids
from app.segments.models import Segment
from app.segments.schemas import SegmentCreate, SegmentPreview, SegmentRead, SegmentUpdate

router = APIRouter(prefix="/api/v1/segments", tags=["segments"])


def _get_segment(db: Session, account_id: uuid.UUID, segment_id: uuid.UUID) -> Segment:
    segment = db.get(Segment, segment_id)
    if segment is None or segment.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Segment not found")
    return segment


def _dump_conditions(body: SegmentCreate | SegmentUpdate) -> list[dict] | None:
    if body.conditions is None:
        return None
    return [cond.model_dump(mode="json") for cond in body.conditions]


@router.post("", response_model=SegmentRead, status_code=status.HTTP_201_CREATED)
def create_segment(
    body: SegmentCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Segment:
    segment = Segment(
        account_id=account_id,
        name=body.name,
        match_type=body.match_type,
        conditions=_dump_conditions(body) or [],
        created_by=current_user.id,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


@router.get("", response_model=list[SegmentRead])
def list_segments(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[Segment]:
    return (
        db.query(Segment)
        .filter(Segment.account_id == account_id)
        .order_by(Segment.created_at.desc())
        .all()
    )


@router.get("/{segment_id}", response_model=SegmentRead)
def get_segment(
    segment_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Segment:
    return _get_segment(db, account_id, segment_id)


@router.patch("/{segment_id}", response_model=SegmentRead)
def update_segment(
    segment_id: uuid.UUID,
    body: SegmentUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Segment:
    segment = _get_segment(db, account_id, segment_id)
    data = body.model_dump(exclude_unset=True, exclude={"conditions"})
    for field, value in data.items():
        setattr(segment, field, value)
    if body.conditions is not None:
        segment.conditions = _dump_conditions(body)
    db.commit()
    db.refresh(segment)
    return segment


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(
    segment_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    segment = _get_segment(db, account_id, segment_id)
    db.delete(segment)
    db.commit()


@router.get("/{segment_id}/preview", response_model=SegmentPreview)
def preview_segment(
    segment_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> SegmentPreview:
    segment = _get_segment(db, account_id, segment_id)
    subscriber_ids = resolve_segment_subscriber_ids(db, segment)
    return SegmentPreview(
        count=len(subscriber_ids), sample_subscriber_ids=subscriber_ids[:20]
    )
