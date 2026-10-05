"""Users, external identities, sessions and single-use tokens. ONB-01, ONB-02, ONB-06.

Authentication is provider-agnostic so the V1 decision can go either way:

* Local email + password  -> ``users.password_hash`` is set, no ``user_identities`` row.
* Auth0 / Cognito / OIDC  -> ``users.password_hash`` is NULL and one ``user_identities``
  row holds the provider's issuer + subject (the ``sub`` claim).
* Both (password now, "Sign in with Google" later) -> both are present.

``user_sessions`` backs server-side refresh tokens so sign-out and "sign out everywhere"
can revoke access. If the team chooses a hosted IdP that owns sessions, this table and
``auth_tokens`` can be dropped.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

if TYPE_CHECKING:
    from app.accounts.models import Account


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class TokenPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


class AuthProvider(str, enum.Enum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    AUTH0 = "auth0"
    COGNITO = "cognito"
    OIDC = "oidc"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_account_id", "account_id"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True, comment="Login email, globally unique")
    password_hash: Mapped[str | None] = mapped_column(
        String(255), comment="argon2id; NULL for users who only sign in through an external IdP"
    )
    full_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), server_default=UserRole.OWNER.value
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="users")
    identities: Mapped[list[UserIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    auth_tokens: Mapped[list[AuthToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserIdentity(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Link between a user and an external identity provider (OIDC issuer + subject)."""

    __tablename__ = "user_identities"
    __table_args__ = (
        Index("uq_user_identities_issuer_subject", "issuer", "external_subject", unique=True),
        Index("ix_user_identities_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    provider: Mapped[AuthProvider] = mapped_column(pg_enum(AuthProvider, "auth_provider"))
    issuer: Mapped[str] = mapped_column(String(255), comment="OIDC iss claim")
    external_subject: Mapped[str] = mapped_column(String(255), comment="OIDC sub claim")
    email_at_provider: Mapped[str | None] = mapped_column(CITEXT)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="identities")


class UserSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Server-side session / refresh token. Revoking it signs the user out (ONB-01)."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        Index(
            "ix_user_sessions_user_id_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Single-use email verification / password reset token. Only a hash is stored."""

    __tablename__ = "auth_tokens"
    __table_args__ = (Index("ix_auth_tokens_user_id_purpose", "user_id", "purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    purpose: Mapped[TokenPurpose] = mapped_column(pg_enum(TokenPurpose, "token_purpose"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="auth_tokens")
