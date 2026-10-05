"""Application settings, loaded from the environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/email_marketing"
    test_database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/email_marketing_test"
    )

    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    upload_dir: str = "var/uploads"


settings = Settings()
