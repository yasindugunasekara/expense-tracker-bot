from datetime import date, datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from postgrest.exceptions import APIError

from app.expense_totals import read_expenses, total_amount
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Summary"])


@router.get("/summary")
def expense_summary(
    start_date: date,
    end_date: date,
    event_id: int | None = None,
):
    """Sum expenses by expense_date; start inclusive, end exclusive (Colombo calendar dates)."""
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
        rows = read_expenses(start_date, end_date, event_id=event_id)
        summary_data = {"total_spent": total_amount(rows), "expense_count": len(rows)}
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


    return {
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date.isoformat(),
        "event_id": event_id,
        "currency": "LKR",
        "summary": summary_data,
    }
