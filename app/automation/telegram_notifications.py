"""Durable Telegram receipts for newly saved Gmail expenses."""
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal

import httpx
from app.gmail_auth import token_path

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def format_expense_notification(expense):
    lines = ["Expense saved successfully!", "",
             f"Description: {expense['title']}",
             f"Amount: LKR {Decimal(str(expense['amount'])):,.2f}",
             f"Category: {expense['category']}"]
    if expense.get("subcategory"):
        lines.append(f"Tag / Keyword: {expense['subcategory']}")
    lines.extend([f"Date: {expense['expense_date']}", "Source: Email import"])
    return "\n".join(lines)


@contextmanager
def database():
    path = token_path().parent / "telegram-notifications.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    os.chmod(path, 0o600)
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS notifications (
            message_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
            sent_at REAL, telegram_message_id INTEGER, last_error TEXT)""")
        yield db
        db.commit()
    finally:
        db.close()


def queue_notification(message_id, expense):
    try:
        with database() as db:
            db.execute("INSERT OR IGNORE INTO notifications(message_id,payload) VALUES (?,?)",
                       (message_id, json.dumps(expense, default=str)))
        return True
    except (OSError, sqlite3.Error):
        logger.error("Expense saved, but Telegram notification could not be queued")
        return False


def send_notification(expense):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    recipient = os.getenv("TELEGRAM_ALLOWED_USER_ID")
    if not token or not recipient:
        raise RuntimeError("Telegram notification configuration is missing")
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(recipient), "text": format_expense_notification(expense)},
            timeout=20,
        )
        # Never expose a request URL containing the bot credential in exceptions/logs.
        if response.status_code != 200:
            raise RuntimeError(f"Telegram notification rejected (HTTP {response.status_code})")
        result = response.json()
        if not result.get("ok") or not result.get("result", {}).get("message_id"):
            raise RuntimeError("Telegram did not confirm notification delivery")
        return result["result"]["message_id"]
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("Telegram notification temporarily unavailable") from None


def deliver_pending():
    sent = failed = 0
    try:
        with database() as db:
            rows = db.execute("SELECT message_id,payload,attempts FROM notifications WHERE sent_at IS NULL AND attempts < 5 AND next_attempt <= ? ORDER BY rowid LIMIT 100", (time.time(),)).fetchall()
        for message_id, payload, attempts in rows:
            try:
                telegram_id = send_notification(json.loads(payload))
            except Exception:
                failed += 1
                with database() as db:
                    db.execute("UPDATE notifications SET attempts=attempts+1,next_attempt=?,last_error=? WHERE message_id=?", (time.time() + min(3600, 60 * 2 ** attempts), "Telegram delivery failed; expense remains saved", message_id))
                logger.warning("Telegram receipt notification deferred; expense remains saved")
            else:
                with database() as db:
                    db.execute("UPDATE notifications SET sent_at=?,telegram_message_id=?,last_error=NULL WHERE message_id=?", (time.time(), telegram_id, message_id))
                sent += 1
        return {"sent": sent, "failed": failed}
    except (OSError, sqlite3.Error):
        logger.error("Telegram notification queue unavailable; expense imports remain saved")
        return {"sent": sent, "failed": failed + 1}
