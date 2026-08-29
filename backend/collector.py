"""
DarEvents collector — Tavily + Groq (fast path for Render free tier)
"""

import json
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from dateutil import parser as date_parser

from config import (
    TAVILY_API_KEY, OPENAI_API_KEY, AI_BASE_URL, AI_MODEL,
    EVENTS_FILE, SPONSORED_FILE, DATA_DIR, MAX_EVENTS, DAYS_AHEAD,
)

os.makedirs(DATA_DIR, exist_ok=True)

# Few focused queries — finish under Render HTTP timeout
FAST_QUERIES = [
    "upcoming events Dar es Salaam Tanzania this week",
    "concerts live music Dar es Salaam 2026",
    "Simba SC Yanga SC football match Dar es Salaam",
    "Mlimani City events tickets",
    "nightlife festivals Dar es Salaam",
    "tech meetup conference Dar es Salaam",
]

EMOJI = {
    "michezo": "⚽", "muziki": "🎵", "usiku": "🌃", "chakula": "🍽️",
    "technology": "💻", "tech": "💻", "sanaa": "🎨", "familia": "👨‍👩‍👧",
    "biashara": "💼", "elimu": "📚", "dini": "🙏", "warsha": "🛠️",
}


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
    events.sort(key=lambda e: (not e.get("sponsored", False), e.get("date_iso") or e.get("date") or "9999"))
    _save_json(EVENTS_FILE, events)


def load_sponsored_ids() -> set:
    data = _load_json(SPONSORED_FILE, {"ids": []})
    return set(data.get("ids", []))


def make_evt_id() -> str:
    return "EVT-" + secrets.token_hex(4).upper()


def normalize_date_to_iso(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str, fuzzy=True, default=datetime.now())
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def is_future(iso: Optional[str], days_ahead: int = DAYS_AHEAD) -> bool:
    if not iso:
        return True
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
        today = datetime.now().date()
        return today <= d <= today + timedelta(days=days_ahead)
    except Exception:
        return True


def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    try:
        from rapidfuzz import fuzz
        return fuzz.token_sort_ratio(a or "", b or "") / 100.0 >= threshold
    except Exception:
        a_set = set((a or "").lower().split())
        b_set = set((b or "").lower().split())
        if not a_set or not b_set:
            return False
        return len(a_set & b_set) / max(len(a_set), len(b_set)) >= threshold


EXTRACTION_PROMPT = """Extract REAL upcoming events in Dar es Salaam / Tanzania from the text.
Return ONLY a JSON array. Each object:
{{"title":"...","category":"michezo|muziki|usiku|chakula|technology|sanaa|familia|biashara|warsha","venue":"...","location":"Dar es Salaam","date":"YYYY-MM-DD","time":"HH:MM","price":"...","description":"...","source_url":"..."}}
No markdown. If none: []

TEXT:
{search_results}
"""


def tavily_search(query: str, max_results: int = 5) -> List[Dict]:
    if not TAVILY_API_KEY:
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        resp = client.search(query=query, search_depth="basic", max_results=max_results)
        return resp.get("results", [])
    except Exception as e:
        print(f"Tavily error: {e}")
        return []


def ai_extract_events(text: str) -> List[Dict]:
    if not OPENAI_API_KEY or not text.strip():
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=AI_BASE_URL)
        prompt = EXTRACTION_PROMPT.format(search_results=text[:6000])
        response = client.chat.completions.create(
            model=AI_MODEL or "llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Return pure JSON array only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2500,
        )
        content = (response.choices[0].message.content or "").strip()
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        start, end = content.find("["), content.rfind("]")
        if start >= 0 and end > start:
            content = content[start : end + 1]
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"AI extraction error: {e}")
        return []


def normalize_category(cat: Optional[str]) -> str:
    if not cat:
        return "Matukio"
    c = cat.strip().lower()
    mapping = {
        "michezo": "Michezo", "sports": "Michezo",
        "technology": "Teknolojia", "tech": "Teknolojia",
        "muziki": "Muziki", "music": "Muziki",
        "usiku": "Usiku", "nightlife": "Usiku",
        "chakula": "Chakula", "food": "Chakula",
        "sanaa": "Sanaa", "familia": "Familia",
        "biashara": "Biashara", "warsha": "Warsha", "elimu": "Warsha",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return cat.title()


def to_frontend(e: Dict) -> Dict:
    cat = normalize_category(e.get("category") or e.get("cat"))
    iso = e.get("date_iso") or normalize_date_to_iso(e.get("date") or "") or e.get("date")
    loc = e.get("loc") or e.get("venue") or e.get("location") or ""
    now = datetime.now().isoformat()
    return {
        "id": e.get("id") or make_evt_id(),
        "emoji": e.get("emoji") or EMOJI.get((e.get("category") or "").lower(), "🎉"),
        "cat": cat,
        "title": e.get("title") or "",
        "date": e.get("date") or iso or "",
        "date_iso": iso,
        "time": e.get("time") or "",
        "loc": loc,
        "price": e.get("price") or "Bure",
        "sponsored": bool(e.get("sponsored", False)),
        "desc": e.get("desc") or e.get("description") or "",
        "source_url": e.get("source_url"),
        "image_url": e.get("image_url"),
        "likes": int(e.get("likes") or 0),
        "dislikes": int(e.get("dislikes") or 0),
        "city": e.get("city") or e.get("location") or "Dar es Salaam",
        "last_seen": e.get("last_seen") or now,
        "created_at": e.get("created_at") or now,
        "status": e.get("status") or "published",
    }


def collect_once() -> Dict[str, Any]:
    print(f"Starting collection @ {datetime.now().isoformat()}")
    diag = {
        "tavily_ok": bool(TAVILY_API_KEY),
        "ai_ok": bool(OPENAI_API_KEY),
        "model": AI_MODEL,
        "base": AI_BASE_URL,
        "hits": 0,
        "raw_chars": 0,
        "extracted": 0,
        "ai_error": None,
    }
    if not TAVILY_API_KEY:
        return {"added": 0, "updated": 0, "total": len(load_events()), "message": "TAVILY_API_KEY missing", "diag": diag}
    if not OPENAI_API_KEY:
        return {"added": 0, "updated": 0, "total": len(load_events()), "message": "GROQ_API_KEY missing", "diag": diag}

    existing = [to_frontend(e) for e in load_events()]
    by_title = {(e.get("title") or "").lower().strip(): e for e in existing}

    raw_blocks = []
    for q in FAST_QUERIES:
        print(f"  Search: {q}")
        results = tavily_search(q, max_results=5)
        diag["hits"] += len(results)
        for r in results:
            snippet = (r.get("content") or "")[:1200]
            if snippet:
                raw_blocks.append(f"URL: {r.get('url')}\nTitle: {r.get('title')}\n{snippet}")

    combined = "\n\n---\n\n".join(raw_blocks)
    diag["raw_chars"] = len(combined)
    print(f"  Raw chars: {len(combined)}")

    extracted = []
    try:
        extracted = ai_extract_events(combined)
    except Exception as e:
        diag["ai_error"] = str(e)
    diag["extracted"] = len(extracted)
    print(f"  Extracted: {len(extracted)}")

    added = updated = 0
    now = datetime.now().isoformat()
    for item in extracted:
        title = (item.get("title") or "").strip()
        if len(title) < 5:
            continue
        iso = normalize_date_to_iso(item.get("date") or "")
        if iso and not is_future(iso):
            continue
        key = title.lower()
        if key in by_title or any(fuzzy_match(title, e.get("title", "")) for e in by_title.values()):
            updated += 1
            continue
        event = to_frontend({
            "id": make_evt_id(),
            "title": title,
            "category": item.get("category"),
            "date": item.get("date") or iso or "",
            "date_iso": iso,
            "time": item.get("time") or "",
            "venue": item.get("venue"),
            "location": item.get("location") or "Dar es Salaam",
            "price": item.get("price") or "Bure",
            "description": item.get("description") or "",
            "source_url": item.get("source_url"),
            "created_at": now,
            "last_seen": now,
        })
        by_title[key] = event
        added += 1

    final = list(by_title.values())
    final = [e for e in final if is_future(e.get("date_iso"))]
    if not final and existing:
        final = existing
    final = final[:MAX_EVENTS]
    save_events(final)

    tip = None
    if diag["raw_chars"] == 0:
        tip = "Tavily empty"
    elif diag["extracted"] == 0:
        tip = diag["ai_error"] or "AI returned 0"
    elif added == 0:
        tip = "All filtered past/duplicate"

    return {
        "added": added,
        "updated": updated,
        "total": len(final),
        "message": f"Collected {added} new, updated {updated}. Total: {len(final)}",
        "timestamp": now,
        "diag": diag,
        "tip": tip,
    }


def seed_from_demo() -> int:
    demo = [
        {"id": "demo1", "emoji": "🎸", "cat": "Muziki", "title": "Kariakoo Groove Night — Vol. XIV", "date": "Ijumaa, Ag. 29", "date_iso": "2026-08-29", "time": "20:00", "loc": "Mlimani City Arena", "price": "TZS 15,000", "sponsored": False, "desc": "Usiku wa muziki live.", "city": "Dar es Salaam"},
        {"id": "demo2", "emoji": "⚽", "cat": "Michezo", "title": "Simba SC vs Yanga SC — Dar Derby", "date": "Jumamosi, Ag. 30", "date_iso": "2026-08-30", "time": "15:00", "loc": "Benjamin Mkapa Stadium", "price": "TZS 5,000", "sponsored": True, "desc": "Derby ya Dar.", "city": "Dar es Salaam"},
        {"id": "demo3", "emoji": "🌅", "cat": "Usiku", "title": "Sunset Rooftop — Coco Beach", "date": "Kila Ijumaa", "date_iso": "2026-08-29", "time": "18:00", "loc": "Coco Beach Hotel", "price": "TZS 10,000", "sponsored": False, "desc": "Rooftop.", "city": "Dar es Salaam"},
        {"id": "demo4", "emoji": "🍳", "cat": "Chakula", "title": "Dar Food Festival 2026", "date": "Ag. 29 – 31", "date_iso": "2026-08-29", "time": "10:00", "loc": "Mnazi Mmoja Grounds", "price": "Bure", "sponsored": True, "desc": "Vyakula.", "city": "Dar es Salaam"},
        {"id": "demo5", "emoji": "💻", "cat": "Teknolojia", "title": "TechDar Bootcamp", "date": "Sept 5–7", "date_iso": "2026-09-05", "time": "09:00", "loc": "UDSM Innovation Hub", "price": "TZS 50,000", "sponsored": False, "desc": "AI & Web.", "city": "Dar es Salaam"},
        {"id": "demo6", "emoji": "🎤", "cat": "Muziki", "title": "Bongo Flava Live", "date": "Jumapili, Ag. 31", "date_iso": "2026-08-31", "time": "17:00", "loc": "Uhuru Gardens", "price": "TZS 8,000", "sponsored": False, "desc": "Bongo Flava.", "city": "Dar es Salaam"},
        {"id": "demo7", "emoji": "🏃", "cat": "Michezo", "title": "Dar Marathon 2026", "date": "Sept 13", "date_iso": "2026-09-13", "time": "06:00", "loc": "Uhuru Monument", "price": "TZS 20,000", "sponsored": True, "desc": "42km.", "city": "Dar es Salaam"},
        {"id": "demo8", "emoji": "🎨", "cat": "Sanaa", "title": "Bagamoyo Arts Festival", "date": "Sept 19–21", "date_iso": "2026-09-19", "time": "Siku nzima", "loc": "Bagamoyo", "price": "TZS 3,000", "sponsored": False, "desc": "Sanaa.", "city": "Dar es Salaam"},
    ]
    now = datetime.now().isoformat()
    for e in demo:
        e["last_seen"] = now
        e["created_at"] = now
        e["likes"] = 0
        e["dislikes"] = 0
    save_events(demo)
    return len(demo)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_from_demo()
    else:
        collect_once()
