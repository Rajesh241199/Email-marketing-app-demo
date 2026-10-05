from typing import Optional, Sequence
from sqlalchemy.orm import Session

from models.account import Account, User, UserAuth, UserStatus
from schemas.account import AccountCreate, AccountUpdate, UserCreate, UserRegister, UserUpdate
from core.security import get_password_hash


# ── Account ───────────────────────────────────────────────────────────────────

def get_account(db: Session, account_id: int) -> Optional[Account]:
    return db.query(Account).filter(Account.id == account_id).first()


def create_account(db: Session, data: AccountCreate) -> Account:
    account = Account(**data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(db: Session, account_id: int, data: AccountUpdate) -> Optional[Account]:
    account = get_account(db, account_id)
    if not account:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return account


# ── User ──────────────────────────────────────────────────────────────────────

def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def register_user(db: Session, data: UserRegister) -> User:
    user = User(email=data.email, first_name=data.first_name, last_name=data.last_name)
    db.add(user)
    db.flush()
    auth = UserAuth(user_id=user.id, password_hash=get_password_hash(data.password))
    db.add(auth)
    db.commit()
    db.refresh(user)
    return user


def set_user_active(db: Session, user_id: int) -> Optional[User]:
    user = get_user(db, user_id)
    if not user:
        return None
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, data: UserUpdate) -> Optional[User]:
    user = get_user(db, user_id)
    if not user:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user
