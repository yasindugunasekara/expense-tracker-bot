import base64,json
from datetime import datetime,timedelta
from email import message_from_bytes
from unittest.mock import MagicMock
import pytest
from app import gmail_auth as auth
from app.automation import email_sender,scheduler

def test_refresh_atomic(monkeypatch,tmp_path):
    token=tmp_path/"token.json";token.write_text("{}")
    monkeypatch.setattr(auth,"TOKEN_FILE",token)
    c=MagicMock(valid=False,refresh_token="test")
    c.to_json.return_value='{"refreshed":true}'
    def refresh(request): c.valid=True
    c.refresh.side_effect=refresh
    load=MagicMock(return_value=c)
    monkeypatch.setattr(auth.Credentials,"from_authorized_user_file",load)
    assert auth.get_credentials(["read"]) is c
    load.assert_called_once_with(str(token))
    assert "refreshed" in token.read_text()
    assert not list(tmp_path.glob(".gmail-*.tmp"))

@pytest.mark.parametrize("kind",["missing","scope","revoked"])
def test_auth_failure(monkeypatch,tmp_path,kind):
    from google.auth.exceptions import RefreshError
    token=tmp_path/"token.json";token.write_text("{}")
    monkeypatch.setattr(auth,"TOKEN_FILE",token)
    c=MagicMock(valid=False,refresh_token="test")
    c.has_scopes.return_value=kind!="scope"
    c.refresh.side_effect=RefreshError("private error")
    monkeypatch.setattr(auth.Credentials,"from_authorized_user_file",MagicMock(side_effect=ValueError() if kind=="missing" else None,return_value=c))
    with pytest.raises(PermissionError,match="locally"): auth.get_credentials(["send"])

def test_send_mime(monkeypatch):
    service=MagicMock()
    send=service.users.return_value.messages.return_value.send
    send.return_value.execute.return_value={"id":"sent"}
    monkeypatch.setattr(auth,"get_gmail_service",lambda scopes:service)
    assert email_sender.send_email("subject","plain","test@example.invalid","<b>html</b>")["message_id"]=="sent"
    message=message_from_bytes(base64.urlsafe_b64decode(send.call_args.kwargs["body"]["raw"]))
    assert message.is_multipart()
    assert message["To"]=="test@example.invalid"
    send.return_value.execute.return_value={}
    with pytest.raises(RuntimeError): email_sender.send_email("s","b")

def task(now,status="failed",attempts=1):
    return {"task_type":"weekly_summary","schedule_time":"00:00","day_of_week":now.weekday(),"last_run_at":(now-timedelta(minutes=5)).isoformat(),"last_status":status,"last_error":json.dumps({"attempts":attempts})}

def test_retry_and_suppression():
    now=datetime(2026,11,2,8,tzinfo=scheduler.TIMEZONE)
    assert scheduler.is_due(task(now),now)
    assert not scheduler.is_due(task(now,"success"),now)
    assert not scheduler.is_due(task(now,attempts=5),now)
    recent=task(now);recent["last_run_at"]=(now-timedelta(seconds=10)).isoformat()
    assert not scheduler.is_due(recent,now)

def test_bad_task_isolated(monkeypatch):
    db=MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data=[{"id":1,"threshold_amount":"bad"},{"id":2,"task_type":"daily_summary","schedule_time":"00:00"}]
    monkeypatch.setattr(scheduler,"supabase",db)
    send=MagicMock();monkeypatch.setitem(scheduler.SUMMARY_JOBS,"daily_summary",send)
    scheduler.check_due_tasks();send.assert_called_once()


def test_valid_token_no_refresh(monkeypatch,tmp_path):
    token=tmp_path/"token.json";token.write_text("{}")
    monkeypatch.setattr(auth,"TOKEN_FILE",token)
    c=MagicMock(valid=True)
    monkeypatch.setattr(auth.Credentials,"from_authorized_user_file",lambda path:c)
    assert auth.get_credentials(["read"]) is c
    c.refresh.assert_not_called()


def test_refresh_transport_error(monkeypatch,tmp_path):
    from google.auth.exceptions import TransportError
    token=tmp_path/"token.json";token.write_text("{}")
    monkeypatch.setattr(auth,"TOKEN_FILE",token)
    c=MagicMock(valid=False,refresh_token="test")
    c.refresh.side_effect=TransportError("private")
    monkeypatch.setattr(auth.Credentials,"from_authorized_user_file",lambda path:c)
    with pytest.raises(ConnectionError,match="temporarily"):
        auth.get_credentials(["read"])


def test_concurrent_refresh_once(monkeypatch,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    token=tmp_path/"token.json";token.write_text("stale")
    monkeypatch.setattr(auth,"TOKEN_FILE",token)
    refreshes=[]
    def load(path):
        c=MagicMock(valid=token.read_text()=="fresh",refresh_token="test")
        def refresh(request):
            refreshes.append(1)
            c.valid=True
        c.refresh.side_effect=refresh
        c.to_json.return_value="fresh"
        return c
    monkeypatch.setattr(auth.Credentials,"from_authorized_user_file",load)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(c.valid for c in pool.map(lambda _:auth.get_credentials(["read"]),range(4)))
    assert len(refreshes)==1


def test_gmail_network_timeout(monkeypatch):
    credentials=MagicMock()
    monkeypatch.setattr(auth,"get_credentials",lambda scopes:credentials)
    http=MagicMock();monkeypatch.setattr(auth.httplib2,"Http",http)
    authorized=MagicMock();monkeypatch.setattr(auth,"AuthorizedHttp",authorized)
    build=MagicMock();monkeypatch.setattr(auth,"build",build)
    auth.get_gmail_service(["read"])
    http.assert_called_once_with(timeout=30)
    authorized.assert_called_once_with(credentials,http=http.return_value)
    assert "credentials" not in build.call_args.kwargs


def test_startup_sync_does_not_block_scheduler(monkeypatch):
    instance=MagicMock()
    monkeypatch.setattr(scheduler,"BlockingScheduler",lambda **kwargs:instance)
    monkeypatch.setattr(scheduler,"check_due_tasks",MagicMock())
    sync=MagicMock();monkeypatch.setattr(scheduler,"auto_sync_receipt_emails",sync)
    scheduler.main()
    sync.assert_not_called()
    instance.start.assert_called_once()
    assert any(c.kwargs.get("id")=="startup_receipt_sync" for c in instance.add_job.call_args_list)


def test_only_one_hourly_receipt_job(monkeypatch):
    instance=MagicMock()
    monkeypatch.setattr(scheduler,"BlockingScheduler",lambda **kwargs:instance)
    monkeypatch.setattr(scheduler,"check_due_tasks",MagicMock())
    sync=MagicMock();monkeypatch.setattr(scheduler,"auto_sync_receipt_emails",sync)
    scheduler.main()
    jobs=[c for c in instance.add_job.call_args_list if c.args[0] is sync and c.kwargs.get("trigger")=="cron"]
    assert len(jobs)==1
    assert jobs[0].kwargs["hour"]=="*" and jobs[0].kwargs["minute"]==0
    assert jobs[0].kwargs["max_instances"]==1 and jobs[0].kwargs["coalesce"]
