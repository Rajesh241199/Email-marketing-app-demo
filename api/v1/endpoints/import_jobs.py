from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.config import settings
from core.deps import get_current_active_user
from crud import crud_import_job
from schemas.import_job import (
    ImportJobOut, ImportJobUploadResponse, FieldMappingRequest, ImportJobErrorOut
)

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv"}


@router.post("/upload", response_model=ImportJobUploadResponse, status_code=201)
async def upload_csv(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Step 1: Upload CSV → detect headers → return preview."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB"
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    job = crud_import_job.create_import_job_from_upload(db, account_id, file.filename, content)

    return ImportJobUploadResponse(
        job_id=job.id,
        headers=job.headers or [],
        preview_rows=job.preview_rows or [],
        total_rows=job.total_rows,
        message=f"CSV uploaded successfully. Found {len(job.headers or [])} columns and {job.total_rows} data rows.",
    )


@router.post("/{job_id}/map", response_model=ImportJobOut)
def set_mapping(
    job_id: int,
    data: FieldMappingRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Step 2: Set field mapping (column → platform field or 'ignore')."""
    job = crud_import_job.set_field_mapping(db, job_id, data)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.post("/{job_id}/process")
def process_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Step 3: Trigger background import processing."""
    job = crud_import_job.get_import_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    if not job.field_mapping:
        raise HTTPException(status_code=400, detail="Set field mapping before processing")

    from models.import_job import ImportStatus
    if job.status not in (ImportStatus.QUEUED, ImportStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Job is already in state '{job.status}' and cannot be restarted"
        )

    background_tasks.add_task(crud_import_job.process_import_job, db, job_id)
    return {"message": "Import started", "job_id": job_id}


@router.get("/{job_id}", response_model=ImportJobOut)
def get_job(job_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    """Check import status and summary."""
    job = crud_import_job.get_import_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.get("/{job_id}/errors", response_model=List[ImportJobErrorOut])
def get_job_errors(
    job_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    job = crud_import_job.get_import_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return crud_import_job.get_import_errors(db, job_id, skip=skip, limit=limit)


@router.get("/", response_model=List[ImportJobOut])
def list_jobs(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_import_job.get_import_jobs_by_account(db, account_id)
