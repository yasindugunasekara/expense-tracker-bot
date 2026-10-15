
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.database import supabase
from app.automation.jobs import (
    send_daily_summary,
    send_weekly_summary,
    send_monthly_summary,
    send_threshold_alert_job,
)

TIMEZONE = ZoneInfo("Asia/Colombo")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUMMARY_JOBS = {
    "daily_summary": send_daily_summary,
    "weekly_summary": send_weekly_summary,
    "monthly_summary": send_monthly_summary,
}


def is_threshold_task(task: dict) -> bool:
    """Return True if the task monitors a spending threshold."""
    amt = task.get("threshold_amount")
    return amt is not None and float(amt) > 0


def get_period_key(period_or_type: str, now: datetime) -> str:
    """Return the period string in which a task is allowed to run."""
    clean = (period_or_type or "").strip().lower()

    if clean in ("daily", "daily_summary"):
        return now.strftime("%Y-%m-%d")

    if clean in ("weekly", "weekly_summary"):
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    if clean in ("monthly", "monthly_summary"):
        return now.strftime("%Y-%m")

    return ""


def already_ran_this_period(task: dict, now: datetime) -> bool:
    last_run = task.get("last_run_at")

    if not last_run:
        return False

    try:
        previous = datetime.fromisoformat(
            last_run.replace("Z", "+00:00")
        )

        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=TIMEZONE)

        previous = previous.astimezone(TIMEZONE)

        period_key = (
            task.get("threshold_period")
            or task.get("task_type")
            or ""
        )

        return (
            get_period_key(period_key, previous)
            == get_period_key(period_key, now)
        )
    except (ValueError, TypeError, KeyError):
        logger.exception(
            "Could not read last_run_at for task %s",
            task.get("id"),
        )
        return True


def is_due(task: dict, now: datetime) -> bool:
    if already_ran_this_period(task, now):
        return False

    schedule_time = task.get("schedule_time")

    if is_threshold_task(task):
        # Threshold task: if schedule_time is omitted, runs continuous checks.
        # If schedule_time is provided, wait until the scheduled time.
        if schedule_time:
            try:
                hour, minute, *_ = schedule_time.split(":")
                scheduled_minutes = int(hour) * 60 + int(minute)
            except (ValueError, AttributeError):
                return False

            current_minutes = now.hour * 60 + now.minute
            if current_minutes < scheduled_minutes:
                return False

            period = (task.get("threshold_period") or "daily").lower()
            if period == "weekly" and task.get("day_of_week") is not None:
                if now.weekday() != int(task["day_of_week"]):
                    return False
            if period == "monthly" and task.get("day_of_month") is not None:
                if now.day != int(task["day_of_month"]):
                    return False

        return True

    # Summary task handling
    task_type = task.get("task_type")
    if task_type not in SUMMARY_JOBS:
        return False

    if not schedule_time:
        return False

    try:
        hour, minute, *_ = schedule_time.split(":")
        scheduled_minutes = int(hour) * 60 + int(minute)
    except (ValueError, AttributeError):
        logger.error(
            "Invalid schedule_time for task %s",
            task.get("id"),
        )
        return False

    current_minutes = now.hour * 60 + now.minute

    if current_minutes < scheduled_minutes:
        return False

    if task_type == "weekly_summary":
        if task.get("day_of_week") is None:
            return False
        if now.weekday() != int(task["day_of_week"]):
            return False

    if task_type == "monthly_summary":
        if task.get("day_of_month") is None:
            return False
        if now.day != int(task["day_of_month"]):
            return False

    return True


def record_result(task_id: int, now: datetime, status: str, error: str | None):
    supabase.table("automation_tasks").update(
        {
            "last_run_at": now.isoformat(),
            "last_status": status,
            "last_error": error,
            "updated_at": now.isoformat(),
        }
    ).eq("id", task_id).execute()


def check_due_tasks():
    now = datetime.now(TIMEZONE)

    try:
        response = (
            supabase.table("automation_tasks")
            .select("*")
            .eq("is_active", True)
            .execute()
        )
        tasks = response.data or []
    except Exception:
        logger.exception("Could not load automation tasks from Supabase")
        return

    for task in tasks:
        if not is_due(task, now):
            continue

        task_id = task["id"]
        task_name = task.get("task_name") or f"Task {task_id}"

        if is_threshold_task(task):
            logger.info("Evaluating threshold task %s ('%s')", task_id, task_name)
            try:
                result = send_threshold_alert_job(task, now)
                if result.get("breached"):
                    record_result(task_id, now, "success", None)
                    logger.info(
                        "Threshold task %s breached limit (spent: %s >= limit: %s). Alert email sent.",
                        task_id,
                        result.get("spent"),
                        result.get("threshold"),
                    )
                else:
                    logger.debug(
                        "Threshold task %s evaluated: %s",
                        task_id,
                        result.get("message"),
                    )
            except Exception as exc:
                logger.exception("Threshold task %s failed", task_id)
                try:
                    record_result(
                        task_id,
                        now,
                        "failed",
                        str(exc)[:2000],
                    )
                except Exception:
                    logger.exception(
                        "Could not record failure for task %s",
                        task_id,
                    )
        else:
            task_type = task["task_type"]
            logger.info("Running summary task %s (%s)", task_id, task_type)

            try:
                SUMMARY_JOBS[task_type]()
                record_result(task_id, now, "success", None)
                logger.info("Task %s completed successfully", task_id)

            except Exception as exc:
                logger.exception("Task %s failed", task_id)

                try:
                    record_result(
                        task_id,
                        now,
                        "failed",
                        str(exc)[:2000],
                    )
                except Exception:
                    logger.exception(
                        "Could not record failure for task %s",
                        task_id,
                    )



def auto_sync_receipt_emails(trigger_label: str = "scheduled"):
    """Check for new PickMe and HelaPay emails and import them into Supabase."""
    logger.info("Starting receipt email sync (%s)...", trigger_label)
    try:
        from app.gmail_reader import sync_receipt_emails
        res = sync_receipt_emails(max_emails=50)
        logger.info(
            "Email sync completed (%s): %d inspected, %d newly imported, %d duplicates skipped, %d ignored.",
            trigger_label,
            res.get("total_found", 0),
            res.get("imported_count", 0),
            res.get("duplicates_skipped", 0),
            res.get("ignored_count", 0),
        )
        return res
    except Exception as exc:
        logger.warning("Could not auto-sync email receipts (%s): %s", trigger_label, exc)
        return None


def main():
    scheduler = BlockingScheduler(timezone=TIMEZONE)

    # Check the database every 30 seconds for summary / threshold tasks.
    scheduler.add_job(
        check_due_tasks,
        trigger="interval",
        seconds=30,
        id="check_due_expense_tasks",
        max_instances=1,
        coalesce=True,
    )

    # Twice-daily email receipt sync:
    # 1. Midday at 12:00 PM (12:00 Asia/Colombo)
    # 2. Night at 11:30 PM (23:30 Asia/Colombo)
    scheduler.add_job(
        auto_sync_receipt_emails,
        trigger="cron",
        hour=12,
        minute=0,
        id="auto_sync_receipt_emails_12pm",
        name="Receipt Email Sync (12:00 PM)",
        max_instances=1,
        coalesce=True,
        kwargs={"trigger_label": "12:00 PM Midday"},
    )
    scheduler.add_job(
        auto_sync_receipt_emails,
        trigger="cron",
        hour=23,
        minute=30,
        id="auto_sync_receipt_emails_1130pm",
        name="Receipt Email Sync (11:30 PM)",
        max_instances=1,
        coalesce=True,
        kwargs={"trigger_label": "11:30 PM Night"},
    )

    logger.info("Expense automation scheduler started.")
    logger.info("Timezone: Asia/Colombo")
    logger.info("Email Receipt Sync Schedule: Twice daily at 12:00 PM and 11:30 PM")

    # Run immediate checks on startup
    check_due_tasks()
    auto_sync_receipt_emails("Startup Check")

    scheduler.start()


if __name__ == "__main__":
    main()

