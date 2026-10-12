import os
from functools import lru_cache
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()


class Settings:
    """Application settings and configuration."""

    APP_NAME: str = "Personal Expense Tracker API"
    APP_DESCRIPTION: str = "Manage expenses and special events with structured logging and Supabase integration"
    APP_VERSION: str = "1.0.0"

    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def validate(self) -> None:
        """Validate required configuration values."""
        if not self.SUPABASE_URL or not self.SUPABASE_KEY:
            raise RuntimeError(
                "Missing SUPABASE_URL or SUPABASE_KEY in environment or .env file."
            )


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
