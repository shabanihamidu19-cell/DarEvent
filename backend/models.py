from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Event(BaseModel):
    id: str
    emoji: str = "🎉"
    cat: str = "Matukio"
    title: str
    date: str  # human readable e.g. "Ijumaa, Ag. 29"
    date_iso: Optional[str] = None  # YYYY-MM-DD for sorting
    time: str = ""
    loc: str = ""
    price: str = "Bure"
    sponsored: bool = False
    desc: str = ""
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    likes: int = 0
    dislikes: int = 0
    city: str = "Dar es Salaam"
    last_seen: Optional[str] = None
    created_at: Optional[str] = None
    ticket_url: Optional[str] = None
    duration_days: Optional[int] = None
    submitter_phone: Optional[str] = None
    status: Optional[str] = "published"

class EventList(BaseModel):
    events: List[Event]
    total: int
    last_updated: Optional[str] = None

class CollectResult(BaseModel):
    added: int = 0
    updated: int = 0
    total: int = 0
    message: str = ""
