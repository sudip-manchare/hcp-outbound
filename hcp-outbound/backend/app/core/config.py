from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Tiger Data / PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://localhost/hcp_outbound"
    DATABASE_URL_SYNC: str = "postgresql://localhost/hcp_outbound"

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
