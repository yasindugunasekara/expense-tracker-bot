from unittest.mock import MagicMock
import pytest
from app import gmail_reader as reader

def setup(monkeypatch):
    service=MagicMock()
    monkeypatch.setattr(reader,"get_gmail_service",lambda:service)
    db=MagicMock();monkeypatch.setattr(reader,"supabase",db)
    return service,db

def test_pagination(monkeypatch):
    service,db=setup(monkeypatch)
    service.users.return_value.messages.return_value.list.return_value.execute.side_effect=[{"messages":[{"id":"a"}],"nextPageToken":"next"},{"messages":[{"id":"b"}]}]
    db.table.return_value.select.return_value.in_.return_value.execute.return_value.data=[{"message_id":x,"status":"imported","expense_id":x,"id":x} for x in ["a","b"]]
    result=reader._sync_receipt_emails(1)
    assert result["total_found"]==2 and result["duplicates_skipped"]==2
    assert service.users.return_value.messages.return_value.list.call_args.kwargs["pageToken"]=="next"
    service.users.return_value.messages.return_value.get.assert_not_called()

def test_tracking_failure(monkeypatch):
    service,db=setup(monkeypatch)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value={"messages":[{"id":"a"}]}
    db.table.return_value.select.return_value.in_.return_value.execute.side_effect=RuntimeError("offline")
    with pytest.raises(RuntimeError,match="prevent duplicate"):reader._sync_receipt_emails()
    db.table.return_value.insert.assert_not_called()

def test_partial_recovery(monkeypatch):
    service,db=setup(monkeypatch)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value={"messages":[{"id":"a"}]}
    service.users.return_value.messages.return_value.get.return_value.execute.return_value={"payload":{"headers":[]}}
    monkeypatch.setattr(reader,"detect_and_parse_receipt",lambda *args:{"amount":10,"expense_date":"2026-11-01"})
    db.table.return_value.select.return_value.in_.return_value.execute.return_value.data=[]
    db.table.return_value.select.return_value.like.return_value.limit.return_value.execute.return_value.data=[{"id":42}]
    result=reader._sync_receipt_emails()
    assert result["duplicates_skipped"]==1
    db.table.return_value.insert.assert_not_called()
    assert db.table.return_value.upsert.call_args.args[0]["expense_id"]==42


def test_receipt_date_and_parser():
    assert reader.receipt_header_date("Sun, 01 Nov 2026 20:00:00 +0000")=="2026-11-02"
    parsed=reader.parse_pickme_receipt("PickMe Trip ID 123", "Trip ID 123 Paid Amount LKR 1,234.50", "Sun, 01 Nov 2026 20:00:00 +0000")
    assert parsed["amount"]==1234.5 and parsed["expense_date"]=="2026-11-02"
    with pytest.raises(ValueError):reader.receipt_header_date("invalid")


def test_overlapping_import_reports_busy(monkeypatch,tmp_path):
    from app import gmail_auth
    from filelock import FileLock
    monkeypatch.setattr(gmail_auth,"token_path",lambda:tmp_path/"token.json")
    with FileLock(str(tmp_path/"receipt-sync.lock")):
        result=reader.sync_receipt_emails()
    assert result["busy"] and not result["success"]


def test_stale_import_tracking_does_not_hide_receipt(monkeypatch):
    service,db=setup(monkeypatch)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value={"messages":[{"id":"a"}]}
    service.users.return_value.messages.return_value.get.return_value.execute.return_value={"payload":{"headers":[]}}
    db.table.return_value.select.return_value.in_.return_value.execute.side_effect=[MagicMock(data=[{"message_id":"a","status":"imported","expense_id":999}]),MagicMock(data=[])]
    db.table.return_value.select.return_value.like.return_value.limit.return_value.execute.return_value.data=[{"id":42}]
    monkeypatch.setattr(reader,"detect_and_parse_receipt",lambda *args:{"amount":10,"expense_date":"2026-11-01"})
    result=reader._sync_receipt_emails()
    assert result["missing_links_retried"]==1
    service.users.return_value.messages.return_value.get.assert_called_once()
    assert db.table.return_value.upsert.call_args.args[0]["expense_id"]==42


@pytest.mark.parametrize("value",["2024-06-01","2025-12-31"])
def test_pre_2026_excluded(value):
    assert not reader.validate_receipt({"expense_date":value,"amount":100})


@pytest.mark.parametrize("value",["2026-02-30","2026-13-01","not-a-date","2099-01-01"])
def test_invalid_future_dates_rejected(value):
    with pytest.raises(ValueError):reader.validate_receipt({"expense_date":value,"amount":100})


def test_boundary_and_naive_utc_header():
    assert reader.validate_receipt({"expense_date":"2026-01-01","amount":"100.25"})
    assert reader.receipt_header_date("Wed, 31 Dec 2025 20:00:00 -0000")=="2026-01-01"


def test_invalid_explicit_date_not_replaced_by_header():
    with pytest.raises(ValueError):reader.parse_pickme_receipt("Trip ID 123","Trip ID 123 February 30, 2026 Paid Amount LKR 100","Sun, 01 Nov 2026 12:00:00 +0530")
    with pytest.raises(ValueError):reader.parse_helapay_receipt("You paid Rs. 100 to Dialog","PAID DATE 2026-02-30","Sun, 01 Nov 2026 12:00:00 +0530")


def test_uncertain_fare_and_nonexpense_alerts_excluded():
    assert reader.parse_pickme_receipt("Trip ID 123","Trip ID 123 LKR 100 discount","Sun, 01 Nov 2026 12:00:00 +0530") is None
    assert reader.parse_helapay_receipt("Digital Refund Alert #123","REFUNDED Rs. 998 DATE 2026-10-23","Sun, 01 Nov 2026 12:00:00 +0530") is None
    assert reader.detect_and_parse_receipt("PickMe","Security Alert","New sign-in 2026-10-23","Sun, 01 Nov 2026 12:00:00 +0530") is None


def test_multipart_uses_one_representation():
    import base64
    def part(mime,text):return {"mimeType":mime,"body":{"data":base64.urlsafe_b64encode(text.encode()).decode()}}
    text=reader.extract_payload_text({"parts":[part("text/plain","Old value Rs. 999"),part("text/html","<b>Paid Amount LKR 100</b>")]})
    assert text=="Paid Amount LKR 100"


@pytest.mark.parametrize("authentication,expected",[
    ("mx.google.com; dkim=pass header.i=@mail.helapay.lk; spf=softfail smtp.mailfrom=alerts@mail.helapay.lk; dmarc=pass header.from=mail.helapay.lk",True),
    ("mx.google.com; dkim=pass header.i=@evil.example; dmarc=fail header.from=mail.helapay.lk",False),
    ("mx.google.com; dkim=fail header.i=@mail.helapay.lk; dmarc=fail header.from=mail.helapay.lk",False),
    ("untrusted.example; dkim=pass header.i=@mail.helapay.lk",False),
])
def test_spam_provider_authentication(authentication,expected):
    message={"payload":{"headers":[{"name":"From","value":"HelaPay <alerts@mail.helapay.lk>"},{"name":"Authentication-Results","value":authentication}]}}
    assert reader.verified_spam_receipt(message) is expected


def test_search_includes_spam_but_excludes_trash(monkeypatch):
    service,db=setup(monkeypatch)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value={}
    reader._sync_receipt_emails()
    kwargs=service.users.return_value.messages.return_value.list.call_args.kwargs
    assert kwargs["includeSpamTrash"] is True
    assert "-in:trash" in kwargs["q"]


@pytest.mark.parametrize("labels,authentication,expected",[
    (["SPAM"],"mx.google.com; dkim=pass header.i=@mail.helapay.lk",1),
    (["SPAM"],"mx.google.com; dkim=fail header.i=@mail.helapay.lk",0),
    (["TRASH"],"mx.google.com; dkim=pass header.i=@mail.helapay.lk",0),
])
def test_spam_and_trash_import_behavior(monkeypatch,labels,authentication,expected):
    import base64
    service,db=setup(monkeypatch)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value={"messages":[{"id":"new-receipt"}]}
    text="PAID Rs. 702.00 DATE 2026-11-01 PAYMENT ID 123456 REFERENCE ID 987654321"
    values={"From":"HelaPay <alerts@mail.helapay.lk>","Subject":"You paid Rs.702 to Dialog Broadband","Date":"Sun, 1 Nov 2026 11:55:18 +0530","Authentication-Results":authentication}
    message={"labelIds":labels,"payload":{"mimeType":"text/plain","headers":[{"name":k,"value":v} for k,v in values.items()],"body":{"data":base64.urlsafe_b64encode(text.encode()).decode()}}}
    service.users.return_value.messages.return_value.get.return_value.execute.return_value=message
    db.table.return_value.select.return_value.in_.return_value.execute.return_value.data=[]
    db.table.return_value.select.return_value.like.return_value.limit.return_value.execute.return_value.data=[]
    db.table.return_value.select.return_value.ilike.return_value.execute.return_value.data=[]
    db.table.return_value.insert.return_value.execute.return_value.data=[{"id":77}]
    result=reader._sync_receipt_emails()
    assert result["imported_count"]==expected
    if expected:
        payload=db.table.return_value.insert.call_args.args[0]
        assert payload["amount"]==702 and payload["expense_date"]=="2026-11-01"
        assert payload["source"]=="email_helapay"
    else:db.table.return_value.insert.assert_not_called()
