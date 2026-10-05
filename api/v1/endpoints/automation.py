from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_automation
from schemas.automation import AutomationCreate, AutomationUpdate, AutomationOut

router = APIRouter()


@router.post("/", response_model=AutomationOut, status_code=201)
def create_automation(account_id: int, data: AutomationCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_automation.create_automation(db, account_id, data)


@router.get("/", response_model=List[AutomationOut])
def list_automations(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_automation.get_automations_by_account(db, account_id)


@router.get("/{automation_id}", response_model=AutomationOut)
def get_automation(automation_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    automation = crud_automation.get_automation(db, automation_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


@router.put("/{automation_id}", response_model=AutomationOut)
def update_automation(automation_id: int, data: AutomationUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    automation = crud_automation.update_automation(db, automation_id, data)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


@router.delete("/{automation_id}", status_code=204)
def delete_automation(automation_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_automation.delete_automation(db, automation_id):
        raise HTTPException(status_code=404, detail="Automation not found")
