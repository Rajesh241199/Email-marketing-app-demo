from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import get_current_active_user
from crud import crud_list
from schemas.subscriber import ListCreate, ListUpdate, ListOut, SubscriberOut, SubscriberListPage

router = APIRouter()


@router.post("/", response_model=ListOut, status_code=201)
def create_list(account_id: int, data: ListCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_list.create_list(db, account_id, data)


@router.get("/", response_model=List[ListOut])
def list_all(account_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return crud_list.get_lists_by_account(db, account_id)


@router.get("/{list_id}", response_model=ListOut)
def get_list(list_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    lst = crud_list.get_list(db, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    return lst


@router.put("/{list_id}", response_model=ListOut)
def update_list(list_id: int, data: ListUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    lst = crud_list.update_list(db, list_id, data)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    return lst


@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_list.delete_list(db, list_id):
        raise HTTPException(status_code=404, detail="List not found")


@router.get("/{list_id}/subscribers", response_model=SubscriberListPage)
def get_list_subscribers(
    list_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    lst = crud_list.get_list(db, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    total, items = crud_list.get_list_subscribers(db, list_id, page=page, per_page=per_page)
    return SubscriberListPage(total=total, page=page, per_page=per_page, items=items)


@router.post("/{list_id}/subscribers/{subscriber_id}", status_code=201)
def add_subscriber_to_list(list_id: int, subscriber_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    added = crud_list.add_subscriber_to_list(db, list_id, subscriber_id)
    if not added:
        raise HTTPException(status_code=409, detail="Subscriber already in list")
    return {"message": "Subscriber added to list"}


@router.delete("/{list_id}/subscribers/{subscriber_id}", status_code=204)
def remove_subscriber_from_list(list_id: int, subscriber_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    if not crud_list.remove_subscriber_from_list(db, list_id, subscriber_id):
        raise HTTPException(status_code=404, detail="Membership not found")
