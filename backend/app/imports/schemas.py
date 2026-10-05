from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.imports.models import ImportStatus, ImportTarget


class ImportColumnMappingIn(BaseModel):
    """One entry of the column-mapping the client submits alongside the CSV.

    The client is expected to have already previewed the file's headers and decided this
    mapping; this API only accepts the final result (see ``target`` values in
    ``ImportTarget``).
    """

    column_index: int
    target: ImportTarget
    custom_field_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _custom_field_id_matches_target(self) -> ImportColumnMappingIn:
        has_id = self.custom_field_id is not None
        if (self.target == ImportTarget.CUSTOM_FIELD) != has_id:
            raise ValueError(
                "custom_field_id is required when target is custom_field, and must be "
                "omitted otherwise"
            )
        return self


class ImportColumnMappingRead(BaseModel):
    id: uuid.UUID
    column_index: int
    source_header: str | None
    target: ImportTarget
    custom_field_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ImportJobRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    created_by: uuid.UUID
    status: ImportStatus
    file_key: str
    original_filename: str
    has_header_row: bool
    target_list_id: uuid.UUID | None
    update_existing: bool
    total_rows: int | None
    imported_count: int
    updated_count: int
    duplicate_count: int
    rejected_count: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportRowErrorRead(BaseModel):
    id: int
    import_job_id: uuid.UUID
    row_number: int
    email: str | None
    error_code: str
    raw_row: object | None

    model_config = {"from_attributes": True}
