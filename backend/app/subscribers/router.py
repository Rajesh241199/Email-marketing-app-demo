"""Subscribers, lists, tags and custom fields. SUB-01..12, PREF-02..04, PREF-09.

Route order matters: the literal ``/lists``, ``/tags`` and ``/fields`` paths are
registered before the ``/{subscriber_id}`` path so they aren't swallowed by the
``{subscriber_id}`` path parameter.

Status changes (subscribe/unsubscribe) are out of scope here: subscribers.status is never
set by this router (it's left at its server default on create and never exposed on
update), and list_memberships only ever moves active -> opted_out here. Re-subscription /
re-opt-in flows are handled elsewhere and must set the ``app.allow_resubscribe`` flag that
app/db/triggers.py checks for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automations.models import (
    Automation,
    AutomationEnrollment,
    AutomationStatus,
    AutomationTrigger,
    EnrollmentStatus,
)
from app.core.deps import get_current_account_id, get_db
from app.subscribers.models import (
    CustomField,
    FieldType,
    ListMembership,
    MailingList,
    MembershipStatus,
    Subscriber,
    SubscriberFieldValue,
    SubscriberStatus,
    SubscriberTag,
    Tag,
)
from app.subscribers.schemas import (
    CustomFieldCreate,
    CustomFieldRead,
    CustomFieldUpdate,
    ListMembershipRead,
    MailingListCreate,
    MailingListRead,
    MailingListUpdate,
    SubscriberCreate,
    SubscriberFieldValueRead,
    SubscriberFieldValueSet,
    SubscriberRead,
    SubscriberUpdate,
    TagCreate,
    TagRead,
)

router = APIRouter(prefix="/api/v1/subscribers", tags=["subscribers"])


# --- lookups (404, never leak cross-account existence) ----------------------


def _get_subscriber(db: Session, account_id: uuid.UUID, subscriber_id: uuid.UUID) -> Subscriber:
    subscriber = db.get(Subscriber, subscriber_id)
    if subscriber is None or subscriber.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscriber not found")
    return subscriber


def _get_mailing_list(db: Session, account_id: uuid.UUID, list_id: uuid.UUID) -> MailingList:
    mailing_list = db.get(MailingList, list_id)
    if mailing_list is None or mailing_list.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return mailing_list


def _get_tag(db: Session, account_id: uuid.UUID, tag_id: uuid.UUID) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None or tag.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    return tag


def _get_custom_field(
    db: Session, account_id: uuid.UUID, custom_field_id: uuid.UUID
) -> CustomField:
    field = db.get(CustomField, custom_field_id)
    if field is None or field.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Custom field not found")
    return field


# --- automation enrollment hook ---------------------------------------------


def _enroll_in_matching_automations(
    db: Session,
    account_id: uuid.UUID,
    subscriber_id: uuid.UUID,
    trigger_type: AutomationTrigger,
    trigger_target_id: uuid.UUID,
) -> None:
    """Create/reset AutomationEnrollment rows for active automations matching this trigger.

    Only creates the enrollment row; nothing here executes automation steps (that's a
    worker's job, out of scope for this bootstrap pass).

    Judgment call: automation_enrollments has a unique constraint on
    (automation_id, subscriber_id), so a subscriber can never have two rows for the same
    automation. For allow_reentry automations, "re-enrolling" therefore resets the existing
    completed/exited row back to active rather than inserting a second row.
    """
    target_column = (
        Automation.trigger_list_id
        if trigger_type == AutomationTrigger.LIST_JOINED
        else Automation.trigger_tag_id
    )
    automations = (
        db.query(Automation)
        .filter(
            Automation.account_id == account_id,
            Automation.status == AutomationStatus.ACTIVE,
            Automation.trigger_type == trigger_type,
            target_column == trigger_target_id,
        )
        .all()
    )
    for automation in automations:
        existing = (
            db.query(AutomationEnrollment)
            .filter(
                AutomationEnrollment.automation_id == automation.id,
                AutomationEnrollment.subscriber_id == subscriber_id,
            )
            .first()
        )
        if existing is None:
            db.add(
                AutomationEnrollment(
                    automation_id=automation.id,
                    subscriber_id=subscriber_id,
                    status=EnrollmentStatus.ACTIVE,
                    current_step_id=None,
                    next_run_at=datetime.now(UTC),
                )
            )
        elif automation.allow_reentry and existing.status != EnrollmentStatus.ACTIVE:
            existing.status = EnrollmentStatus.ACTIVE
            existing.current_step_id = None
            existing.next_run_at = datetime.now(UTC)
            existing.completed_at = None
            existing.exit_reason = None
        # else: already active, or completed/exited with allow_reentry=False -> skip.


# --- Mailing lists -----------------------------------------------------------


@router.post("/lists", response_model=MailingListRead, status_code=status.HTTP_201_CREATED)
def create_list(
    body: MailingListCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> MailingList:
    mailing_list = MailingList(account_id=account_id, **body.model_dump())
    db.add(mailing_list)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A list with this name already exists"
        ) from exc
    db.refresh(mailing_list)
    return mailing_list


@router.get("/lists", response_model=list[MailingListRead])
def list_lists(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[MailingList]:
    return db.query(MailingList).filter(MailingList.account_id == account_id).all()


@router.get("/lists/{list_id}", response_model=MailingListRead)
def get_list(
    list_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> MailingList:
    return _get_mailing_list(db, account_id, list_id)


@router.patch("/lists/{list_id}", response_model=MailingListRead)
def update_list(
    list_id: uuid.UUID,
    body: MailingListUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> MailingList:
    mailing_list = _get_mailing_list(db, account_id, list_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(mailing_list, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A list with this name already exists"
        ) from exc
    db.refresh(mailing_list)
    return mailing_list


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    mailing_list = _get_mailing_list(db, account_id, list_id)
    db.delete(mailing_list)
    db.commit()


# --- Tags ---------------------------------------------------------------------


@router.post("/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def create_tag(
    body: TagCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Tag:
    tag = Tag(account_id=account_id, name=body.name)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A tag with this name already exists"
        ) from exc
    db.refresh(tag)
    return tag


@router.get("/tags", response_model=list[TagRead])
def list_tags(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[Tag]:
    return db.query(Tag).filter(Tag.account_id == account_id).all()


@router.get("/tags/{tag_id}", response_model=TagRead)
def get_tag(
    tag_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Tag:
    return _get_tag(db, account_id, tag_id)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    tag = _get_tag(db, account_id, tag_id)
    db.delete(tag)
    db.commit()


# --- Custom fields -------------------------------------------------------------


@router.post("/fields", response_model=CustomFieldRead, status_code=status.HTTP_201_CREATED)
def create_custom_field(
    body: CustomFieldCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CustomField:
    field = CustomField(account_id=account_id, **body.model_dump())
    db.add(field)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A custom field with this key already exists"
        ) from exc
    db.refresh(field)
    return field


@router.get("/fields", response_model=list[CustomFieldRead])
def list_custom_fields(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[CustomField]:
    return db.query(CustomField).filter(CustomField.account_id == account_id).all()


@router.get("/fields/{custom_field_id}", response_model=CustomFieldRead)
def get_custom_field(
    custom_field_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CustomField:
    return _get_custom_field(db, account_id, custom_field_id)


@router.patch("/fields/{custom_field_id}", response_model=CustomFieldRead)
def update_custom_field(
    custom_field_id: uuid.UUID,
    body: CustomFieldUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> CustomField:
    field = _get_custom_field(db, account_id, custom_field_id)
    for attr, value in body.model_dump(exclude_unset=True).items():
        setattr(field, attr, value)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/fields/{custom_field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_field(
    custom_field_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    field = _get_custom_field(db, account_id, custom_field_id)
    db.delete(field)
    db.commit()


# --- Subscribers ---------------------------------------------------------------


@router.post("", response_model=SubscriberRead, status_code=status.HTTP_201_CREATED)
def create_subscriber(
    body: SubscriberCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Subscriber:
    subscriber = Subscriber(account_id=account_id, **body.model_dump())
    db.add(subscriber)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A subscriber with this email already exists"
        ) from exc
    db.refresh(subscriber)
    return subscriber


@router.get("", response_model=list[SubscriberRead])
def list_subscribers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: SubscriberStatus | None = Query(None, alias="status"),
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[Subscriber]:
    query = db.query(Subscriber).filter(Subscriber.account_id == account_id)
    if status_filter is not None:
        query = query.filter(Subscriber.status == status_filter)
    return query.order_by(Subscriber.created_at).offset(offset).limit(limit).all()


@router.get("/{subscriber_id}", response_model=SubscriberRead)
def get_subscriber(
    subscriber_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Subscriber:
    return _get_subscriber(db, account_id, subscriber_id)


@router.patch("/{subscriber_id}", response_model=SubscriberRead)
def update_subscriber(
    subscriber_id: uuid.UUID,
    body: SubscriberUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Subscriber:
    subscriber = _get_subscriber(db, account_id, subscriber_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(subscriber, field, value)
    db.commit()
    db.refresh(subscriber)
    return subscriber


@router.delete("/{subscriber_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscriber(
    subscriber_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    subscriber = _get_subscriber(db, account_id, subscriber_id)
    db.delete(subscriber)
    db.commit()


# --- List membership -----------------------------------------------------------


@router.post(
    "/{subscriber_id}/lists/{list_id}",
    response_model=ListMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_subscriber_to_list(
    subscriber_id: uuid.UUID,
    list_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> ListMembership:
    _get_subscriber(db, account_id, subscriber_id)
    _get_mailing_list(db, account_id, list_id)

    membership = db.get(ListMembership, (list_id, subscriber_id))
    if membership is not None:
        if membership.status == MembershipStatus.ACTIVE:
            return membership
        # opted_out -> active is rejected by the DB trigger (app/db/triggers.py) unless
        # the resubscribe flag is set, which this bootstrap pass doesn't implement.
        # Surface it as a clear conflict instead of letting the trigger's raw exception
        # bubble up, rather than working around the trigger.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Subscriber previously opted out of this list; re-adding requires the "
            "resubscribe flow",
        )

    membership = ListMembership(
        list_id=list_id, subscriber_id=subscriber_id, status=MembershipStatus.ACTIVE
    )
    db.add(membership)
    db.flush()
    _enroll_in_matching_automations(
        db, account_id, subscriber_id, AutomationTrigger.LIST_JOINED, list_id
    )
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/{subscriber_id}/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_subscriber_from_list(
    subscriber_id: uuid.UUID,
    list_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    _get_subscriber(db, account_id, subscriber_id)
    _get_mailing_list(db, account_id, list_id)

    membership = db.get(ListMembership, (list_id, subscriber_id))
    if membership is None or membership.status == MembershipStatus.OPTED_OUT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List membership not found")

    membership.status = MembershipStatus.OPTED_OUT
    membership.removed_at = datetime.now(UTC)
    db.commit()


# --- Subscriber tags ------------------------------------------------------------


@router.post(
    "/{subscriber_id}/tags/{tag_id}",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
)
def apply_tag_to_subscriber(
    subscriber_id: uuid.UUID,
    tag_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Tag:
    _get_subscriber(db, account_id, subscriber_id)
    tag = _get_tag(db, account_id, tag_id)

    existing = db.get(SubscriberTag, (subscriber_id, tag_id))
    if existing is None:
        db.add(SubscriberTag(subscriber_id=subscriber_id, tag_id=tag_id))
        db.flush()
        _enroll_in_matching_automations(
            db, account_id, subscriber_id, AutomationTrigger.TAG_APPLIED, tag_id
        )
        db.commit()
    return tag


@router.delete("/{subscriber_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tag_from_subscriber(
    subscriber_id: uuid.UUID,
    tag_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    _get_subscriber(db, account_id, subscriber_id)
    _get_tag(db, account_id, tag_id)

    existing = db.get(SubscriberTag, (subscriber_id, tag_id))
    if existing is not None:
        db.delete(existing)
        db.commit()


# --- Subscriber custom field values ----------------------------------------------


@router.put("/{subscriber_id}/fields/{custom_field_id}", response_model=SubscriberFieldValueRead)
def set_subscriber_field_value(
    subscriber_id: uuid.UUID,
    custom_field_id: uuid.UUID,
    body: SubscriberFieldValueSet,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> SubscriberFieldValue:
    _get_subscriber(db, account_id, subscriber_id)
    field = _get_custom_field(db, account_id, custom_field_id)

    value_text: str | None = None
    value_number: Decimal | None = None
    value_date: date | None = None
    value_bool: bool | None = None

    if body.value is not None:
        if field.data_type in (FieldType.TEXT, FieldType.CHOICE):
            if not isinstance(body.value, str):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected a text value for this field"
                )
            value_text = body.value
        elif field.data_type == FieldType.NUMBER:
            if isinstance(body.value, bool):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected a numeric value for this field"
                )
            try:
                value_number = Decimal(str(body.value))
            except (InvalidOperation, ValueError) as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected a numeric value for this field"
                ) from exc
        elif field.data_type == FieldType.DATE:
            if isinstance(body.value, str):
                try:
                    value_date = date.fromisoformat(body.value)
                except ValueError as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "Expected an ISO date (YYYY-MM-DD) for this field",
                    ) from exc
            else:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Expected an ISO date (YYYY-MM-DD) for this field",
                )
        elif field.data_type == FieldType.BOOLEAN:
            if not isinstance(body.value, bool):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected a boolean value for this field"
                )
            value_bool = body.value

    value_row = db.get(SubscriberFieldValue, (subscriber_id, custom_field_id))
    if value_row is None:
        value_row = SubscriberFieldValue(
            subscriber_id=subscriber_id, custom_field_id=custom_field_id
        )
        db.add(value_row)

    value_row.value_text = value_text
    value_row.value_number = value_number
    value_row.value_date = value_date
    value_row.value_bool = value_bool

    db.commit()
    db.refresh(value_row)
    return value_row
