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
    db.table.return_value.select.return_value.in_.return_value.execute.return_value.data=[{"message_id":x,"status":"imported"} for x in ["a","b"]]
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
    monkeypatch.setattr(reader,"detect_and_parse_receipt",lambda *args:{"amount":10})
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
