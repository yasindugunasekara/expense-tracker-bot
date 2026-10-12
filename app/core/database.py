from supabase import create_client, Client
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    """Initialize or return existing Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        logger.info("Initializing Supabase client: %s", settings.SUPABASE_URL)
        _supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _supabase_client


# Module-level client instance for convenience
supabase: Client = get_supabase_client()
