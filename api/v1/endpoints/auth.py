from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import verify_password, create_access_token
from core.config import settings
from crud.crud_account import get_user_by_email, register_user, set_user_active
from schemas.account import UserRegister, UserOut
from schemas.token import Token

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserRegister, db: Session = Depends(get_db)):
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = register_user(db, data)
    return user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = get_user_by_email(db, form_data.username)
    if not user or not user.auth or not verify_password(form_data.password, user.auth.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/verify-email/{user_id}", response_model=UserOut)
def verify_email(user_id: int, db: Session = Depends(get_db)):
    user = set_user_active(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/forgot-password")
def forgot_password(email: str, db: Session = Depends(get_db)):
    # Scaffold — implement email sending in Rajesh's sprint
    return {"message": "If that email exists, a reset link will be sent"}
