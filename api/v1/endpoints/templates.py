from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_template
from schemas.template import (
    TemplateCreate, TemplateUpdate, TemplateOut,
    TemplateValidationResult, TemplatePreviewRequest, TemplateListPage
)

router = APIRouter()


@router.post("/", response_model=TemplateOut, status_code=201)
def create_template(account_id: int, data: TemplateCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_template.create_template(db, account_id, data)


@router.get("/", response_model=TemplateListPage)
def list_templates(
    account_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    total, items = crud_template.get_templates_by_account(
        db, account_id, page=page, per_page=per_page,
        q=q, include_archived=include_archived,
    )
    return TemplateListPage(total=total, page=page, per_page=per_page, items=items)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    template = crud_template.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, data: TemplateUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    template = crud_template.update_template(db, template_id, data)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_template.delete_template(db, template_id):
        raise HTTPException(status_code=404, detail="Template not found")


@router.post("/{template_id}/duplicate", response_model=TemplateOut, status_code=201)
def duplicate_template(template_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    copy = crud_template.duplicate_template(db, template_id)
    if not copy:
        raise HTTPException(status_code=404, detail="Template not found")
    return copy


@router.post("/{template_id}/validate", response_model=TemplateValidationResult)
def validate_template(template_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    result = crud_template.validate_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.get("/{template_id}/preview")
def preview_template(
    template_id: int,
    first_name: str = "Subscriber",
    last_name: str = "",
    email: str = "subscriber@example.com",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    template = crud_template.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    merge_data = {"first_name": first_name, "last_name": last_name, "email": email}
    rendered_html = crud_template.render_preview(template, merge_data)
    return {
        "template_id": template_id,
        "subject": template.subject,
        "rendered_html": rendered_html,
        "merge_data_used": merge_data,
    }
