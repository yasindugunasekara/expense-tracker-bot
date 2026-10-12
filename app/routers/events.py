from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from postgrest.exceptions import APIError

from app.core.database import supabase
from app.core.logging import get_logger
from app.schemas.event import EventCreate

logger = get_logger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])


def handle_database_error(exc: Exception, action_description: str) -> HTTPException:
    """Format database errors with clear logging and status codes."""
    if isinstance(exc, APIError):
        code = getattr(exc, "code", None)
        message = getattr(exc, "message", str(exc))
        logger.error(
            "Supabase APIError while %s: code=%s, message=%s",
            action_description,
            code,
            message,
        )
        if code == "42501":
            return HTTPException(
                status_code=403,
                detail="Permission denied: Row-Level Security (RLS) policy violated for table 'expense_events'. Ensure an INSERT policy exists or configure the service_role key.",
            )
        return HTTPException(
            status_code=400,
            detail=f"Database error while {action_description}: {message}",
        )
    logger.exception("Unexpected error while %s: %s", action_description, exc)
    return HTTPException(
        status_code=500,
        detail=f"Internal server error while {action_description}.",
    )


# -------------------------------
# Start an event or trip
# -------------------------------
@router.post("", status_code=201)
def start_event(event: EventCreate):
    logger.info("Attempting to start event: '%s' (type: %s)", event.name, event.event_type)

    try:
        active = (
            supabase.table("expense_events")
            .select("id, name")
            .eq("status", "active")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, "checking active events")

    if active.data:
        active_name = active.data[0]["name"]
        logger.warning(
            "Cannot start event '%s': event '%s' is already active",
            event.name,
            active_name,
        )
        raise HTTPException(
            status_code=409,
            detail=f"Event '{active_name}' is already active. Finish it first.",
        )

    data = event.model_dump(mode="json", exclude_none=True)

    try:
        result = supabase.table("expense_events").insert(data).execute()
        created_event = result.data[0]
        logger.info(
            "Successfully started event ID %s: '%s'",
            created_event.get("id"),
            event.name,
        )
        return {"message": "Event started", "event": created_event}
    except Exception as exc:
        raise handle_database_error(exc, "starting event")


# -------------------------------
# Get the active event
# -------------------------------
@router.get("/active")
def get_active_event():
    logger.debug("Fetching current active event")
    try:
        result = (
            supabase.table("expense_events")
            .select("*")
            .eq("status", "active")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, "fetching active event")

    if not result.data:
        return {"active_event": None}

    return {"active_event": result.data[0]}


# -------------------------------
# Finish an event
# -------------------------------
@router.post("/{event_id}/end")
def end_event(event_id: int):
    logger.info("Ending event ID %d", event_id)

    try:
        existing = (
            supabase.table("expense_events")
            .select("*")
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, f"verifying event ID {event_id}")

    if not existing.data:
        logger.warning("Event ID %d not found", event_id)
        raise HTTPException(status_code=404, detail="Event not found")

    event = existing.data[0]

    if event["status"] != "active":
        logger.warning("Event ID %d is not active (status: %s)", event_id, event["status"])
        raise HTTPException(
            status_code=409,
            detail="This event is not active",
        )

    ended_at = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            supabase.table("expense_events")
            .update({
                "status": "completed",
                "ended_at": ended_at,
            })
            .eq("id", event_id)
            .eq("status", "active")
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, f"completing event ID {event_id}")

    if not result.data:
        logger.warning("Event ID %d status changed concurrently", event_id)
        raise HTTPException(
            status_code=409,
            detail="The event status changed. Refresh and try again.",
        )

    logger.info("Successfully ended event ID %d: '%s'", event_id, event.get("name"))
    return {"message": "Event completed", "event": result.data[0]}


# -------------------------------
# List events
# -------------------------------
@router.get("")
def list_events():
    logger.debug("Listing past events")
    try:
        result = (
            supabase.table("expense_events")
            .select("*")
            .order("started_at", desc=True)
            .limit(100)
            .execute()
        )
        return {"events": result.data}
    except Exception as exc:
        raise handle_database_error(exc, "listing events")
