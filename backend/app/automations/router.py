"""Trigger > wait > email automations: CRUD for automations and their steps.

Enrollment creation (when a subscriber joins a triggering list / gets a triggering tag) and
step execution are explicitly out of scope for this bootstrap pass - see the TODO on the
enrollments endpoint below.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, null
from sqlalchemy.orm import Session

from app.automations.models import (
    Automation,
    AutomationEnrollment,
    AutomationStatus,
    AutomationStep,
    AutomationTrigger,
    StepType,
    WaitUnit,
)
from app.automations.schemas import (
    AutomationCreate,
    AutomationEnrollmentRead,
    AutomationRead,
    AutomationStepCreate,
    AutomationStepRead,
    AutomationStepUpdate,
    AutomationUpdate,
)
from app.core.deps import get_current_account_id, get_db

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])


def _get_automation(db: Session, account_id: uuid.UUID, automation_id: uuid.UUID) -> Automation:
    automation = db.get(Automation, automation_id)
    if automation is None or automation.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Automation not found")
    return automation


def _get_step(db: Session, automation: Automation, step_id: uuid.UUID) -> AutomationStep:
    step = db.get(AutomationStep, step_id)
    if step is None or step.automation_id != automation.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    return step


def _validate_trigger_target(
    trigger_type: AutomationTrigger,
    trigger_list_id: uuid.UUID | None,
    trigger_tag_id: uuid.UUID | None,
) -> None:
    """Mirrors the ``trigger_target_matches_type`` check constraint."""
    if trigger_type == AutomationTrigger.LIST_JOINED:
        if trigger_list_id is None or trigger_tag_id is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "trigger_type 'list_joined' requires trigger_list_id and no trigger_tag_id",
            )
    else:
        if trigger_tag_id is None or trigger_list_id is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "trigger_type 'tag_applied' requires trigger_tag_id and no trigger_list_id",
            )


def _validate_active_sender(
    automation_status: AutomationStatus, sender_id: uuid.UUID | None
) -> None:
    """Mirrors the ``active_has_sender`` check constraint."""
    if automation_status == AutomationStatus.ACTIVE and sender_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Activating an automation requires sender_id to be set",
        )


def _validate_step_fields(
    step_type: StepType,
    wait_amount: int | None,
    wait_unit: WaitUnit | None,
    template_id: uuid.UUID | None,
    content_json: Any | None,
) -> None:
    """Mirrors the ``step_fields_match_type`` check constraint."""
    if step_type == StepType.WAIT:
        if wait_amount is None or wait_amount <= 0 or wait_unit is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "wait steps require wait_amount > 0 and wait_unit",
            )
        if template_id is not None or content_json is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "wait steps cannot have template_id or content_json",
            )
    else:
        if wait_amount is not None or wait_unit is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "email steps cannot have wait_amount or wait_unit",
            )
        if template_id is None and content_json is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "email steps require template_id or content_json",
            )


@router.post("", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
def create_automation(
    body: AutomationCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Automation:
    _validate_trigger_target(body.trigger_type, body.trigger_list_id, body.trigger_tag_id)
    automation = Automation(account_id=account_id, **body.model_dump())
    db.add(automation)
    db.commit()
    db.refresh(automation)
    return automation


@router.get("", response_model=list[AutomationRead])
def list_automations(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[Automation]:
    return (
        db.query(Automation)
        .filter(Automation.account_id == account_id)
        .order_by(Automation.created_at.desc())
        .all()
    )


@router.get("/{automation_id}", response_model=AutomationRead)
def get_automation(
    automation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Automation:
    return _get_automation(db, account_id, automation_id)


@router.patch("/{automation_id}", response_model=AutomationRead)
def update_automation(
    automation_id: uuid.UUID,
    body: AutomationUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Automation:
    automation = _get_automation(db, account_id, automation_id)
    updates = body.model_dump(exclude_unset=True)

    new_trigger_type = updates.get("trigger_type", automation.trigger_type)
    new_trigger_list_id = updates.get("trigger_list_id", automation.trigger_list_id)
    new_trigger_tag_id = updates.get("trigger_tag_id", automation.trigger_tag_id)
    _validate_trigger_target(new_trigger_type, new_trigger_list_id, new_trigger_tag_id)

    new_status = updates.get("status", automation.status)
    new_sender_id = updates.get("sender_id", automation.sender_id)
    _validate_active_sender(new_status, new_sender_id)

    for field, value in updates.items():
        setattr(automation, field, value)

    if new_status == AutomationStatus.ACTIVE and automation.activated_at is None:
        automation.activated_at = datetime.now(UTC)

    db.commit()
    db.refresh(automation)
    return automation


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(
    automation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    automation = _get_automation(db, account_id, automation_id)
    db.delete(automation)
    db.commit()


@router.post(
    "/{automation_id}/steps", response_model=AutomationStepRead, status_code=status.HTTP_201_CREATED
)
def create_step(
    automation_id: uuid.UUID,
    body: AutomationStepCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> AutomationStep:
    automation = _get_automation(db, account_id, automation_id)
    _validate_step_fields(
        body.step_type, body.wait_amount, body.wait_unit, body.template_id, body.content_json
    )

    position = body.position
    if position is None:
        max_position = (
            db.query(func.max(AutomationStep.position))
            .filter(AutomationStep.automation_id == automation.id)
            .scalar()
        )
        position = 0 if max_position is None else max_position + 1
    else:
        conflict = (
            db.query(AutomationStep)
            .filter(
                AutomationStep.automation_id == automation.id,
                AutomationStep.position == position,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "position already in use")

    step = AutomationStep(
        automation_id=automation.id,
        position=position,
        # exclude_none: a JSON/JSONB column stores Python None as a literal JSON "null",
        # not SQL NULL (see the sqlalchemy.types.JSON docs) - omitting unset fields keeps
        # content_json truly NULL so the step_fields_match_type constraint sees it that way.
        **body.model_dump(exclude={"position"}, exclude_none=True),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@router.get("/{automation_id}/steps", response_model=list[AutomationStepRead])
def list_steps(
    automation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[AutomationStep]:
    automation = _get_automation(db, account_id, automation_id)
    return (
        db.query(AutomationStep)
        .filter(AutomationStep.automation_id == automation.id)
        .order_by(AutomationStep.position)
        .all()
    )


@router.get("/{automation_id}/steps/{step_id}", response_model=AutomationStepRead)
def get_step(
    automation_id: uuid.UUID,
    step_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> AutomationStep:
    automation = _get_automation(db, account_id, automation_id)
    return _get_step(db, automation, step_id)


@router.patch("/{automation_id}/steps/{step_id}", response_model=AutomationStepRead)
def update_step(
    automation_id: uuid.UUID,
    step_id: uuid.UUID,
    body: AutomationStepUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> AutomationStep:
    automation = _get_automation(db, account_id, automation_id)
    step = _get_step(db, automation, step_id)
    updates = body.model_dump(exclude_unset=True)

    new_step_type = updates.get("step_type", step.step_type)
    new_wait_amount = updates.get("wait_amount", step.wait_amount)
    new_wait_unit = updates.get("wait_unit", step.wait_unit)
    new_template_id = updates.get("template_id", step.template_id)
    new_content_json = updates.get("content_json", step.content_json)
    _validate_step_fields(
        new_step_type, new_wait_amount, new_wait_unit, new_template_id, new_content_json
    )

    if "position" in updates and updates["position"] != step.position:
        conflict = (
            db.query(AutomationStep)
            .filter(
                AutomationStep.automation_id == automation.id,
                AutomationStep.position == updates["position"],
                AutomationStep.id != step.id,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "position already in use")

    for field, value in updates.items():
        # content_json is JSON/JSONB: assigning Python None stores a literal JSON "null",
        # not SQL NULL, which step_fields_match_type's "content_json IS NULL" wouldn't see
        # as null - use sql.null() to force a real SQL NULL when explicitly clearing it.
        if field == "content_json" and value is None:
            setattr(step, field, null())
        else:
            setattr(step, field, value)

    db.commit()
    db.refresh(step)
    return step


@router.delete("/{automation_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_step(
    automation_id: uuid.UUID,
    step_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    automation = _get_automation(db, account_id, automation_id)
    step = _get_step(db, automation, step_id)
    db.delete(step)
    db.commit()


@router.get("/{automation_id}/enrollments", response_model=list[AutomationEnrollmentRead])
def list_enrollments(
    automation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[AutomationEnrollment]:
    # TODO: enrollment creation (on list-join / tag-apply) belongs to the subscribers/tags
    # routers, and step execution needs a scheduler/worker - neither exists in this
    # bootstrap pass. This endpoint is read-only.
    automation = _get_automation(db, account_id, automation_id)
    return (
        db.query(AutomationEnrollment)
        .filter(AutomationEnrollment.automation_id == automation.id)
        .order_by(AutomationEnrollment.entered_at)
        .all()
    )
