import secrets
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://app:app@localhost:5432/invoices"
    STORAGE_PATH: str = "./storage"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    class Config:
        env_file = ".env"


def generate_secret_key() -> str:
    return secrets.token_urlsafe(32)


settings = Settings()