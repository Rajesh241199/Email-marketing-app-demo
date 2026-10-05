"""CSV subscriber imports.

Processing runs synchronously inside the request handler below (no worker/queue infra
exists yet in this codebase) - fine for the CSV sizes this pass targets, but a real
deployment should move ``_process_import`` onto a background job before large files
become common.
"""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_account_id, get_current_user, get_db
from app.core.storage import storage
from app.db.enums import ChangeSource
from app.imports.models import (
    ImportColumnMapping,
    ImportJob,
    ImportRowError,
    ImportStatus,
    ImportTarget,
)
from app.imports.schemas import (
    ImportColumnMappingIn,
    ImportJobRead,
    ImportRowErrorRead,
)
from app.subscribers.models import (
    CustomField,
    FieldType,
    ListMembership,
    MembershipStatus,
    Subscriber,
    SubscriberFieldValue,
)

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_mapping_list_adapter = TypeAdapter(list[ImportColumnMappingIn])

_FIELD_VALUE_COLUMN = {
    FieldType.TEXT: "value_text",
    FieldType.CHOICE: "value_text",
    FieldType.NUMBER: "value_number",
    FieldType.DATE: "value_date",
    FieldType.BOOLEAN: "value_bool",
}

_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no"}


def _cast_field_value(data_type: FieldType, raw: str) -> tuple[str, object] | None:
    """Cast a raw CSV string to the column/value pair for ``SubscriberFieldValue``.

    Returns ``None`` on a cast failure (caller records a row error and moves on).
    """
    column = _FIELD_VALUE_COLUMN[data_type]
    try:
        if data_type in (FieldType.TEXT, FieldType.CHOICE):
            return column, raw
        if data_type == FieldType.NUMBER:
            return column, Decimal(raw)
        if data_type == FieldType.DATE:
            return column, date.fromisoformat(raw)
        if data_type == FieldType.BOOLEAN:
            lowered = raw.strip().lower()
            if lowered in _TRUE_VALUES:
                return column, True
            if lowered in _FALSE_VALUES:
                return column, False
            return None
    except (InvalidOperation, ValueError):
        return None
    return None


def _process_import(
    db: Session,
    job: ImportJob,
    mappings: list[ImportColumnMappingIn],
    content: bytes,
    account_id: uuid.UUID,
) -> None:
    try:
        text = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error) as exc:
        job.status = ImportStatus.FAILED
        job.error_message = f"Could not parse CSV: {exc}"
        job.finished_at = datetime.now(UTC)
        return

    data_rows = rows[1:] if job.has_header_row else rows

    simple_targets = {
        ImportTarget.EMAIL,
        ImportTarget.FIRST_NAME,
        ImportTarget.LAST_NAME,
        ImportTarget.EXTERNAL_ID,
    }
    simple_mappings = [m for m in mappings if m.target in simple_targets]
    custom_field_mappings = [m for m in mappings if m.target == ImportTarget.CUSTOM_FIELD]

    total_rows = 0
    imported_count = 0
    updated_count = 0
    duplicate_count = 0
    rejected_count = 0
    has_row_errors = False
    seen_emails: set[str] = set()

    for offset, row in enumerate(data_rows, start=1):
        total_rows += 1
        row_number = offset

        def cell(column_index: int, row: list[str] = row) -> str | None:
            if 0 <= column_index < len(row):
                value = row[column_index].strip()
                return value or None
            return None

        values: dict[ImportTarget, str | None] = {
            m.target: cell(m.column_index) for m in simple_mappings
        }
        email = values.get(ImportTarget.EMAIL)

        if not email:
            db.add(
                ImportRowError(
                    import_job_id=job.id,
                    row_number=row_number,
                    email=None,
                    error_code="missing_email",
                    raw_row=row,
                )
            )
            rejected_count += 1
            has_row_errors = True
            continue

        if not _EMAIL_RE.match(email):
            db.add(
                ImportRowError(
                    import_job_id=job.id,
                    row_number=row_number,
                    email=email,
                    error_code="invalid_email",
                    raw_row=row,
                )
            )
            rejected_count += 1
            has_row_errors = True
            continue

        email_key = email.lower()
        if email_key in seen_emails:
            duplicate_count += 1
            continue
        seen_emails.add(email_key)

        existing = (
            db.query(Subscriber)
            .filter(Subscriber.account_id == account_id, Subscriber.email == email)
            .first()
        )

        if existing is None:
            subscriber = Subscriber(
                account_id=account_id,
                email=email,
                first_name=values.get(ImportTarget.FIRST_NAME),
                last_name=values.get(ImportTarget.LAST_NAME),
                external_id=values.get(ImportTarget.EXTERNAL_ID),
                source=ChangeSource.CSV_IMPORT,
                # status is intentionally never set here - the DB trigger applies
                # suppression automatically, and the column default covers everyone else.
            )
            db.add(subscriber)
            db.flush()
            imported_count += 1
            target_subscriber = subscriber
        else:
            target_subscriber = existing
            if job.update_existing:
                # Never touch `status` here - only profile fields. The opt-out trigger
                # protects status at the DB level; this is the application-level half of
                # that same rule.
                if values.get(ImportTarget.FIRST_NAME) is not None:
                    existing.first_name = values[ImportTarget.FIRST_NAME]
                if values.get(ImportTarget.LAST_NAME) is not None:
                    existing.last_name = values[ImportTarget.LAST_NAME]
                if values.get(ImportTarget.EXTERNAL_ID) is not None:
                    existing.external_id = values[ImportTarget.EXTERNAL_ID]
                updated_count += 1

        for m in custom_field_mappings:
            raw_value = cell(m.column_index)
            if raw_value is None:
                continue
            field = db.get(CustomField, m.custom_field_id)
            if field is None or field.account_id != account_id:
                continue
            casted = _cast_field_value(field.data_type, raw_value)
            if casted is None:
                db.add(
                    ImportRowError(
                        import_job_id=job.id,
                        row_number=row_number,
                        email=email,
                        error_code="invalid_custom_field_value",
                        raw_row=row,
                    )
                )
                has_row_errors = True
                continue
            column, value = casted
            field_value = db.get(
                SubscriberFieldValue, (target_subscriber.id, field.id)
            )
            if field_value is None:
                field_value = SubscriberFieldValue(
                    subscriber_id=target_subscriber.id, custom_field_id=field.id
                )
                db.add(field_value)
            setattr(field_value, column, value)

        if job.target_list_id is not None:
            membership = db.get(
                ListMembership, (job.target_list_id, target_subscriber.id)
            )
            if membership is None:
                db.add(
                    ListMembership(
                        list_id=job.target_list_id,
                        subscriber_id=target_subscriber.id,
                        source=ChangeSource.CSV_IMPORT,
                    )
                )
            elif membership.status == MembershipStatus.OPTED_OUT:
                pass  # never resubscribe an opted-out membership from an import

        db.flush()

    job.total_rows = total_rows
    job.imported_count = imported_count
    job.updated_count = updated_count
    job.duplicate_count = duplicate_count
    job.rejected_count = rejected_count
    job.status = ImportStatus.COMPLETED_WITH_ERRORS if has_row_errors else ImportStatus.COMPLETED
    job.finished_at = datetime.now(UTC)


@router.post("", response_model=ImportJobRead, status_code=status.HTTP_201_CREATED)
def create_import(
    file: UploadFile,
    column_mapping: str = Form(...),
    target_list_id: uuid.UUID | None = Form(default=None),
    update_existing: bool = Form(default=False),
    account_id: uuid.UUID = Depends(get_current_account_id),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportJob:
    try:
        mappings = _mapping_list_adapter.validate_python(json.loads(column_mapping))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid column_mapping: {exc}"
        ) from exc

    content = file.file.read()
    file_key = storage.save(filename=file.filename or "import.csv", content=content)

    now = datetime.now(UTC)
    job = ImportJob(
        account_id=account_id,
        created_by=current_user.id,
        status=ImportStatus.PROCESSING,
        file_key=file_key,
        original_filename=file.filename or "import.csv",
        has_header_row=True,
        target_list_id=target_list_id,
        update_existing=update_existing,
        started_at=now,
    )
    db.add(job)
    db.flush()

    for m in mappings:
        db.add(
            ImportColumnMapping(
                import_job_id=job.id,
                column_index=m.column_index,
                target=m.target,
                custom_field_id=m.custom_field_id,
            )
        )
    db.flush()

    _process_import(db, job, mappings, content, account_id)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[ImportJobRead])
def list_imports(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[ImportJob]:
    return (
        db.query(ImportJob)
        .filter(ImportJob.account_id == account_id)
        .order_by(ImportJob.created_at.desc())
        .all()
    )


def _get_import(db: Session, account_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import job not found")
    return job


@router.get("/{job_id}", response_model=ImportJobRead)
def get_import(
    job_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> ImportJob:
    return _get_import(db, account_id, job_id)


@router.get("/{job_id}/errors", response_model=list[ImportRowErrorRead])
def list_import_errors(
    job_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> list[ImportRowError]:
    job = _get_import(db, account_id, job_id)
    return (
        db.query(ImportRowError)
        .filter(ImportRowError.import_job_id == job.id)
        .order_by(ImportRowError.row_number)
        .offset(skip)
        .limit(limit)
        .all()
    )
