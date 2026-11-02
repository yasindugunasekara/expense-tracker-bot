from unittest.mock import MagicMock
import pytest
from app.automation import telegram_notifications as notifications
from app import gmail_reader

real_send_notification = notifications.send_notification


def expense():
    return {"title":"sunday fun","amount":500,"category":"Enjoy","subcategory":"fun","expense_date":"2026-11-01"}


def test_requested_message_format():
    text=notifications.format_expense_notification(expense())
    assert text.startswith("Expense saved successfully!\n\nDescription: sunday fun\nAmount: LKR 500.00\nCategory: Enjoy\nTag / Keyword: fun")
    assert "Date: 2026-11-01" in text and "Source: Email import" in text


def test_persistent_deduplication(monkeypatch):
    send=MagicMock(return_value=77);monkeypatch.setattr(notifications,"send_notification",send)
    assert notifications.queue_notification("gmail-a",expense())
    assert notifications.deliver_pending()=={"sent":1,"failed":0}
    notifications.queue_notification("gmail-a",expense())
    assert notifications.deliver_pending()=={"sent":0,"failed":0}
    send.assert_called_once()


def test_notification_failure_retries_without_duplicate_import(monkeypatch):
    monkeypatch.setattr(notifications,"send_notification",MagicMock(side_effect=RuntimeError("failed")))
    notifications.queue_notification("gmail-a",expense())
    assert notifications.deliver_pending()=={"sent":0,"failed":1}
    assert notifications.deliver_pending()=={"sent":0,"failed":0}
    with notifications.database() as db:db.execute("UPDATE notifications SET next_attempt=0")
    send=MagicMock(return_value=78);monkeypatch.setattr(notifications,"send_notification",send)
    assert notifications.deliver_pending()=={"sent":1,"failed":0}
    with notifications.database() as db:
        assert db.execute("SELECT attempts,sent_at FROM notifications").fetchone()[1] is not None


def test_dry_run_never_sends_notifications(monkeypatch,tmp_path):
    from app import gmail_auth
    monkeypatch.setattr(gmail_auth,"token_path",lambda:tmp_path/"token.json")
    monkeypatch.setattr(gmail_reader,"_sync_receipt_emails",lambda *args:{"success":True})
    send=MagicMock();monkeypatch.setattr(gmail_reader,"deliver_pending",send)
    gmail_reader.sync_receipt_emails(dry_run=True)
    send.assert_not_called()


def test_telegram_request_and_safe_error(monkeypatch):
    module=notifications
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN","test-secret")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID","123")
    response=MagicMock(status_code=200)
    response.json.return_value={"ok":True,"result":{"message_id":99}}
    post=MagicMock(return_value=response);monkeypatch.setattr(module.httpx,"post",post)
    assert real_send_notification(expense())==99
    assert post.call_args.kwargs["json"]["chat_id"]==123
    assert post.call_args.kwargs["timeout"]==20
    response.status_code=403
    with pytest.raises(RuntimeError,match="HTTP 403") as exc:real_send_notification(expense())
    assert "test-secret" not in str(exc.value)
