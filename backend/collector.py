"""
DarEvents collector — Tavily + Groq
If AI returns 0, fallback uses Tavily titles as real events (still not demo).
"""

import json
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from dateutil import parser as date_parser

from config import (
    TAVILY_API_KEY, OPENAI_API_KEY, AI_BASE_URL, AI_MODEL,
    EVENTS_FILE, SPONSORED_FILE, DATA_DIR, MAX_EVENTS, DAYS_AHEAD,
)

os.makedirs(DATA_DIR, exist_ok=True)

FAST_QUERIES = [
    "upcoming events Dar es Salaam Tanzania 2026",
    "concerts live music tickets Dar es Salaam",
    "Simba SC vs Yanga match schedule Tanzania",
    "Mlimani City events concert",
    "festival nightlife Dar es Salaam this month",
    "tech conference meetup Dar es Salaam",
]

EMOJI = {
    "michezo": "⚽", "muziki": "🎵", "usiku": "🌃", "chakula": "🍽️",
    "technology": "💻", "tech": "💻", "sanaa": "🎨", "familia": "👨‍👩‍👧",
    "biashara": "💼", "warsha": "🛠️", "matukio": "🎉",
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


def _parse_json_loose(content: str) -> List[Dict]:
    content = (content or "").strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    # try array
    start, end = content.find("["), content.rfind("]")
    if start >= 0 and end > start:
        try:
            data = json.loads(content[start : end + 1])
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
    # try object with events key
    start, end = content.find("{"), content.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(content[start : end + 1])
            if isinstance(data, dict):
                for k in ("events", "data", "results", "items"):
                    if isinstance(data.get(k), list):
                        return [x for x in data[k] if isinstance(x, dict)]
                if "title" in data:
                    return [data]
        except Exception:
            pass
    return []


def ai_extract_events(text: str) -> Tuple[List[Dict], Optional[str]]:
    """Returns (events, error_or_preview)."""
    if not OPENAI_API_KEY or not text.strip():
        return [], "no key or empty text"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=AI_BASE_URL)
        prompt = (
            "From the web search text below, list upcoming REAL events in Dar es Salaam or Tanzania.\n"
            'Reply with ONLY JSON: {"events":[{"title":"...","category":"muziki|michezo|usiku|chakula|technology|sanaa","venue":"...","date":"YYYY-MM-DD or text","time":"","price":"","description":"short","source_url":"url if known"}]}\n'
            "If none found: {\"events\":[]}\n\n"
            + text[:5000]
        )
        response = client.chat.completions.create(
            model=AI_MODEL or "llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You output only valid JSON. No markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=2000,
        )
        content = (response.choices[0].message.content or "").strip()
        parsed = _parse_json_loose(content)
        if not parsed:
            return [], f"parse_fail preview={content[:180]!r}"
        return parsed, None
    except Exception as e:
        return [], str(e)


def fallback_from_tavily(results: List[Dict]) -> List[Dict]:
    """Turn search hits into events when AI fails — still real web data, not demo."""
    out = []
    skip = re.compile(r"wikipedia|login|signup|privacy|terms|about us|home page", re.I)
    eventish = re.compile(
        r"event|concert|festival|match|ticket|live|meetup|conference|show|party|"
        r"simba|yanga|marathon|workshop|seminar|nightlife|gig", re.I
    )
    for r in results:
        title = (r.get("title") or "").strip()
        url = r.get("url") or ""
        content = (r.get("content") or "")[:400]
        if len(title) < 8 or skip.search(title):
            continue
        if not (eventish.search(title) or eventish.search(content)):
            continue
        cat = "Matukio"
        tl = title.lower()
        if any(w in tl for w in ("concert", "music", "live", "flava", "band")):
            cat = "muziki"
        elif any(w in tl for w in ("simba", "yanga", "football", "match", "marathon")):
            cat = "michezo"
        elif any(w in tl for w in ("tech", "meetup", "hack", "conference")):
            cat = "technology"
        elif any(w in tl for w in ("party", "nightlife", "club")):
            cat = "usiku"
        out.append({
            "title": title[:120],
            "category": cat,
            "venue": "",
            "location": "Dar es Salaam",
            "date": "",
            "time": "",
            "price": "Check on site",
            "description": content[:200],
            "source_url": url,
        })
        if len(out) >= 15:
            break
    return out


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
        "biashara": "Biashara", "warsha": "Warsha",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return cat.title()


def to_frontend(e: Dict) -> Dict:
    cat = normalize_category(e.get("category") or e.get("cat"))
    iso = e.get("date_iso") or normalize_date_to_iso(str(e.get("date") or ""))
    loc = e.get("loc") or e.get("venue") or e.get("location") or ""
    now = datetime.now().isoformat()
    return {
        "id": e.get("id") or make_evt_id(),
        "emoji": e.get("emoji") or EMOJI.get((e.get("category") or "").lower(), "🎉"),
        "cat": cat,
        "title": e.get("title") or "",
        "date": e.get("date") or iso or "Tarehe TBA",
        "date_iso": iso,
        "time": e.get("time") or "",
        "loc": loc or "Dar es Salaam",
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
        "hits": 0,
        "raw_chars": 0,
        "extracted": 0,
        "fallback": 0,
        "ai_error": None,
    }
    if not TAVILY_API_KEY:
        return {"added": 0, "updated": 0, "total": len(load_events()), "message": "TAVILY_API_KEY missing", "diag": diag}

    existing = [to_frontend(e) for e in load_events()]
    by_title = {(e.get("title") or "").lower().strip(): e for e in existing}

    all_results = []
    raw_blocks = []
    for q in FAST_QUERIES:
        print(f"  Search: {q}")
        results = tavily_search(q, max_results=5)
        diag["hits"] += len(results)
        all_results.extend(results)
        for r in results:
            snippet = (r.get("content") or "")[:1000]
            if snippet or r.get("title"):
                raw_blocks.append(f"URL: {r.get('url')}\nTitle: {r.get('title')}\n{snippet}")

    combined = "\n\n---\n\n".join(raw_blocks)
    diag["raw_chars"] = len(combined)

    extracted, ai_err = [], None
    if OPENAI_API_KEY and combined:
        extracted, ai_err = ai_extract_events(combined)
        diag["ai_error"] = ai_err
    diag["extracted"] = len(extracted)

    if not extracted and all_results:
        extracted = fallback_from_tavily(all_results)
        diag["fallback"] = len(extracted)
        print(f"  Fallback events: {len(extracted)}")

    added = updated = 0
    now = datetime.now().isoformat()
    for item in extracted:
        title = (item.get("title") or "").strip()
        if len(title) < 5:
            continue
        iso = normalize_date_to_iso(str(item.get("date") or ""))
        if iso and not is_future(iso):
            continue
        key = title.lower()
        if key in by_title or any(fuzzy_match(title, e.get("title", "")) for e in by_title.values()):
            updated += 1
            continue
        # replace demo slots when we get real data
        event = to_frontend({
            "id": make_evt_id(),
            "title": title,
            "category": item.get("category"),
            "date": item.get("date") or iso or "",
            "date_iso": iso,
            "time": item.get("time") or "",
            "venue": item.get("venue"),
            "location": item.get("location") or "Dar es Salaam",
            "price": item.get("price") or "Check on site",
            "description": item.get("description") or "",
            "source_url": item.get("source_url"),
            "created_at": now,
            "last_seen": now,
        })
        by_title[key] = event
        added += 1

    final = list(by_title.values())
    # Prefer real (source_url) over demo when mixing
    real = [e for e in final if e.get("source_url") and not str(e.get("id", "")).startswith("demo")]
    demos = [e for e in final if str(e.get("id", "")).startswith("demo")]
    others = [e for e in final if e not in real and e not in demos]
    if real:
        final = real + others + demos  # real first
    final = [e for e in final if is_future(e.get("date_iso"))]
    if not final:
        final = existing
    final = final[:MAX_EVENTS]
    save_events(final)

    tip = None
    if diag["raw_chars"] == 0:
        tip = "Tavily empty"
    elif added == 0 and diag["extracted"] == 0 and diag["fallback"] == 0:
        tip = diag["ai_error"] or "Nothing extracted"
    elif added == 0:
        tip = "All filtered as duplicate/past"

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
        print(collect_once())
