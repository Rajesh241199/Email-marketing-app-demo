import csv
import io
import os
import uuid
from datetime import datetime, timezone
from email_validator import validate_email, EmailNotValidError
from typing import Optional, Sequence, List
from sqlalchemy.orm import Session

from core.config import settings
from models.import_job import ImportJob, ImportJobError, ImportStatus
from models.subscriber import Subscriber, SubscriberListMembership, SubscriberStatus
from models.suppression import PreferenceAuditLog, PreferenceChangeType, PreferenceChangeSource
from schemas.import_job import FieldMappingRequest

PREVIEW_ROWS = 5


def get_import_job(db: Session, job_id: int) -> Optional[ImportJob]:
    return db.query(ImportJob).filter(ImportJob.id == job_id).first()


def get_import_jobs_by_account(db: Session, account_id: int) -> Sequence[ImportJob]:
    return (
        db.query(ImportJob)
        .filter(ImportJob.account_id == account_id)
        .order_by(ImportJob.created_at.desc())
        .all()
    )


def create_import_job_from_upload(
    db: Session, account_id: int, filename: str, content: bytes
) -> ImportJob:
    """Parse CSV headers + preview, store file, create ImportJob record."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{filename}"
    stored_path = os.path.join(settings.UPLOAD_DIR, stored_name)

    with open(stored_path, "wb") as f:
        f.write(content)

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []

    preview_rows: List[dict] = []
    total_rows = 0
    for row in reader:
        total_rows += 1
        if len(preview_rows) < PREVIEW_ROWS:
            preview_rows.append(dict(row))

    job = ImportJob(
        account_id=account_id,
        original_filename=filename,
        stored_filename=stored_name,
        status=ImportStatus.QUEUED,
        total_rows=total_rows,
        headers=list(headers),
        preview_rows=preview_rows,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def set_field_mapping(db: Session, job_id: int, data: FieldMappingRequest) -> Optional[ImportJob]:
    job = get_import_job(db, job_id)
    if not job:
        return None
    job.field_mapping = data.field_mapping
    if data.list_id:
        job.list_id = data.list_id
    db.commit()
    db.refresh(job)
    return job


def process_import_job(db: Session, job_id: int):
    """Run synchronously (call from BackgroundTasks in the endpoint)."""
    job = get_import_job(db, job_id)
    if not job or not job.field_mapping:
        return

    job.status = ImportStatus.PROCESSING
    db.commit()

    stored_path = os.path.join(settings.UPLOAD_DIR, job.stored_filename or "")
    if not os.path.exists(stored_path):
        job.status = ImportStatus.FAILED
        job.error_summary = {"error": "Uploaded file not found"}
        db.commit()
        return

    try:
        with open(stored_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            imported = duplicate = invalid = skipped = 0

            for row_num, row in enumerate(reader, start=2):
                mapped = _apply_mapping(row, job.field_mapping)
                if mapped is None:
                    skipped += 1
                    continue

                email = mapped.get("email", "").strip().lower()
                if not email:
                    _add_error(db, job.id, row_num, dict(row), "Missing email address")
                    invalid += 1
                    continue

                try:
                    validate_email(email, check_deliverability=False)
                except EmailNotValidError as exc:
                    _add_error(db, job.id, row_num, dict(row), f"Invalid email: {exc}")
                    invalid += 1
                    continue

                existing = (
                    db.query(Subscriber)
                    .filter(Subscriber.account_id == job.account_id, Subscriber.email == email)
                    .first()
                )
                if existing:
                    # Never overwrite suppressed/unsubscribed status (BR-05)
                    if existing.status in (SubscriberStatus.SUPPRESSED, SubscriberStatus.UNSUBSCRIBED):
                        duplicate += 1
                        continue
                    duplicate += 1
                    continue

                sub = Subscriber(
                    account_id=job.account_id,
                    email=email,
                    first_name=mapped.get("first_name") or None,
                    last_name=mapped.get("last_name") or None,
                    status=SubscriberStatus.SUBSCRIBED,
                    consent_source="import",
                    consent_at=datetime.now(timezone.utc),
                )
                db.add(sub)
                db.flush()

                if job.list_id:
                    db.add(SubscriberListMembership(subscriber_id=sub.id, list_id=job.list_id))

                db.add(PreferenceAuditLog(
                    subscriber_id=sub.id,
                    change_type=PreferenceChangeType.SUBSCRIBED,
                    source=PreferenceChangeSource.IMPORT,
                    new_status=SubscriberStatus.SUBSCRIBED.value,
                ))
                imported += 1

            db.commit()

        job.imported_count = imported
        job.duplicate_count = duplicate
        job.invalid_count = invalid
        job.skipped_count = skipped
        job.completed_at = datetime.now(timezone.utc)
        job.status = ImportStatus.COMPLETED if invalid == 0 else ImportStatus.COMPLETED_WITH_ERRORS
        job.error_summary = {
            "imported": imported,
            "duplicates": duplicate,
            "invalid": invalid,
            "skipped": skipped,
        }
        db.commit()

    except Exception as exc:
        job.status = ImportStatus.FAILED
        job.error_summary = {"error": str(exc)}
        db.commit()


def get_import_errors(
    db: Session, job_id: int, skip: int = 0, limit: int = 100
) -> Sequence[ImportJobError]:
    return (
        db.query(ImportJobError)
        .filter(ImportJobError.import_job_id == job_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_mapping(row: dict, mapping: dict) -> Optional[dict]:
    """Convert raw CSV row to platform fields using the mapping."""
    result = {}
    for col, field in mapping.items():
        if field == "ignore" or not field:
            continue
        result[field] = row.get(col, "")
    return result


def _add_error(db: Session, job_id: int, row_num: int, raw: dict, reason: str):
    db.add(ImportJobError(import_job_id=job_id, row_number=row_num, raw_data=raw, error_reason=reason))
