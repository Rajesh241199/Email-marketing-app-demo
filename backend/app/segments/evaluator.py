"""Evaluates a :class:`Segment`'s ``conditions`` against live subscriber data.

See ``app/segments/schemas.py`` for the exact condition-rule JSON shape this evaluator
understands. Kept deliberately simple (readable over clever) - this is not a general
query DSL, just the four rule types the schema documents.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import ColumnElement, false, select
from sqlalchemy.orm import Session

from app.segments.models import Segment, SegmentMatch
from app.subscribers.models import (
    CustomField,
    FieldType,
    ListMembership,
    MembershipStatus,
    Subscriber,
    SubscriberFieldValue,
    SubscriberStatus,
    SubscriberTag,
)


def _status_condition(cond: dict) -> ColumnElement[bool]:
    try:
        status = SubscriberStatus(cond["value"])
    except ValueError:
        return false()
    return Subscriber.status == status


def _tag_condition(cond: dict) -> ColumnElement[bool]:
    try:
        tag_id = uuid.UUID(str(cond["value"]))
    except ValueError:
        return false()
    return Subscriber.id.in_(
        select(SubscriberTag.subscriber_id).where(SubscriberTag.tag_id == tag_id)
    )


def _list_condition(cond: dict) -> ColumnElement[bool]:
    try:
        list_id = uuid.UUID(str(cond["value"]))
    except ValueError:
        return false()
    return Subscriber.id.in_(
        select(ListMembership.subscriber_id).where(
            ListMembership.list_id == list_id,
            ListMembership.status == MembershipStatus.ACTIVE,
        )
    )


_VALUE_COLUMN = {
    FieldType.TEXT: SubscriberFieldValue.value_text,
    FieldType.CHOICE: SubscriberFieldValue.value_text,
    FieldType.NUMBER: SubscriberFieldValue.value_number,
    FieldType.DATE: SubscriberFieldValue.value_date,
    FieldType.BOOLEAN: SubscriberFieldValue.value_bool,
}


def _cast_custom_field_value(data_type: FieldType, raw_value: object) -> object | None:
    try:
        if data_type in (FieldType.TEXT, FieldType.CHOICE):
            return str(raw_value)
        if data_type == FieldType.NUMBER:
            return Decimal(str(raw_value))
        if data_type == FieldType.DATE:
            from datetime import date

            return date.fromisoformat(str(raw_value))
        if data_type == FieldType.BOOLEAN:
            if isinstance(raw_value, bool):
                return raw_value
            return str(raw_value).strip().lower() in ("true", "1", "yes")
    except (InvalidOperation, ValueError, TypeError):
        return None
    return None


def _custom_field_condition(
    db: Session, account_id: uuid.UUID, cond: dict
) -> ColumnElement[bool]:
    try:
        custom_field_id = uuid.UUID(str(cond["custom_field_id"]))
    except (KeyError, ValueError):
        return false()

    field = db.get(CustomField, custom_field_id)
    if field is None or field.account_id != account_id:
        return false()

    column = _VALUE_COLUMN[field.data_type]
    op = cond.get("op")

    if op == "contains":
        if field.data_type not in (FieldType.TEXT, FieldType.CHOICE):
            return false()
        needle = str(cond.get("value", ""))
        return Subscriber.id.in_(
            select(SubscriberFieldValue.subscriber_id).where(
                SubscriberFieldValue.custom_field_id == custom_field_id,
                column.ilike(f"%{needle}%"),
            )
        )

    casted = _cast_custom_field_value(field.data_type, cond.get("value"))
    if casted is None:
        return false()

    matching = select(SubscriberFieldValue.subscriber_id).where(
        SubscriberFieldValue.custom_field_id == custom_field_id, column == casted
    )
    if op == "eq":
        return Subscriber.id.in_(matching)
    if op == "neq":
        return Subscriber.id.notin_(matching)
    return false()


def _condition_expr(db: Session, account_id: uuid.UUID, cond: dict) -> ColumnElement[bool]:
    field = cond.get("field")
    if field == "status":
        return _status_condition(cond)
    if field == "tag":
        return _tag_condition(cond)
    if field == "list":
        return _list_condition(cond)
    if field == "custom_field":
        return _custom_field_condition(db, account_id, cond)
    return false()


def resolve_segment_subscriber_ids(db: Session, segment: Segment) -> list[uuid.UUID]:
    """Return the ids of every subscriber in ``segment.account_id`` matching the segment.

    Builds one SQLAlchemy query over ``Subscriber`` (joined, via sub-selects, against
    ``SubscriberTag``, ``ListMembership`` and ``SubscriberFieldValue``), scoped to the
    segment's account. ALL combines every rule with AND, ANY with OR. No rules -> matches
    every subscriber in the account.
    """
    conditions: list[dict] = segment.conditions or []
    query = db.query(Subscriber.id).filter(Subscriber.account_id == segment.account_id)

    if conditions:
        exprs = [_condition_expr(db, segment.account_id, cond) for cond in conditions]
        if segment.match_type == SegmentMatch.ALL:
            for expr in exprs:
                query = query.filter(expr)
        else:
            from sqlalchemy import or_

            query = query.filter(or_(*exprs))

    return [row[0] for row in query.all()]
