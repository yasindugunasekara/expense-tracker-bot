from datetime import date
from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    """Schema for creating a new expense."""
    title: str = Field(..., min_length=1, max_length=200, description="Title or description of the expense")
    amount: float = Field(..., gt=0, description="Amount spent (must be greater than 0)")
    category: str = Field(..., min_length=1, max_length=100, description="Primary expense category")
    subcategory: str | None = Field(default=None, max_length=100, description="Subcategory if applicable")
    merchant: str | None = Field(default=None, max_length=150, description="Merchant or vendor name")
    payment_method: str | None = Field(default=None, max_length=50, description="Payment method used")
    expense_date: date | None = Field(default=None, description="Date the expense occurred")
    notes: str | None = Field(default=None, description="Additional notes or comments")
    source: str = Field(default="manual", max_length=50, description="Source of the expense entry")
    event_id: int | None = Field(default=None, description="Associated event or trip ID")


class ExpenseUpdate(BaseModel):
    """Schema for updating an existing expense."""
    title: str | None = Field(default=None, min_length=1, max_length=200)
    amount: float | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    subcategory: str | None = None
    merchant: str | None = None
    payment_method: str | None = None
    expense_date: date | None = None
    notes: str | None = None
    event_id: int | None = None
