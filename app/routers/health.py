from fastapi import APIRouter, HTTPException
from postgrest.exceptions import APIError
from app.core.database import supabase
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/")
def home():
    """Root health and welcome endpoint."""
    return {
        "message": "Personal Expense Tracker API is running",
        "status": "healthy",
    }


@router.get("/health/db")
def database_health():
    """Verify Supabase database connectivity."""
    try:
        supabase.table("expenses").select("id").limit(1).execute()
        logger.info("Database health check passed")
        return {"database": "connected", "status": "healthy"}
    except APIError as api_err:
        logger.error("Supabase API error during health check: %s", api_err.message)
        raise HTTPException(
            status_code=503,
            detail=f"Database health check failed: {api_err.message}",
        )
    except Exception as exc:
        logger.exception("Unexpected error connecting to database: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not connect to the database. Check server logs and credentials.",
        )
