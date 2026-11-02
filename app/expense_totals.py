"""Date-based expense reads shared by reports and budget alerts."""
from decimal import Decimal
from app.core.database import supabase


def read_expenses(start_date, end_date, event_id=None, category=None):
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")
    rows = []
    offset = 0
    while True:
        query = (supabase.table("expenses")
                 .select("id,title,amount,category,subcategory,expense_date")
                 .gte("expense_date", start_date.isoformat())
                 .lt("expense_date", end_date.isoformat()).order("id"))
        if event_id is not None:
            query = query.eq("event_id", event_id)
        if category:
            query = query.ilike("category", category)
        page = query.range(offset, offset + 499).execute().data or []
        rows.extend(page)
        if len(page) < 500:
            return rows
        offset += 500


def total_amount(rows):
    total = sum((Decimal(str(row["amount"])) for row in rows), Decimal("0"))
    if not total.is_finite():
        raise ValueError("Expense amount must be finite")
    return total.quantize(Decimal("0.01"))
