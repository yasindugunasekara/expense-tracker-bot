from datetime import date, datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from postgrest.exceptions import APIError

from app.core.database import supabase
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Summary"])


@router.get("/summary")
def expense_summary(
    start_date: date,
    end_date: date,
    event_id: int | None = None,
):
    """Retrieve summarized expense metrics between start_date and end_date."""
    if end_date <= start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be after start_date",
        )

    logger.info(
        "Generating expense summary: start_date=%s, end_date=%s, event_id=%s",
        start_date,
        end_date,
        event_id,
    )

    try:
        result = supabase.rpc(
            "get_expense_summary",
            {
                "p_start_date": start_date.isoformat(),
                "p_end_date": end_date.isoformat(),
                "p_event_id": event_id,
            },
        ).execute()
    except APIError as api_err:
        logger.error("Supabase APIError while calculating summary: %s", api_err.message)
        raise HTTPException(
            status_code=400,
            detail=f"Database error while generating summary: {api_err.message}",
        )
    except Exception as exc:
        logger.exception("Unexpected error while calculating summary: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve expense summary. Check server logs.",
        )

    summary_data = result.data[0] if (result.data and len(result.data) > 0) else {}

    return {
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date.isoformat(),
        "event_id": event_id,
        "currency": "LKR",
        "summary": summary_data,
    }
