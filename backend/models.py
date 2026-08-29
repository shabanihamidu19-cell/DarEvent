from pydantic import BaseModel, Field
from typing import Optional, List

class Event(BaseModel):
    id: str  # EVT-XXXXXXXX (8 hex chars)
    title: str
    category: str
    subcategory: Optional[str] = None
    venue: Optional[str] = None
    location: Optional[str] = None
    address: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD preferred
    time: Optional[str] = None
    price: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    image_url: Optional[str] = None
    confidence: str = Field("low", regex="^(high|medium|low)$")
    sponsored: bool = False
    created_at: Optional[str] = None
    last_seen: Optional[str] = None

class EventList(BaseModel):
    events: List[Event]
    total: int
    last_updated: Optional[str] = None

class CollectResult(BaseModel):
    added: int = 0
    updated: int = 0
    total: int = 0
    message: str = ""
