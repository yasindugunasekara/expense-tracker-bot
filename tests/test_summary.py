from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from app import expense_totals
from app.automation import jobs,email_template
from app.routers.summary import expense_summary

@pytest.mark.parametrize("today,start,end",[(date(2026,11,2),date(2026,10,26),date(2026,11,2)),(date(2026,11,1),date(2026,10,19),date(2026,10,26)),(date(2027,1,4),date(2026,12,28),date(2027,1,4))])
def test_completed_week(monkeypatch,today,start,end):
    monkeypatch.setattr(jobs,"get_local_date",lambda:today)
    send=MagicMock();monkeypatch.setattr(jobs,"send_summary_email",send)
    jobs.send_weekly_summary();send.assert_called_once_with("Weekly",start,end)

def test_boundary_pagination_and_decimal(monkeypatch):
    db=MagicMock();monkeypatch.setattr(expense_totals,"supabase",db)
    query=db.table.return_value.select.return_value.gte.return_value.lt.return_value.order.return_value
    query.range.return_value.execute.side_effect=[MagicMock(data=[{"amount":"0.10"}]*500),MagicMock(data=[{"amount":"0.20"}])]
    rows=expense_totals.read_expenses(date(2026,10,26),date(2026,11,2))
    assert expense_totals.total_amount(rows)==Decimal("50.20")
    db.table.return_value.select.return_value.gte.assert_called_with("expense_date","2026-10-26")
    db.table.return_value.select.return_value.gte.return_value.lt.assert_called_with("expense_date","2026-11-02")
    assert query.range.call_args.args==(500,999)

def test_summary_matches_email(monkeypatch):
    import app.routers.summary as route
    monkeypatch.setattr(route,"read_expenses",lambda *args,**kwargs:[{"amount":"0.10"},{"amount":"0.20"}])
    result=expense_summary(date(2026,10,26),date(2026,11,2))
    assert result["summary"]=={"total_spent":Decimal("0.30"),"expense_count":2}
    html=email_template.build_summary_email("Weekly",date(2026,10,26),date(2026,11,2),result)
    assert "LKR 0.30" in html and "01 Nov 2026" in html

def test_empty_and_missing_summary():
    assert expense_totals.total_amount([])==Decimal("0.00")
    with pytest.raises(ValueError,match="must include"):
        email_template.build_summary_email("Weekly",date(2026,10,26),date(2026,11,2),{"summary":{}})
