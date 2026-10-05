from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_tag
from schemas.subscriber import TagCreate, TagOut

router = APIRouter()


@router.post("/", response_model=TagOut, status_code=201)
def create_tag(account_id: int, data: TagCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if crud_tag.get_tag_by_name(db, account_id, data.name):
        raise HTTPException(status_code=409, detail="Tag with this name already exists")
    return crud_tag.create_tag(db, account_id, data)


@router.get("/", response_model=List[TagOut])
def list_tags(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_tag.get_tags_by_account(db, account_id)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_tag.delete_tag(db, tag_id):
        raise HTTPException(status_code=404, detail="Tag not found")


@router.post("/subscribers/{subscriber_id}/tags/{tag_id}", status_code=201)
def apply_tag(subscriber_id: int, tag_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    applied = crud_tag.apply_tag_to_subscriber(db, tag_id, subscriber_id)
    if not applied:
        raise HTTPException(status_code=409, detail="Tag already applied")
    return {"message": "Tag applied"}


@router.delete("/subscribers/{subscriber_id}/tags/{tag_id}", status_code=204)
def remove_tag(subscriber_id: int, tag_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_tag.remove_tag_from_subscriber(db, tag_id, subscriber_id):
        raise HTTPException(status_code=404, detail="Tag association not found")
