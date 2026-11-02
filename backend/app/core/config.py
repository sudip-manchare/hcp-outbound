from __future__ import annotations

import sys
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tiger Data / PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://localhost/hcp_outbound"
    DATABASE_URL_SYNC: str = "postgresql://localhost/hcp_outbound"

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    SECRET_KEY: str = "change-me-in-production"

    # FIX: Added API_KEYS for admin route authentication. Set a comma-separated
    # list of accepted keys via the API_KEYS environment variable in production.
    # pydantic-settings automatically parses a JSON array from the env string.
    API_KEYS: list[str] = []

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_SECONDS: float = 30.0

    # Official public-source APIs.  These are deliberately configured as
    # endpoints rather than optional integrations: the live profile route
    # always queries both sources and never substitutes seed fixtures.
    NPPES_API_BASE_URL: str = "https://npiregistry.cms.hhs.gov/api/"
    NPPES_API_VERSION: str = "2.1"
    CMS_OPEN_PAYMENTS_API_BASE_URL: str = "https://openpaymentsdata.cms.gov/api/1"
    # Required in .env; CMS publishes a distinct dataset for each reporting year.
    CMS_OPEN_PAYMENTS_GENERAL_DATASET_ID: str
    CMS_OPEN_PAYMENTS_PROGRAM_YEAR: int = 2025
    EXTERNAL_API_TIMEOUT_SECONDS: float = 30.0
    CMS_OPEN_PAYMENTS_MAX_PAGE_SIZE: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        # FIX: Prevent the server from starting in production with the placeholder
        # SECRET_KEY. A default key makes HMAC-signed tokens trivially forgeable.
        # Fail loudly at boot rather than silently at runtime.
        if self.APP_ENV == "production" and self.SECRET_KEY == "change-me-in-production":
            print(
                "FATAL: SECRET_KEY must be set to a strong random value before "
                "running in production. Set the SECRET_KEY environment variable.",
                file=sys.stderr,
            )
            sys.exit(1)
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
