"""
DarEvents Automated Collector
Uses Tavily for discovery + AI for structured extraction.
Runs on schedule. Self-managing: dedup, expire old, prioritize sponsored.
"""

import json
import os
import hashlib
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dateutil import parser as date_parser

from config import (
    TAVILY_API_KEY, OPENAI_API_KEY, AI_BASE_URL, AI_MODEL,
    EVENTS_FILE, SPONSORED_FILE, DATA_DIR, SEARCH_QUERIES,
    MAX_EVENTS, DAYS_AHEAD, CITIES
)
from models import Event

# Ensure data dir
os.makedirs(DATA_DIR, exist_ok=True)

def _load_json(path: str, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_events() -> List[Dict]:
    return _load_json(EVENTS_FILE, [])

def save_events(events: List[Dict]):
    # Sort: sponsored first, then by date_iso
    events.sort(key=lambda e: (not e.get("sponsored", False), e.get("date_iso") or "9999"))
    _save_json(EVENTS_FILE, events)

def load_sponsored_ids() -> set:
    data = _load_json(SPONSORED_FILE, {"ids": []})
    return set(data.get("ids", []))

def make_id(title: str, date: str, loc: str) -> str:
    raw = f"{title.lower().strip()}|{date}|{loc.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def normalize_date(date_str: str) -> tuple[str, Optional[str]]:
    """Return (human_readable, iso YYYY-MM-DD)"""
    if not date_str:
        return "", None
    try:
        # Try parse common formats
        dt = date_parser.parse(date_str, fuzzy=True, default=datetime.now())
        iso = dt.strftime("%Y-%m-%d")
        # Simple Swahili-friendly human
        days = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
        months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]
        human = f"{days[dt.weekday()]}, {months[dt.month-1]} {dt.day}"
        return human, iso
    except Exception:
        return date_str, None

def is_future(iso: Optional[str], days_ahead: int = DAYS_AHEAD) -> bool:
    if not iso:
        return True  # keep if unknown
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
        today = datetime.now().date()
        return today <= d <= today + timedelta(days=days_ahead)
    except Exception:
        return True

def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    """Simple similarity without heavy deps if needed."""
    try:
        from fuzzywuzzy import fuzz
        return fuzz.token_sort_ratio(a.lower(), b.lower()) >= threshold * 100
    except ImportError:
        # fallback
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return False
        inter = len(a_set & b_set)
        return inter / max(len(a_set), len(b_set)) >= threshold

# ─── Tavily Discovery ───────────────────────────────────────────────

def tavily_search(query: str, max_results: int = 8) -> List[Dict]:
    if not TAVILY_API_KEY:
        print("⚠️  TAVILY_API_KEY missing – skipping search")
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        resp = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_raw_content=True,
            include_answer=False,
        )
        return resp.get("results", [])
    except Exception as e:
        print(f"Tavily error: {e}")
        return []

def tavily_research(query: str) -> str:
    """Deep research for richer context."""
    if not TAVILY_API_KEY:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        # research endpoint if available, else search
        resp = client.search(
            query=query,
            search_depth="advanced",
            max_results=6,
            include_raw_content=True,
        )
        texts = []
        for r in resp.get("results", []):
            content = r.get("raw_content") or r.get("content") or ""
            texts.append(f"Source: {r.get('url')}\n{content[:2000]}")
        return "\n\n---\n\n".join(texts)
    except Exception as e:
        print(f"Tavily research error: {e}")
        return ""

# ─── AI Structured Extraction ───────────────────────────────────────

EXTRACTION_PROMPT = """You are an expert event data extractor for Tanzania (Dar es Salaam focus).
From the text below, extract ALL upcoming real events (concerts, sports, festivals, nightlife, workshops, food, tech, family, culture).

Return ONLY a valid JSON array of objects. No markdown, no explanation.
Each object must have these fields:
- title: string (event name)
- date: string (e.g. "Ijumaa, Ag. 29" or "2026-09-05" or "Sept 5–7")
- time: string (e.g. "20:00" or "18:00–22:00" or "")
- loc: string (venue + city if possible)
- price: string (e.g. "TZS 15,000" or "Bure" or "Free")
- cat: string (one of: Muziki, Michezo, Usiku, Chakula, Warsha, Familia, Teknolojia, Sanaa, Biashara, Matukio)
- emoji: single emoji matching the category
- desc: short Swahili or English description (1-2 sentences)
- source_url: the URL if available

Rules:
- Only real future or current events. Skip past ones.
- Prefer Dar es Salaam / Tanzania events.
- If price unknown use "Bure" or "Check on site".
- Keep title clean, no extra hashtags.
- If no events found return []

Text:
"""

def ai_extract_events(raw_text: str) -> List[Dict]:
    if not OPENAI_API_KEY or not raw_text.strip():
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=AI_BASE_URL)
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You extract structured event data as pure JSON array only."},
                {"role": "user", "content": EXTRACTION_PROMPT + raw_text[:12000]}
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        content = response.choices[0].message.content.strip()
        # Clean markdown if any
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"AI extraction error: {e}")
        return []

# ─── Main Collect Pipeline ──────────────────────────────────────────

def collect_once() -> Dict[str, Any]:
    """Run one full collection cycle. Safe to call repeatedly."""
    print(f"🚀 Starting collection @ {datetime.now().isoformat()}")
    existing = load_events()
    existing_by_id = {e["id"]: e for e in existing}
    sponsored_ids = load_sponsored_ids()

    new_raw = []
    for q in SEARCH_QUERIES:
        print(f"  Searching: {q[:50]}...")
        results = tavily_search(q, max_results=6)
        for r in results:
            text = (r.get("raw_content") or r.get("content") or "")[:3000]
            if text:
                new_raw.append(f"URL: {r.get('url')}\nTitle: {r.get('title')}\n{text}")

    # Also one deep research
    research_text = tavily_research(
        "List all upcoming events, concerts, festivals, sports matches, workshops and nightlife in Dar es Salaam Tanzania for the next 60 days with dates, venues and ticket prices"
    )
    if research_text:
        new_raw.append(research_text)

    combined = "\n\n==========\n\n".join(new_raw)
    print(f"  Raw content length: {len(combined)} chars")
    extracted = ai_extract_events(combined)
    print(f"  AI extracted: {len(extracted)} candidates")

    added = 0
    updated = 0
    now = datetime.now().isoformat()

    for item in extracted:
        title = (item.get("title") or "").strip()
        if not title or len(title) < 5:
            continue
        date_h, date_iso = normalize_date(item.get("date", ""))
        if not is_future(date_iso):
            continue

        loc = (item.get("loc") or "").strip()
        eid = make_id(title, date_h or date_iso or "", loc)

        # Dedup against existing (fuzzy)
        is_dup = False
        for ex in existing:
            if fuzzy_match(title, ex.get("title", "")) and (
                not date_iso or not ex.get("date_iso") or date_iso == ex.get("date_iso")
            ):
                is_dup = True
                # update last_seen
                if eid in existing_by_id:
                    existing_by_id[eid]["last_seen"] = now
                    updated += 1
                break
        if is_dup:
            continue

        cat = item.get("cat") or "Matukio"
        emoji = item.get("emoji") or {
            "Muziki": "🎵", "Michezo": "⚽", "Usiku": "🌃", "Chakula": "🍽️",
            "Warsha": "🛠️", "Familia": "👨‍👩‍👧", "Teknolojia": "💻", "Sanaa": "🎨"
        }.get(cat, "🎉")

        event = {
            "id": eid,
            "emoji": emoji,
            "cat": cat,
            "title": title,
            "date": date_h or item.get("date", ""),
            "date_iso": date_iso,
            "time": item.get("time") or "",
            "loc": loc,
            "price": item.get("price") or "Bure",
            "sponsored": eid in sponsored_ids or item.get("sponsored", False),
            "desc": item.get("desc") or "",
            "source_url": item.get("source_url"),
            "city": "Dar es Salaam",
            "last_seen": now,
            "created_at": now,
        }
        existing_by_id[eid] = event
        added += 1

    # Rebuild list, drop very old
    final = list(existing_by_id.values())
    final = [e for e in final if is_future(e.get("date_iso"))]
    # Keep max
    final = final[:MAX_EVENTS]
    save_events(final)

    result = {
        "added": added,
        "updated": updated,
        "total": len(final),
        "message": f"Collected {added} new, updated {updated}. Total live: {len(final)}",
        "timestamp": now,
    }
    print(f"✅ {result['message']}")
    return result

def seed_from_demo():
    """Seed initial data from the original demo events so site is never empty."""
    demo = [
        {"id": "demo1", "emoji": "🎸", "cat": "Muziki wa Live", "title": "Kariakoo Groove Night — Vol. XIV", "date": "Ijumaa, Ag. 29", "date_iso": "2026-08-29", "time": "20:00", "loc": "Mlimani City Arena", "price": "TZS 15,000", "sponsored": False, "desc": "Usiku mkubwa wa muziki wa bendi za live kutoka Dar es Salaam. Wageni maalum: TMK, G-Nako, na wasanii wa kizazi kipya.", "city": "Dar es Salaam"},
        {"id": "demo2", "emoji": "⚽", "cat": "Michezo", "title": "Simba SC vs Yanga SC — Dar Derby", "date": "Jumamosi, Ag. 30", "date_iso": "2026-08-30", "time": "15:00", "loc": "Benjamin Mkapa Stadium", "price": "TZS 5,000", "sponsored": True, "desc": "Mechi ya kirafiki lakini ya nguvu kati ya Simba SC na Young Africans.", "city": "Dar es Salaam"},
        {"id": "demo3", "emoji": "🌅", "cat": "Usiku wa Burudani", "title": "Sunset Rooftop — Coco Beach", "date": "Kila Ijumaa", "date_iso": "2026-08-29", "time": "18:00–22:00", "loc": "Coco Beach Hotel Rooftop", "price": "TZS 10,000", "sponsored": False, "desc": "Jiburudishe juu ya paa na mandhari nzuri ya Bahari ya Hindi.", "city": "Dar es Salaam"},
        {"id": "demo4", "emoji": "🍳", "cat": "Chakula & Kinywaji", "title": "Dar Food Festival 2026", "date": "Ag. 29 – 31", "date_iso": "2026-08-29", "time": "10:00–22:00", "loc": "Mnazi Mmoja Grounds", "price": "Bure", "sponsored": True, "desc": "Tamasha kubwa la vyakula vya Tanzania na Afrika Mashariki.", "city": "Dar es Salaam"},
        {"id": "demo5", "emoji": "💻", "cat": "Teknolojia", "title": "TechDar Bootcamp — AI & Web Dev", "date": "Sept 5–7, 2026", "date_iso": "2026-09-05", "time": "09:00–17:00", "loc": "UDSM Innovation Hub", "price": "TZS 50,000", "sponsored": False, "desc": "Kozi ya siku tatu ya kujifunza AI na maendeleo ya wavuti.", "city": "Dar es Salaam"},
        {"id": "demo6", "emoji": "🎤", "cat": "Muziki", "title": "Bongo Flava Live — Uhuru Gardens", "date": "Jumapili, Ag. 31", "date_iso": "2026-08-31", "time": "17:00", "loc": "Uhuru Gardens, Kivukoni", "price": "TZS 8,000", "sponsored": False, "desc": "Mshororo wa wasanii wa Bongo Flava.", "city": "Dar es Salaam"},
        {"id": "demo7", "emoji": "🏃", "cat": "Michezo", "title": "Dar es Salaam Marathon 2026", "date": "Sept 13, 2026", "date_iso": "2026-09-13", "time": "06:00", "loc": "Uhuru Monument — Kariakoo", "price": "TZS 20,000", "sponsored": True, "desc": "Mbio za kilometa 42 kati ya jiji la Dar es Salaam.", "city": "Dar es Salaam"},
        {"id": "demo8", "emoji": "🎨", "cat": "Sanaa & Utamaduni", "title": "Bagamoyo Arts Festival", "date": "Sept 19–21", "date_iso": "2026-09-19", "time": "Siku Nzima", "loc": "Bagamoyo Town Centre", "price": "TZS 3,000", "sponsored": False, "desc": "Tamasha la sanaa za jadi na za kisasa kutoka Tanzania.", "city": "Dar es Salaam"},
    ]
    now = datetime.now().isoformat()
    for e in demo:
        e["last_seen"] = now
        e["created_at"] = now
    save_events(demo)
    print(f"Seeded {len(demo)} demo events")
    return len(demo)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_from_demo()
    else:
        # If no keys, just seed so frontend works
        if not TAVILY_API_KEY or not OPENAI_API_KEY:
            print("No API keys set → seeding demo data only")
            seed_from_demo()
        else:
            collect_once()
