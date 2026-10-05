"""Shared FastAPI dependencies: DB session, current user, current account.

Every authenticated router should depend on ``get_current_user`` (or
``get_current_account_id`` when only the account scope is needed) rather than decoding the
token itself, so account isolation stays in one place.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.security import decode_access_token
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)

__all__ = ["get_db", "get_current_user", "get_current_account_id"]


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.disabled_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


def get_current_account_id(user: User = Depends(get_current_user)) -> uuid.UUID:
    return user.account_id
