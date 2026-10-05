from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_custom_field
from schemas.subscriber import CustomFieldCreate, CustomFieldUpdate, CustomFieldOut

router = APIRouter()


@router.post("/", response_model=CustomFieldOut, status_code=201)
def create_custom_field(account_id: int, data: CustomFieldCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if crud_custom_field.get_field_by_slug(db, account_id, data.field_slug):
        raise HTTPException(status_code=409, detail="A custom field with this slug already exists")
    return crud_custom_field.create_custom_field(db, account_id, data)


@router.get("/", response_model=List[CustomFieldOut])
def list_custom_fields(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_custom_field.get_custom_fields_by_account(db, account_id)


@router.get("/{field_id}", response_model=CustomFieldOut)
def get_custom_field(field_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    field = crud_custom_field.get_custom_field(db, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Custom field not found")
    return field


@router.put("/{field_id}", response_model=CustomFieldOut)
def update_custom_field(field_id: int, data: CustomFieldUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    field = crud_custom_field.update_custom_field(db, field_id, data)
    if not field:
        raise HTTPException(status_code=404, detail="Custom field not found")
    return field


@router.delete("/{field_id}", status_code=204)
def delete_custom_field(field_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_custom_field.delete_custom_field(db, field_id):
        raise HTTPException(status_code=404, detail="Custom field not found")
