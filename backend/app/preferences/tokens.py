"""Long-lived, non-expiring tokens for the public preference-center links.

These are a different *kind* of token than the session access token in
``app.core.security``: they never expire (a preference-center link in an old email must
keep working), carry only the subscriber id, and are tagged ``"type": "preference"`` so a
leaked/forged access token (or vice versa) can never be mistaken for one, even though both
are signed with the same ``settings.jwt_secret``.
"""

from __future__ import annotations

import uuid
from typing import Any

import jwt

from app.core.config import settings

_TOKEN_TYPE = "preference"


def create_preference_token(subscriber_id: uuid.UUID) -> str:
    payload: dict[str, Any] = {"sub": str(subscriber_id), "type": _TOKEN_TYPE}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_preference_token(token: str) -> uuid.UUID:
    """Raises ``jwt.PyJWTError`` (including our own ``InvalidTokenError``) if invalid."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != _TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not a preference-center token")
    return uuid.UUID(payload["sub"])
