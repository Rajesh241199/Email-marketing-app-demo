from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.deps import get_current_active_user
from crud.crud_account import get_account, create_account, update_account
from schemas.account import AccountCreate, AccountUpdate, AccountOut

router = APIRouter()


@router.post("/", response_model=AccountOut, status_code=201)
def create_new_account(
    data: AccountCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    return create_account(db, data)


@router.get("/{account_id}", response_model=AccountOut)
def read_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    account = get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.put("/{account_id}", response_model=AccountOut)
def update_account_profile(
    account_id: int,
    data: AccountUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    account = update_account(db, account_id, data)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
