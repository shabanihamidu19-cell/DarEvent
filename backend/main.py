"""
DarEvents API
- Serves events (sponsored always first)
- Triggers collection
- Simple sponsored management
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
from datetime import datetime
import os
import json

from config import EVENTS_FILE, SPONSORED_FILE, DATA_DIR
from models import Event, EventList, CollectResult
from collector import load_events, save_events, collect_once, seed_from_demo, load_sponsored_ids

app = FastAPI(
    title="DarEvents API",
    description="Automated events platform for Dar es Salaam & Tanzania",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def root():
    index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "DarEvents API is running. Go to /docs"}

@app.get("/api/events", response_model=EventList)
def get_events(
    cat: Optional[str] = Query(None, description="Filter by category"),
    q: Optional[str] = Query(None, description="Search title/location"),
    city: Optional[str] = Query(None),
    sort: Optional[str] = Query("default", description="default | trending | date"),
    limit: int = Query(50, ge=1, le=200),
):
    events = load_events()
    # Ensure likes/dislikes exist
    for e in events:
        e.setdefault("likes", 0)
        e.setdefault("dislikes", 0)
        e.setdefault("image_url", None)

    if cat and cat.lower() != "all":
        events = [e for e in events if cat.lower() in (e.get("cat") or "").lower()]
    if q:
        ql = q.lower()
        events = [e for e in events if ql in (e.get("title") or "").lower() or ql in (e.get("loc") or "").lower()]
    if city:
        events = [e for e in events if city.lower() in (e.get("city") or "").lower()]

    if sort == "trending":
        # Score = likes - dislikes*0.5 + small boost for recent
        events.sort(key=lambda e: (
            not e.get("sponsored", False),
            -(e.get("likes", 0) - e.get("dislikes", 0) * 0.5)
        ))
    else:
        # default: sponsored first, then date
        events.sort(key=lambda e: (not e.get("sponsored", False), e.get("date_iso") or "9999"))

    last = None
    if events:
        lasts = [e.get("last_seen") for e in events if e.get("last_seen")]
        last = max(lasts) if lasts else None

    return EventList(
        events=[Event(**{k: v for k, v in e.items() if k in Event.model_fields}) for e in events[:limit]],
        total=len(events),
        last_updated=last,
    )

@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    events = load_events()
    for e in events:
        if e.get("id") == event_id:
            return e
    raise HTTPException(404, "Event not found")

@app.post("/api/collect", response_model=CollectResult)
def trigger_collect(background_tasks: BackgroundTasks, force: bool = False):
    """Trigger automated collection. Runs in background."""
    def _run():
        try:
            collect_once()
        except Exception as ex:
            print(f"Collect failed: {ex}")
    background_tasks.add_task(_run)
    return CollectResult(message="Collection started in background", total=len(load_events()))

@app.post("/api/seed")
def seed_demo():
    n = seed_from_demo()
    return {"seeded": n}

@app.post("/api/sponsored/{event_id}")
def mark_sponsored(event_id: str, sponsored: bool = True):
    """Mark / unmark an event as sponsored (ads appear first)."""
    events = load_events()
    found = False
    for e in events:
        if e.get("id") == event_id:
            e["sponsored"] = sponsored
            found = True
            break
    if not found:
        raise HTTPException(404, "Event not found")
    save_events(events)

    # Also persist id list
    data = {"ids": []}
    if os.path.exists(SPONSORED_FILE):
        with open(SPONSORED_FILE) as f:
            data = json.load(f)
    ids = set(data.get("ids", []))
    if sponsored:
        ids.add(event_id)
    else:
        ids.discard(event_id)
    with open(SPONSORED_FILE, "w") as f:
        json.dump({"ids": list(ids)}, f, indent=2)
    return {"ok": True, "event_id": event_id, "sponsored": sponsored}

@app.get("/api/health")
def health():
    events = load_events()
    return {
        "status": "ok",
        "events_count": len(events),
        "sponsored_count": sum(1 for e in events if e.get("sponsored")),
        "timestamp": datetime.now().isoformat(),
    }

@app.post("/api/events/submit")
def submit_user_event(payload: dict):
    """Anyone can post an event (free for now). Duration stored for future billing demo."""
    from collector import make_id, normalize_date, save_events, load_events
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "Title required")
    date_raw = payload.get("date") or ""
    date_h, date_iso = normalize_date(date_raw)
    loc = (payload.get("loc") or "").strip()
    eid = make_id(title, date_h or date_iso or "", loc)
    now = datetime.now().isoformat()
    cat = payload.get("cat") or "Matukio"
    emoji_map = {
        "Muziki": "🎵", "Michezo": "⚽", "Usiku": "🌃", "Chakula": "🍽️",
        "Warsha": "🛠️", "Familia": "👨‍👩‍👧", "Teknolojia": "💻", "Sanaa": "🎨", "Biashara": "💼"
    }
    event = {
        "id": eid,
        "emoji": emoji_map.get(cat, "🎉"),
        "cat": cat,
        "title": title,
        "date": date_h or date_raw,
        "date_iso": date_iso or date_raw,
        "time": payload.get("time") or "",
        "loc": loc,
        "price": payload.get("price") or "Bure",
        "sponsored": False,
        "desc": payload.get("desc") or "",
        "source_url": None,
        "image_url": payload.get("image_url"),
        "likes": 0,
        "dislikes": 0,
        "city": "Dar es Salaam",
        "last_seen": now,
        "created_at": now,
        "duration_days": payload.get("duration_days", 2),
        "submitter_phone": payload.get("phone"),
        "ticket_url": payload.get("ticket_url"),
        "status": "published",
    }
    events = load_events()
    if any(e.get("id") == eid for e in events):
        return {"ok": True, "message": "Already exists", "id": eid}
    events.insert(0, event)
    save_events(events)
    return {"ok": True, "id": eid, "message": "Event published"}

@app.post("/api/events/{event_id}/vote")
def vote_event(event_id: str, vote: str = Query(..., regex="^(like|dislike)$")):
    """Like or dislike an event. Used for Trending score."""
    events = load_events()
    found = False
    for e in events:
        if e.get("id") == event_id:
            e.setdefault("likes", 0)
            e.setdefault("dislikes", 0)
            if vote == "like":
                e["likes"] = e.get("likes", 0) + 1
            else:
                e["dislikes"] = e.get("dislikes", 0) + 1
            found = True
            break
    if not found:
        raise HTTPException(404, "Event not found")
    save_events(events)
    return {"ok": True, "id": event_id, "likes": e["likes"], "dislikes": e["dislikes"]}

# Optional: APScheduler for true self-managing (uncomment on server)
# from apscheduler.schedulers.background import BackgroundScheduler
# scheduler = BackgroundScheduler()
# scheduler.add_job(collect_once, "interval", hours=6, id="collect")
# scheduler.start()
