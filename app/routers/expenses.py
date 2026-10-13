from datetime import date, datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from postgrest.exceptions import APIError

from app.core.database import supabase
from app.core.logging import get_logger
from app.schemas.expense import ExpenseCreate, ExpenseUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/expenses", tags=["Expenses"])


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
                detail="Permission denied: Row-Level Security (RLS) policy violated. Check Supabase RLS policies or use service_role key.",
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
# Create an expense
# -------------------------------
@router.post("", status_code=201)
def create_expense(expense: ExpenseCreate):
    data = expense.model_dump(mode="json", exclude_none=True)
    active_event_name = None

    # If no event ID is supplied, attach to the active event if one exists
    if expense.event_id is None:
        try:
            active = (
                supabase.table("expense_events")
                .select("id, name")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if active.data:
                data["event_id"] = active.data[0]["id"]
                active_event_name = active.data[0]["name"]
                logger.info(
                    "Attaching expense '%s' to active event '%s' (ID %s)",
                    expense.title,
                    active_event_name,
                    data["event_id"],
                )
        except Exception as exc:
            logger.warning("Could not check for active event: %s", exc)
    else:
        try:
            ev = (
                supabase.table("expense_events")
                .select("name")
                .eq("id", expense.event_id)
                .limit(1)
                .execute()
            )
            if ev.data:
                active_event_name = ev.data[0]["name"]
        except Exception:
            pass

    try:
        result = supabase.table("expenses").insert(data).execute()
        created_expense = dict(result.data[0])
        if active_event_name:
            created_expense["event_name"] = active_event_name
        logger.info(
            "Created expense ID %s: '%s' (Amount: %s, Category: %s)",
            created_expense.get("id"),
            expense.title,
            expense.amount,
            expense.category,
        )
        return {"message": "Expense created", "expense": created_expense}
    except Exception as exc:
        raise handle_database_error(exc, "creating expense")



# -------------------------------
# List expenses with filters
# -------------------------------
@router.get("")
def list_expenses(
    category: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    event_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    logger.debug(
        "Listing expenses: category=%s, date_from=%s, date_to=%s, event_id=%s, limit=%s, offset=%s",
        category,
        date_from,
        date_to,
        event_id,
        limit,
        offset,
    )

    query = (
        supabase.table("expenses")
        .select("*")
        .order("expense_date", desc=True)
        .order("id", desc=True)
    )

    if category:
        query = query.eq("category", category)

    if date_from:
        query = query.gte("expense_date", date_from.isoformat())

    if date_to:
        query = query.lte("expense_date", date_to.isoformat())

    if event_id is not None:
        query = query.eq("event_id", event_id)

    try:
        result = query.range(offset, offset + limit - 1).execute()
        return {
            "count_returned": len(result.data),
            "limit": limit,
            "offset": offset,
            "expenses": result.data,
        }
    except Exception as exc:
        raise handle_database_error(exc, "retrieving expenses")


# -------------------------------
# Get one expense
# -------------------------------
@router.get("/{expense_id}")
def get_expense(expense_id: int):
    try:
        result = (
            supabase.table("expenses")
            .select("*")
            .eq("id", expense_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, f"fetching expense ID {expense_id}")

    if not result.data:
        logger.warning("Expense ID %d not found", expense_id)
        raise HTTPException(status_code=404, detail="Expense not found")

    return result.data[0]


# -------------------------------
# Update an expense
# -------------------------------
@router.put("/{expense_id}")
def update_expense(expense_id: int, expense: ExpenseUpdate):
    changes = expense.model_dump(mode="json", exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update",
        )

    changes["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            supabase.table("expenses")
            .update(changes)
            .eq("id", expense_id)
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, f"updating expense ID {expense_id}")

    if not result.data:
        logger.warning("Update failed: Expense ID %d not found", expense_id)
        raise HTTPException(status_code=404, detail="Expense not found")

    logger.info("Updated expense ID %d: fields changed=%s", expense_id, list(changes.keys()))
    return {"message": "Expense updated", "expense": result.data[0]}


# -------------------------------
# Delete an expense
# -------------------------------
@router.delete("/{expense_id}")
def delete_expense(expense_id: int):
    try:
        existing = (
            supabase.table("expenses")
            .select("id")
            .eq("id", expense_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise handle_database_error(exc, f"checking expense ID {expense_id}")

    if not existing.data:
        logger.warning("Delete failed: Expense ID %d not found", expense_id)
        raise HTTPException(status_code=404, detail="Expense not found")

    try:
        supabase.table("expenses").delete().eq("id", expense_id).execute()
        logger.info("Deleted expense ID %d", expense_id)
        return {"message": "Expense deleted", "id": expense_id}
    except Exception as exc:
        raise handle_database_error(exc, f"deleting expense ID {expense_id}")
