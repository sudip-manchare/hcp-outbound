from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Tiger Data / PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://localhost/hcp_outbound"
    DATABASE_URL_SYNC: str = "postgresql://localhost/hcp_outbound"

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    SECRET_KEY: str = "change-me-in-production"
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


@lru_cache()
def get_settings() -> Settings:
    return Settings()
