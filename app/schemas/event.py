from typing import Literal
from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    """Schema for creating/starting a new expense event or trip."""
    name: str = Field(..., min_length=1, max_length=200, description="Name of the event or trip")
    event_type: Literal["trip", "campus", "other"] = Field(default="trip", description="Type of event")
    destination: str | None = Field(default=None, max_length=200, description="Destination location if applicable")
    notes: str | None = Field(default=None, description="Additional notes or details")
