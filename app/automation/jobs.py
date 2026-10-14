
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.core.database import supabase
from app.automation.email_sender import send_email
from app.automation.email_template import (
    build_summary_email,
    build_threshold_alert_email,
)


TIMEZONE = ZoneInfo("Asia/Colombo")
API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


def get_local_date() -> date:
    return datetime.now(TIMEZONE).date()


def get_summary(start_date: date, end_date: date) -> dict:
    """
    Fetch a summary for [start_date, end_date).

    The end date is exclusive.
    Example: October 14 to October 15 means October 14 only.
    """
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    response = httpx.get(
        f"{API_BASE_URL}/summary",
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        timeout=30.0,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError("The summary API did not return a JSON object.")

    return data



def send_summary_email(
    period_name: str,
    start_date: date,
    end_date: date,
) -> dict:
    summary = get_summary(start_date, end_date)

    last_included_date = end_date - timedelta(days=1)

    # Keep a readable plain-text fallback.
    body = (
        f"{period_name} Expense Summary\n"
        f"Period: {start_date.isoformat()} "
        f"to {last_included_date.isoformat()}\n\n"
        "Summary from your expense tracker:\n\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
    )

    # Generate the branded HTML version.
    html_body = build_summary_email(
        period_name=period_name,
        start_date=start_date,
        end_date_exclusive=end_date,
        summary_data=summary,
    )

    result = send_email(
        subject=f"Expensa | {period_name} Expense Summary",
        body=body,
        html_body=html_body,
    )

    return {
        "success": True,
        "period": period_name,
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date.isoformat(),
        "email_result": result,
    }



def send_daily_summary() -> dict:
    yesterday = get_local_date() - timedelta(days=1)

    return send_summary_email(
        "Daily",
        yesterday,
        yesterday + timedelta(days=1),
    )


def send_weekly_summary() -> dict:
    today = get_local_date()
    this_monday = today - timedelta(days=today.weekday())

    last_monday = this_monday - timedelta(days=7)
    this_monday_exclusive = this_monday

    return send_summary_email(
        "Weekly",
        last_monday,
        this_monday_exclusive,
    )


def send_monthly_summary() -> dict:
    today = get_local_date()
    first_day_this_month = today.replace(day=1)

    last_day_previous_month = first_day_this_month - timedelta(days=1)
    first_day_previous_month = last_day_previous_month.replace(day=1)

    return send_summary_email(
        "Monthly",
        first_day_previous_month,
        first_day_this_month,
    )


def get_category_spending_details(
    category: str | None,
    start_date: date,
    end_date_exclusive: date,
) -> tuple[float, list[dict]]:
    """
    Fetch all expenses for [start_date, end_date_exclusive), optionally filtered by category.
    Returns (total_spent, expenses_list).
    """
    query = (
        supabase.table("expenses")
        .select("id,title,amount,category,subcategory,expense_date")
        .gte("expense_date", start_date.isoformat())
        .lt("expense_date", end_date_exclusive.isoformat())
        .order("expense_date", desc=True)
        .order("id", desc=True)
    )

    clean_category = (category or "").strip()
    if clean_category and clean_category.lower() not in {"all", "all categories", "none"}:
        query = query.ilike("category", clean_category)

    result = query.execute()
    expenses = result.data or []
    total_spent = sum(float(item.get("amount") or 0) for item in expenses)
    return total_spent, expenses


def send_threshold_alert_job(task: dict, now: datetime | None = None) -> dict:
    """
    Check if an automated threshold alert task has exceeded its spending limit.
    If limit is exceeded, generates and sends the threshold alert email.
    """
    period = (task.get("threshold_period") or "daily").strip().lower()
    category = (task.get("category") or "").strip() or "All Categories"
    threshold = float(task.get("threshold_amount") or 0)
    task_name = task.get("task_name") or f"{category} Limit Alert"

    current_date = now.date() if now else get_local_date()

    if period == "weekly":
        start_date = current_date - timedelta(days=current_date.weekday())
        end_date = start_date + timedelta(days=7)
        period_name = "Weekly"
    elif period == "monthly":
        start_date = current_date.replace(day=1)
        if start_date.month == 12:
            end_date = date(start_date.year + 1, 1, 1)
        else:
            end_date = date(start_date.year, start_date.month + 1, 1)
        period_name = "Monthly"
    else:  # default daily
        start_date = current_date
        end_date = current_date + timedelta(days=1)
        period_name = "Daily"

    total_spent, expenses = get_category_spending_details(
        category=category,
        start_date=start_date,
        end_date_exclusive=end_date,
    )

    if total_spent < threshold:
        return {
            "breached": False,
            "category": category,
            "period": period_name,
            "threshold": threshold,
            "spent": total_spent,
            "message": f"Spending of {total_spent} has not reached limit {threshold}.",
        }

    # Generate and send email alert
    html_body = build_threshold_alert_email(
        task_name=task_name,
        category=category,
        period_name=period_name,
        start_date=start_date,
        end_date_exclusive=end_date,
        threshold_amount=threshold,
        spent_amount=total_spent,
        transactions=expenses,
    )

    last_day = end_date - timedelta(days=1)
    body = (
        f"⚠️ EXPENSA BUDGET ALERT: {category} spending reached limit!\n\n"
        f"Task: {task_name}\n"
        f"Period: {period_name} ({start_date.isoformat()} to {last_day.isoformat()})\n"
        f"Limit: LKR {threshold:,.2f}\n"
        f"Actual Spent: LKR {total_spent:,.2f} (+LKR {max(0.0, total_spent - threshold):,.2f} over limit)\n"
        f"Transactions: {len(expenses)} recorded\n\n"
        f"Review your expenses to stay aligned with your budget."
    )

    subject = f"⚠️ Expensa Alert: {category} Limit Reached (Spent: LKR {total_spent:,.2f} / Limit: LKR {threshold:,.2f})"

    email_result = send_email(
        subject=subject,
        body=body,
        html_body=html_body,
    )

    return {
        "breached": True,
        "category": category,
        "period": period_name,
        "threshold": threshold,
        "spent": total_spent,
        "email_result": email_result,
    }
