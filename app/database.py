from collections.abc import Generator

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Settings(BaseSettings):
    database_url: str
    auth_secret_key: str = "change-me-in-env-with-at-least-32-characters"
    auth_access_token_expire_minutes: int = 60 * 24
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    bedrock_model_id: str = "mistral.ministral-3-14b-instruct"
    bedrock_region: str = "us-east-1"
    # Storage
    use_s3: bool = False
    upload_dir: str = "uploads/complaints"
    local_base_url: str = "http://localhost:8000"
    # AWS
    aws_bucket: str = ""
    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    # Admin OTP lifecycle
    admin_unverified_ttl_hours: int = 6
    admin_cleanup_interval_minutes: int = 30
    # Comma-separated emails allowed to access super admin endpoints.
    super_admin_emails: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_database_configured() -> bool:
    return bool(settings.database_url)