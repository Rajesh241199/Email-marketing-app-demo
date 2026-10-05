import hashlib
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Union

from jose import jwt
from core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_hash = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return bcrypt.checkpw(
        password_hash.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_hash.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
