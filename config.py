"""Application configuration loaded from the local .env file."""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Runtime model settings can be changed from the UI. These values are the
    # safe startup defaults; API keys are never written to the settings file.
    MODEL_PROVIDER: str = os.getenv("MODEL_PROVIDER", "ollama_local")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_CLOUD_URL: str = os.getenv("OLLAMA_CLOUD_URL", "https://ollama.com")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "")
    OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "")

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
    DOCUMENT_TTL_HOURS: int = int(os.getenv("DOCUMENT_TTL_HOURS", "24"))
    APPLICATION_SESSION_TTL_MINUTES: int = int(os.getenv("APPLICATION_SESSION_TTL_MINUTES", "20"))

    @property
    def has_adzuna(self) -> bool:
        placeholders = {"your_app_id", "your_app_key", "changeme", "replace_me"}
        return bool(
            self.ADZUNA_APP_ID
            and self.ADZUNA_APP_KEY
            and self.ADZUNA_APP_ID.casefold() not in placeholders
            and self.ADZUNA_APP_KEY.casefold() not in placeholders
        )


settings = Settings()

if (
    settings.LANGCHAIN_TRACING_V2.lower() == "true"
    and len(settings.LANGCHAIN_API_KEY.strip()) >= 20
):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
else:
    # A placeholder/invalid tracing key should never create noisy background
    # failures during otherwise successful local runs.
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
