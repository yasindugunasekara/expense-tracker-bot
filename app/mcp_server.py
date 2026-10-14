
import json
import os
from datetime import date

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("expense-tracker")

API_BASE_URL = os.getenv(
    "EXPENSE_API_URL",
    "http://127.0.0.1:8000",
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
