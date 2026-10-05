from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_account_id, get_current_user, get_db
from app.core.storage import storage
from app.templates.models import BlockKind, ContentBlock, MediaAsset, Template
from app.templates.schemas import (
    ContentBlockCreate,
    ContentBlockRead,
    ContentBlockUpdate,
    MediaAssetRead,
    TemplateCreate,
    TemplateRead,
    TemplateUpdate,
)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])
content_blocks_router = APIRouter(prefix="/api/v1/content-blocks", tags=["content-blocks"])
media_router = APIRouter(prefix="/api/v1/media", tags=["media"])


# --------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------


def _get_template(db: Session, account_id: uuid.UUID, template_id: uuid.UUID) -> Template:
    template = db.get(Template, template_id)
    if (
        template is None
        or template.account_id != account_id
        or template.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return template


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Template:
    template = Template(account_id=account_id, created_by=current_user.id, **body.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("", response_model=list[TemplateRead])
def list_templates(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[Template]:
    return (
        db.query(Template)
        .filter(Template.account_id == account_id, Template.deleted_at.is_(None))
        .order_by(Template.created_at.desc())
        .all()
    )


@router.get("/{template_id}", response_model=TemplateRead)
def get_template(
    template_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Template:
    return _get_template(db, account_id, template_id)


@router.patch("/{template_id}", response_model=TemplateRead)
def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> Template:
    template = _get_template(db, account_id, template_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    template = _get_template(db, account_id, template_id)
    template.deleted_at = datetime.now(UTC)
    db.commit()


@router.post(
    "/{template_id}/duplicate", response_model=TemplateRead, status_code=status.HTTP_201_CREATED
)
def duplicate_template(
    template_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Template:
    source = _get_template(db, account_id, template_id)
    copy = Template(
        account_id=account_id,
        name=f"{source.name} (copy)",
        subject=source.subject,
        preheader=source.preheader,
        header_block_id=source.header_block_id,
        footer_block_id=source.footer_block_id,
        content_json=source.content_json,
        html=source.html,
        plain_text=source.plain_text,
        duplicated_from_id=source.id,
        created_by=current_user.id,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


# --------------------------------------------------------------------------------------
# Content blocks (header / footer)
# --------------------------------------------------------------------------------------


def _get_block(db: Session, account_id: uuid.UUID, block_id: uuid.UUID) -> ContentBlock:
    block = db.get(ContentBlock, block_id)
    if block is None or block.account_id != account_id or block.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content block not found")
    return block


def _unset_other_defaults(
    db: Session, account_id: uuid.UUID, kind: BlockKind, except_id: uuid.UUID | None
) -> None:
    query = db.query(ContentBlock).filter(
        ContentBlock.account_id == account_id,
        ContentBlock.kind == kind,
        ContentBlock.is_default.is_(True),
        ContentBlock.deleted_at.is_(None),
    )
    if except_id is not None:
        query = query.filter(ContentBlock.id != except_id)
    query.update({"is_default": False})


@content_blocks_router.post(
    "", response_model=ContentBlockRead, status_code=status.HTTP_201_CREATED
)
def create_content_block(
    body: ContentBlockCreate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContentBlock:
    if body.is_default:
        _unset_other_defaults(db, account_id, body.kind, except_id=None)
    block = ContentBlock(account_id=account_id, created_by=current_user.id, **body.model_dump())
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@content_blocks_router.get("", response_model=list[ContentBlockRead])
def list_content_blocks(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[ContentBlock]:
    return (
        db.query(ContentBlock)
        .filter(ContentBlock.account_id == account_id, ContentBlock.deleted_at.is_(None))
        .order_by(ContentBlock.created_at.desc())
        .all()
    )


@content_blocks_router.get("/{block_id}", response_model=ContentBlockRead)
def get_content_block(
    block_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> ContentBlock:
    return _get_block(db, account_id, block_id)


@content_blocks_router.patch("/{block_id}", response_model=ContentBlockRead)
def update_content_block(
    block_id: uuid.UUID,
    body: ContentBlockUpdate,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> ContentBlock:
    block = _get_block(db, account_id, block_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        _unset_other_defaults(db, account_id, block.kind, except_id=block.id)
    for field, value in data.items():
        setattr(block, field, value)
    db.commit()
    db.refresh(block)
    return block


@content_blocks_router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content_block(
    block_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    block = _get_block(db, account_id, block_id)
    block.deleted_at = datetime.now(UTC)
    db.commit()


# --------------------------------------------------------------------------------------
# Media assets
# --------------------------------------------------------------------------------------


def _media_read(asset: MediaAsset) -> MediaAssetRead:
    return MediaAssetRead(
        id=asset.id,
        account_id=asset.account_id,
        file_key=asset.file_key,
        url=storage.url_for(asset.file_key),
        filename=asset.filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        width=asset.width,
        height=asset.height,
        alt_text=asset.alt_text,
        created_by=asset.created_by,
        created_at=asset.created_at,
    )


def _get_media(db: Session, account_id: uuid.UUID, media_id: uuid.UUID) -> MediaAsset:
    asset = db.get(MediaAsset, media_id)
    if asset is None or asset.account_id != account_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media asset not found")
    return asset


@media_router.post("", response_model=MediaAssetRead, status_code=status.HTTP_201_CREATED)
def upload_media(
    file: UploadFile,
    alt_text: str | None = Form(default=None),
    account_id: uuid.UUID = Depends(get_current_account_id),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaAssetRead:
    content = file.file.read()
    key = storage.save(filename=file.filename or "upload", content=content)
    asset = MediaAsset(
        account_id=account_id,
        file_key=key,
        filename=file.filename or key,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        alt_text=alt_text,
        created_by=current_user.id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _media_read(asset)


@media_router.get("", response_model=list[MediaAssetRead])
def list_media(
    account_id: uuid.UUID = Depends(get_current_account_id), db: Session = Depends(get_db)
) -> list[MediaAssetRead]:
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.account_id == account_id)
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
    return [_media_read(asset) for asset in assets]


@media_router.get("/{media_id}", response_model=MediaAssetRead)
def get_media(
    media_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> MediaAssetRead:
    return _media_read(_get_media(db, account_id, media_id))


@media_router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    media_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    db: Session = Depends(get_db),
) -> None:
    asset = _get_media(db, account_id, media_id)
    storage.delete(asset.file_key)
    db.delete(asset)
    db.commit()
