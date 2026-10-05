"""Registration, login, session refresh/revocation, email verification, password reset.

Email delivery for verification / reset links isn't wired up yet (no provider in this
bootstrap pass) - tokens are created and stored hashed as designed, but the raw value is
only returned here for /verify-email's request-step sibling in dev. See
docs/api/testing.md for how to fetch a token directly from the database for manual testing.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.auth.models import AuthToken, TokenPurpose, User, UserRole, UserSession
from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserRead,
    VerifyEmailRequest,
)
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    generate_single_use_token,
    hash_password,
    hash_refresh_token,
    hash_single_use_token,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        ipaddress.ip_address(host) if host else None
    except ValueError:
        return None
    return host


def _issue_tokens(db: Session, user: User, request: Request) -> TokenResponse:
    access_token = create_access_token(user_id=user.id, account_id=user.account_id)
    refresh_token = generate_refresh_token()
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    db.flush()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest, request: Request, db: Session = Depends(get_db)
) -> RegisterResponse:
    if db.query(User).filter(User.email == body.user.email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    account = Account(**body.account.model_dump())
    db.add(account)
    db.flush()

    user = User(
        account_id=account.id,
        email=body.user.email,
        password_hash=hash_password(body.user.password),
        full_name=body.user.full_name,
        role=UserRole.OWNER,
    )
    db.add(user)
    db.flush()

    verify_token = generate_single_use_token()
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_single_use_token(verify_token),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )

    tokens = _issue_tokens(db, user, request)
    db.commit()
    return RegisterResponse(**tokens.model_dump(), user=UserRead.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if (
        user is None
        or user.password_hash is None
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.disabled_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    user.last_login_at = datetime.now(UTC)
    tokens = _issue_tokens(db, user, request)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token_hash = hash_refresh_token(body.refresh_token)
    session = db.query(UserSession).filter(UserSession.refresh_token_hash == token_hash).first()
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or session.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    user = db.get(User, session.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")

    session.last_used_at = now
    access_token = create_access_token(user_id=user.id, account_id=user.account_id)
    db.commit()
    return TokenResponse(access_token=access_token, refresh_token=body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutRequest, db: Session = Depends(get_db)) -> None:
    token_hash = hash_refresh_token(body.refresh_token)
    session = db.query(UserSession).filter(UserSession.refresh_token_hash == token_hash).first()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    now = datetime.now(UTC)
    db.query(UserSession).filter(
        UserSession.user_id == current_user.id, UserSession.revoked_at.is_(None)
    ).update({"revoked_at": now})
    db.commit()


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)) -> None:
    token_hash = hash_single_use_token(body.token)
    auth_token = (
        db.query(AuthToken)
        .filter(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == TokenPurpose.EMAIL_VERIFICATION,
        )
        .first()
    )
    now = datetime.now(UTC)
    if auth_token is None or auth_token.used_at is not None or auth_token.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")

    user = db.get(User, auth_token.user_id)
    assert user is not None
    user.email_verified_at = now
    auth_token.used_at = now
    db.commit()


@router.post("/password-reset/request", status_code=status.HTTP_204_NO_CONTENT)
def request_password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)) -> None:
    user = db.query(User).filter(User.email == body.email).first()
    if user is not None:
        db.add(
            AuthToken(
                user_id=user.id,
                purpose=TokenPurpose.PASSWORD_RESET,
                token_hash=hash_single_use_token(generate_single_use_token()),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()
    # Always 204, whether or not the email exists, to avoid leaking which emails are registered.


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)) -> None:
    token_hash = hash_single_use_token(body.token)
    auth_token = (
        db.query(AuthToken)
        .filter(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == TokenPurpose.PASSWORD_RESET,
        )
        .first()
    )
    now = datetime.now(UTC)
    if auth_token is None or auth_token.used_at is not None or auth_token.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")

    user = db.get(User, auth_token.user_id)
    assert user is not None
    user.password_hash = hash_password(body.new_password)
    auth_token.used_at = now
    db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
    ).update({"revoked_at": now})
    db.commit()
