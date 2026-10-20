
import json
import os
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Ensure project root is in sys.path so "app" module is always resolvable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from mcp.server.fastmcp import FastMCP

from app.core.database import supabase

mcp = FastMCP("expense-tracker")

API_BASE_URL = (
    os.getenv("EXPENSE_API_URL")
    or os.getenv("API_BASE_URL")
    or "http://127.0.0.1:8000"
).rstrip("/")

REQUEST_TIMEOUT = 15.0


def json_result(data) -> str:
    """Return compact JSON to reduce unnecessary token usage."""
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def validate_date(value: str, field_name: str) -> str | None:
    """Validate an optional ISO date."""
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


async def api_get(path: str, params: dict | None = None):
    """Call the existing FastAPI backend."""
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT
    ) as client:
        response = await client.get(
            f"{API_BASE_URL}{path}",
            params=params,
        )
        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            return response.text


def handle_api_error(exc: Exception) -> str:
    """Return a concise error without exposing credentials."""
    if isinstance(exc, httpx.HTTPStatusError):
        return json_result({
            "error": "Expense API request failed.",
            "status_code": exc.response.status_code,
        })

    if isinstance(exc, httpx.RequestError):
        return json_result({
            "error": (
                "Cannot connect to the expense API. "
                "Check that FastAPI is running."
            )
        })

    return json_result({
        "error": "Unexpected error while retrieving expenses."
    })


@mcp.tool()
async def get_expense_summary(
    start_date: str,
    end_date: str,
    event_id: int | None = None,
) -> str:
    """
    Get summarized expense metrics between two dates.
    Optionally filter by an event ID.
    Dates must use YYYY-MM-DD format.
    """
    start = validate_date(start_date, "start_date")
    end = validate_date(end_date, "end_date")

    if start is None or end is None:
        return json_result({
            "error": "Dates must use YYYY-MM-DD format."
        })

    if start > end:
        return json_result({
            "error": "start_date must not be after end_date."
        })

    params = {
        "start_date": start,
        "end_date": end,
    }

    if event_id is not None:
        params["event_id"] = event_id

    try:
        result = await api_get("/summary", params)
        return json_result(result)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return handle_api_error(exc)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool()
async def search_expenses(
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    event_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """
    Search individual expense records.

    Use date_from and date_to to filter dates in YYYY-MM-DD format.
    Use category to filter expenses, such as Transport or Food.
    Use event_id to filter a specific trip or event.
    Limit defaults to 20 and cannot exceed 100.
    Use offset to retrieve the next page of results.
    """
    if date_from is not None:
        date_from = validate_date(date_from, "date_from")
        if date_from is None:
            return json_result({
                "error": "date_from must use YYYY-MM-DD format."
            })

    if date_to is not None:
        date_to = validate_date(date_to, "date_to")
        if date_to is None:
            return json_result({
                "error": "date_to must use YYYY-MM-DD format."
            })

    if date_from and date_to and date_from > date_to:
        return json_result({
            "error": "date_from must not be after date_to."
        })

    if not 1 <= limit <= 100:
        return json_result({
            "error": "limit must be between 1 and 100."
        })

    if offset < 0:
        return json_result({
            "error": "offset cannot be negative."
        })

    params = {
        "limit": limit,
        "offset": offset,
    }

    if category and category.strip():
        params["category"] = category.strip()

    if date_from:
        params["date_from"] = date_from

    if date_to:
        params["date_to"] = date_to

    if event_id is not None:
        params["event_id"] = event_id

    try:
        result = await api_get("/expenses", params)
        return json_result(result)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return handle_api_error(exc)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool()
async def get_expense_details(expense_id: int) -> str:
    """
    Retrieve one expense by its numeric expense ID.
    Use this when the user asks for the details of a specific expense.
    """
    if expense_id <= 0:
        return json_result({
            "error": "expense_id must be a positive integer."
        })

    try:
        result = await api_get(f"/expenses/{expense_id}")
        return json_result(result)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return handle_api_error(exc)
    except Exception as exc:
        return handle_api_error(exc)


# ---------------------------------------------------------
# MCP tools: summaries and scheduled task management
# ---------------------------------------------------------
TIMEZONE = ZoneInfo("Asia/Colombo")

TASK_COLUMNS = (
    "id,task_name,task_type,schedule_time,day_of_week,"
    "day_of_month,category,threshold_amount,threshold_period,"
    "is_active,last_run_at,last_status,last_error,"
    "next_run_at,created_at,updated_at"
)

SUPPORTED_TASK_TYPES = {
    "daily_summary",
    "weekly_summary",
    "monthly_summary",
}


def local_today() -> date:
    """Return today's date in Sri Lanka."""
    return datetime.now(TIMEZONE).date()


def parse_schedule_time(value: str) -> str | None:
    """Validate a 24-hour time such as 20:00."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return None


def task_error(message: str) -> str:
    return json_result({"success": False, "error": message})


@mcp.tool()
async def get_daily_summary() -> str:
    """Get yesterday's expense summary in Sri Lanka time."""
    today = local_today()
    yesterday = today - timedelta(days=1)
    try:
        # end_date is exclusive: includes yesterday, excludes today.
        result = await api_get(
            "/summary",
            {
                "start_date": yesterday.isoformat(),
                "end_date": today.isoformat(),
            },
        )
        return json_result(result)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return handle_api_error(exc)
    except Exception as exc:
        return handle_api_error(exc)


@mcp.tool()
async def list_scheduled_tasks() -> str:
    """
    List all scheduled automation tasks (daily, weekly, and monthly summaries, plus category threshold alerts).
    """
    try:
        response = (
            supabase.table("automation_tasks")
            .select(TASK_COLUMNS)
            .order("id")
            .execute()
        )
        return json_result({
            "success": True,
            "tasks": response.data or [],
        })
    except Exception as exc:
        return task_error(f"Could not load scheduled tasks: {exc}")


@mcp.tool()
async def create_threshold_alert(
    task_name: str,
    category: str,
    threshold_amount: float,
    period: str = "daily",
    schedule_time: str | None = None,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
) -> str:
    """
    Create an automated category spending limit / threshold alert task.
    When spending in 'category' reaches or exceeds 'threshold_amount' in the given
    period ('daily', 'weekly', or 'monthly'), an alert email is sent to the user.

    task_name: Descriptive name, e.g., 'Daily Food Limit Alert' or 'Weekly Transport Cap'
    category: Expense category to monitor, e.g. 'Food', 'Transport', 'Shopping', 'Buy'
    threshold_amount: Spending limit in LKR (e.g. 2000.0 or 15000.0)
    period: 'daily', 'weekly', or 'monthly' (default: 'daily')
    schedule_time: Optional 24-hr time ('20:00') to check at a specific time; omit or pass null for continuous real-time checks.
    day_of_week: For weekly alerts with schedule_time, 0 (Monday) to 6 (Sunday)
    day_of_month: For monthly alerts with schedule_time, 1 to 31
    """
    clean_name = (task_name or "").strip()
    if not clean_name:
        return task_error("task_name cannot be empty.")

    clean_category = (category or "").strip()
    if not clean_category:
        return task_error("category cannot be empty.")

    try:
        limit_val = float(threshold_amount)
        if limit_val <= 0:
            return task_error("threshold_amount must be greater than 0.")
    except (ValueError, TypeError):
        return task_error("threshold_amount must be a valid positive number.")

    clean_period = (period or "daily").strip().lower()
    if clean_period not in ("daily", "weekly", "monthly"):
        return task_error("period must be 'daily', 'weekly', or 'monthly'.")

    period_to_task_type = {
        "daily": "daily_summary",
        "weekly": "weekly_summary",
        "monthly": "monthly_summary",
    }
    task_type = period_to_task_type[clean_period]

    formatted_time = None
    if schedule_time:
        formatted_time = parse_schedule_time(schedule_time)
        if not formatted_time:
            return task_error(
                "schedule_time must be in 24-hour format HH:MM (e.g. '20:00' or '08:30')."
            )

    if clean_period == "weekly" and formatted_time:
        if day_of_week is not None and not (0 <= day_of_week <= 6):
            return task_error("day_of_week must be between 0 (Monday) and 6 (Sunday).")

    if clean_period == "monthly" and formatted_time:
        if day_of_month is not None and not (1 <= day_of_month <= 31):
            return task_error("day_of_month must be between 1 and 31.")

    payload = {
        "task_name": clean_name,
        "task_type": task_type,
        "category": clean_category,
        "threshold_amount": limit_val,
        "threshold_period": clean_period,
        "schedule_time": formatted_time,
        "day_of_week": day_of_week if (clean_period == "weekly" and formatted_time) else None,
        "day_of_month": day_of_month if (clean_period == "monthly" and formatted_time) else None,
        "is_active": True,
    }

    try:
        response = supabase.table("automation_tasks").insert(payload).execute()
        created = response.data[0] if response.data else payload
        return json_result({
            "success": True,
            "message": (
                f"Threshold alert task '{clean_name}' for category '{clean_category}' "
                f"(Limit: LKR {limit_val:,.2f} {clean_period}) created successfully."
            ),
            "task": created,
        })
    except Exception as exc:
        return task_error(f"Failed to create threshold alert task: {exc}")


@mcp.tool()
async def create_scheduled_task(
    task_name: str,
    task_type: str,
    schedule_time: str,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    category: str | None = None,
    threshold_amount: float | None = None,
    threshold_period: str | None = None,
) -> str:
    """
    Create a scheduled summary email task or custom automation task.

    task_name: Descriptive name, e.g., 'Daily Expense Email'
    task_type: Must be 'daily_summary', 'weekly_summary', or 'monthly_summary'
    schedule_time: 24-hour time in Sri Lanka time, e.g., '20:00'
    day_of_week: For weekly_summary, 0 (Monday) to 6 (Sunday)
    day_of_month: For monthly_summary, 1 to 31
    category: Optional category filter or target for spending thresholds
    threshold_amount: Optional spending threshold amount in LKR
    threshold_period: Optional threshold period ('daily', 'weekly', 'monthly')
    """
    clean_name = (task_name or "").strip()
    if not clean_name:
        return task_error("task_name cannot be empty.")

    clean_type = (task_type or "").strip().lower()
    if clean_type not in SUPPORTED_TASK_TYPES:
        return task_error(
            f"Invalid task_type '{task_type}'. Supported: {sorted(SUPPORTED_TASK_TYPES)}"
        )

    formatted_time = parse_schedule_time(schedule_time)
    if not formatted_time:
        return task_error(
            "schedule_time must be in 24-hour format HH:MM (e.g. '20:00' or '08:30')."
        )

    if clean_type == "weekly_summary":
        if day_of_week is None or not (0 <= day_of_week <= 6):
            return task_error(
                "weekly_summary requires day_of_week between 0 (Monday) and 6 (Sunday)."
            )

    if clean_type == "monthly_summary":
        if day_of_month is None or not (1 <= day_of_month <= 31):
            return task_error(
                "monthly_summary requires day_of_month between 1 and 31."
            )

    payload = {
        "task_name": clean_name,
        "task_type": clean_type,
        "schedule_time": formatted_time,
        "day_of_week": day_of_week if clean_type == "weekly_summary" else None,
        "day_of_month": day_of_month if clean_type == "monthly_summary" else None,
        "category": (category or "").strip() or None,
        "threshold_amount": float(threshold_amount) if threshold_amount is not None else None,
        "threshold_period": (threshold_period or "").strip().lower() or None,
        "is_active": True,
    }

    try:
        response = (
            supabase.table("automation_tasks")
            .insert(payload)
            .execute()
        )
        created = response.data[0] if response.data else payload
        return json_result({
            "success": True,
            "message": f"Scheduled task '{clean_name}' created successfully.",
            "task": created,
        })
    except Exception as exc:
        return task_error(f"Failed to create scheduled task: {exc}")



@mcp.tool()
async def get_task_status(task_id: int) -> str:
    """
    Get the status, last execution result, and details of a scheduled task by ID.
    """
    if task_id <= 0:
        return task_error("task_id must be a positive integer.")

    try:
        response = (
            supabase.table("automation_tasks")
            .select(TASK_COLUMNS)
            .eq("id", task_id)
            .execute()
        )
        if not response.data:
            return task_error(f"Task with ID {task_id} not found.")

        return json_result({
            "success": True,
            "task": response.data[0],
        })
    except Exception as exc:
        return task_error(f"Could not retrieve task status: {exc}")


@mcp.tool()
async def pause_task(task_id: int) -> str:
    """
    Pause a scheduled automation task so it stops running.
    """
    if task_id <= 0:
        return task_error("task_id must be a positive integer.")

    now_iso = datetime.now(TIMEZONE).isoformat()
    try:
        response = (
            supabase.table("automation_tasks")
            .update({"is_active": False, "updated_at": now_iso})
            .eq("id", task_id)
            .execute()
        )
        if not response.data:
            return task_error(f"Task with ID {task_id} not found.")

        return json_result({
            "success": True,
            "message": f"Task {task_id} has been paused.",
            "task": response.data[0],
        })
    except Exception as exc:
        return task_error(f"Failed to pause task {task_id}: {exc}")


@mcp.tool()
async def resume_task(task_id: int) -> str:
    """
    Resume a paused scheduled automation task.
    """
    if task_id <= 0:
        return task_error("task_id must be a positive integer.")

    now_iso = datetime.now(TIMEZONE).isoformat()
    try:
        response = (
            supabase.table("automation_tasks")
            .update({"is_active": True, "updated_at": now_iso})
            .eq("id", task_id)
            .execute()
        )
        if not response.data:
            return task_error(f"Task with ID {task_id} not found.")

        return json_result({
            "success": True,
            "message": f"Task {task_id} has been resumed.",
            "task": response.data[0],
        })
    except Exception as exc:
        return task_error(f"Failed to resume task {task_id}: {exc}")


@mcp.tool()
async def delete_task(task_id: int, confirm: bool = False) -> str:
    """
    Delete a scheduled task.
    Requires confirmation before permanent removal. If confirm is False, returns task details and asks for confirmation.
    """
    if task_id <= 0:
        return task_error("task_id must be a positive integer.")

    try:
        check = (
            supabase.table("automation_tasks")
            .select(TASK_COLUMNS)
            .eq("id", task_id)
            .execute()
        )
        if not check.data:
            return task_error(f"Task with ID {task_id} not found.")

        task = check.data[0]

        if not confirm:
            return json_result({
                "success": False,
                "requires_confirmation": True,
                "message": (
                    f"Are you sure you want to delete task #{task_id} '{task.get('task_name')}'? "
                    "Call delete_task with confirm=True to permanently delete it."
                ),
                "task": task,
            })

        supabase.table("automation_tasks").delete().eq("id", task_id).execute()
        return json_result({
            "success": True,
            "message": f"Task #{task_id} ('{task.get('task_name')}') has been permanently deleted.",
        })
    except Exception as exc:
        return task_error(f"Failed to delete task {task_id}: {exc}")


@mcp.tool()
async def sync_email_receipts(max_emails: int = 25) -> str:
    """
    Scan Gmail for unimported PickMe ride receipts and HelaPay payment confirmation bills,
    extract expense details (amounts, dates, merchants, payment methods, reference IDs),
    save them to Supabase, and prevent duplicate imports.
    PickMe rides are mapped to Transport, while HelaPay payments are classified by actual bill details
    (e.g. Internet, Mobile Reload, Electricity, Water, Insurance).
    """
    import asyncio
    from app.gmail_reader import sync_receipt_emails

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, sync_receipt_emails, max_emails, False)
        return json_result(result)
    except Exception as exc:
        return json_result({
            "success": False,
            "error": f"Failed to sync email receipts: {exc}",
        })


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in ("sse", "streamable-http"):
        mcp.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.getenv("MCP_PORT", "8001"))
        mcp.run(transport=transport)
    else:
        mcp.run(transport="stdio")
