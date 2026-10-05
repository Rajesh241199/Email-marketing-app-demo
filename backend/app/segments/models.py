"""Saved dynamic segments (SUB-09). Evaluated at send time, not stored as membership."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class SegmentMatch(str, enum.Enum):
    ALL = "all"
    ANY = "any"


class Segment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "segments"
    __table_args__ = (Index("uq_segments_account_id_name", "account_id", "name", unique=True),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(150))
    match_type: Mapped[SegmentMatch] = mapped_column(
        pg_enum(SegmentMatch, "segment_match"), server_default=SegmentMatch.ALL.value
    )
    conditions: Mapped[Any] = mapped_column(
        JSONB, comment="Rules over fields, tags, lists and status"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
