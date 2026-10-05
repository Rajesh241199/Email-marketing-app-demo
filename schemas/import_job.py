from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from models.import_job import ImportStatus

# Platform fields a CSV column can be mapped to
PLATFORM_FIELDS = [
    "email",
    "first_name",
    "last_name",
    "subscriber_id",
    "ignore",
]


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    list_id: Optional[int]
    original_filename: str
    status: ImportStatus
    total_rows: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    skipped_count: int
    field_mapping: Optional[Dict[str, str]]
    headers: Optional[List[str]]
    preview_rows: Optional[List[Dict[str, Any]]]
    error_summary: Optional[Dict[str, Any]]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ImportJobUploadResponse(BaseModel):
    job_id: int
    headers: List[str]
    preview_rows: List[Dict[str, Any]]
    total_rows: int
    message: str


class FieldMappingRequest(BaseModel):
    field_mapping: Dict[str, str]
    list_id: Optional[int] = None


class ImportJobErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    row_number: int
    raw_data: Optional[Dict[str, Any]]
    error_reason: str
    created_at: datetime
