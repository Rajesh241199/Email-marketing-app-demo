"""Reusable email templates, shared header/footer blocks and uploaded images. TMP-01..12."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, false, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class BlockKind(str, enum.Enum):
    HEADER = "header"
    FOOTER = "footer"


class ContentBlock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Reusable header or footer shared by many templates (TMP-04).

    Editing a block changes every template that uses it. Campaigns are unaffected once
    created, because a campaign copies its rendered content. Footers must contain the
    business identity and unsubscribe placeholders (TMP-09); this is validated in code.
    """

    __tablename__ = "content_blocks"
    __table_args__ = (
        Index("ix_content_blocks_account_id_kind", "account_id", "kind"),
        Index(
            "uq_content_blocks_default_per_kind",
            "account_id",
            "kind",
            unique=True,
            postgresql_where=text("is_default AND deleted_at IS NULL"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    kind: Mapped[BlockKind] = mapped_column(pg_enum(BlockKind, "block_kind"))
    name: Mapped[str] = mapped_column(String(200))
    content_json: Mapped[Any] = mapped_column(JSONB)
    html: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(
        server_default=false(), comment="Used for new templates; one default per kind"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Soft delete"
    )


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (Index("ix_templates_account_id_name", "account_id", "name"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str | None] = mapped_column(String(255))
    preheader: Mapped[str | None] = mapped_column(String(255))
    header_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_blocks.id", ondelete="SET NULL")
    )
    footer_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_blocks.id", ondelete="SET NULL")
    )
    content_json: Mapped[Any] = mapped_column(
        JSONB, comment="Body blocks: text, image, button, divider, spacer (TMP-02)"
    )
    html: Mapped[str | None] = mapped_column(Text, comment="Rendered responsive HTML")
    plain_text: Mapped[str | None] = mapped_column(Text, comment="Plain-text fallback (TMP-11)")
    duplicated_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Soft delete"
    )

    header_block: Mapped[ContentBlock | None] = relationship(foreign_keys=[header_block_id])
    footer_block: Mapped[ContentBlock | None] = relationship(foreign_keys=[footer_block_id])


class MediaAsset(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "media_assets"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    file_key: Mapped[str] = mapped_column(String(512))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None]
    height: Mapped[int | None]
    alt_text: Mapped[str | None] = mapped_column(String(255), comment="TMP-10")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
