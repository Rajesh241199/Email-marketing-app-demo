from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import get_current_active_user
from crud.crud_sender import (
    get_sender, get_senders_by_account, create_sender,
    update_sender, delete_sender, mark_sender_verified
)
from schemas.sender import SenderCreate, SenderUpdate, SenderOut

router = APIRouter()


@router.post("/", response_model=SenderOut, status_code=201)
def create_new_sender(account_id: int, data: SenderCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return create_sender(db, account_id, data)


@router.get("/", response_model=List[SenderOut])
def list_senders(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return get_senders_by_account(db, account_id)


@router.get("/{sender_id}", response_model=SenderOut)
def get_one_sender(sender_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    sender = get_sender(db, sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    return sender


@router.put("/{sender_id}", response_model=SenderOut)
def update_one_sender(sender_id: int, data: SenderUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    sender = update_sender(db, sender_id, data)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    return sender


@router.delete("/{sender_id}", status_code=204)
def delete_one_sender(sender_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not delete_sender(db, sender_id):
        raise HTTPException(status_code=404, detail="Sender not found")


@router.post("/{sender_id}/verify", response_model=SenderOut)
def verify_sender(sender_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    sender = mark_sender_verified(db, sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    return sender
