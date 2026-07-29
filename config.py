"""Application configuration loaded from the local .env file."""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Gemini is the only model provider used by this application.
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MODEL: str = os.getenv("GOOGLE_MODEL", "gemini-3.1-flash-lite")

    # Optional free Adzuna tier.  With no credentials the app uses Playwright.
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
    ADZUNA_COUNTRY: str = os.getenv("ADZUNA_COUNTRY", "eg")

    # Optional LangSmith tracing.
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "job-matcher")

    DEFAULT_LOCATION: str = os.getenv("DEFAULT_LOCATION", "Cairo")
    RESULTS_PER_QUERY: int = int(os.getenv("RESULTS_PER_QUERY", "10"))
    TOP_N_JOBS: int = int(os.getenv("TOP_N_JOBS", "10"))
    MEMORY_DB_PATH: str = os.getenv("MEMORY_DB_PATH", "./memory/job_matcher_memory.sqlite")

    @property
    def has_adzuna(self) -> bool:
        return bool(self.ADZUNA_APP_ID and self.ADZUNA_APP_KEY)


settings = Settings()

if settings.LANGCHAIN_TRACING_V2.lower() == "true" and settings.LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
