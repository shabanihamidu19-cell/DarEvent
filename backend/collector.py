"""
DarEvents collector — Tavily + Groq
Frontend-compatible fields: cat, loc, emoji, desc, date_iso, likes
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
    MAX_RESULTS_PER_QUERY, CATEGORY_QUERIES, VENUE_QUERIES,
    LOCATION_QUERIES, EVENT_TYPE_QUERIES, SPORTS_QUERIES,
)

os.makedirs(DATA_DIR, exist_ok=True)

EMOJI = {
    "michezo": "⚽", "muziki": "🎵", "usiku": "🌃", "chakula": "🍽️",
    "technology": "💻", "tech": "💻", "sanaa": "🎨", "familia": "👨‍👩‍👧",
    "biashara": "💼", "elimu": "📚", "dini": "🙏", "afya": "🏥",
    "burudani": "🎉", "mikutano": "🤝", "maonesho": "🏛️", "community": "👥",
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


try:
    from rapidfuzz import fuzz

    def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
        if not a or not b:
            return False
        return fuzz.token_sort_ratio(a, b) / 100.0 >= threshold
except Exception:
    def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
        a_set = set((a or "").lower().split())
        b_set = set((b or "").lower().split())
        if not a_set or not b_set:
            return False
        return len(a_set & b_set) / max(len(a_set), len(b_set)) >= threshold


EXTRACTION_PROMPT = """Wewe ni AI ya DarEvents. Toa matukio HALISI ya Tanzania/Dar es Salaam kutoka maandishi.

Rudisha JSON array PEKEE (hakuna markdown). Kila object:
{{
  "title": "...",
  "category": "michezo|muziki|usiku|chakula|technology|sanaa|familia|biashara|elimu|dini|burudani|nyingine",
  "venue": "...",
  "location": "Dar es Salaam",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "price": "...",
  "description": "...",
  "source_url": "..."
}}

Rules: matukio ya baadaye tu; usibuni data; kama hakuna → []

TEXT:
{search_results}
"""


def tavily_search(query: str, max_results: int = 5) -> List[Dict]:
    if not TAVILY_API_KEY:
        print("TAVILY_API_KEY missing")
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        resp = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_raw_content=False,
        )
        return resp.get("results", [])
    except Exception as e:
        print(f"Tavily error: {e}")
        return []


def ai_extract_events(search_results_text: str) -> List[Dict]:
    if not OPENAI_API_KEY or not search_results_text.strip():
        print("AI key missing or empty text")
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=AI_BASE_URL)
        prompt = EXTRACTION_PROMPT.format(search_results=search_results_text[:8000])
        response = client.chat.completions.create(
            model=AI_MODEL or "llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Return pure JSON array only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
        )
        content = (response.choices[0].message.content or "").strip()
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        start = content.find("[")
        end = content.rfind("]")
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
        "sanaa": "Sanaa", "art": "Sanaa",
        "familia": "Familia", "family": "Familia",
        "biashara": "Biashara", "business": "Biashara",
        "elimu": "Warsha", "education": "Warsha", "warsha": "Warsha",
        "dini": "Dini", "burudani": "Usiku",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return cat.title() if cat else "Matukio"


def to_frontend(e: Dict) -> Dict:
    cat = normalize_category(e.get("category") or e.get("cat"))
    iso = e.get("date_iso") or normalize_date_to_iso(e.get("date") or "") or e.get("date")
    loc = e.get("loc") or e.get("venue") or e.get("location") or ""
    title = e.get("title") or ""
    now = datetime.now().isoformat()
    return {
        "id": e.get("id") or make_evt_id(),
        "emoji": e.get("emoji") or EMOJI.get((e.get("category") or "").lower(), "🎉"),
        "cat": cat,
        "title": title,
        "date": e.get("date") if not str(e.get("date", "")).startswith("20") else (iso or ""),
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


def generate_queries() -> List[str]:
    qs = []
    for bucket in (CATEGORY_QUERIES[:5], VENUE_QUERIES[:5], LOCATION_QUERIES[:4], EVENT_TYPE_QUERIES[:5], SPORTS_QUERIES[:4]):
        qs.extend(bucket)
    seen, out = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


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

    existing = load_events()
    existing = [to_frontend(e) for e in existing]
    by_title = {(e.get("title") or "").lower().strip(): e for e in existing}

    raw_blocks = []
    for q in generate_queries():
        print(f"  Search: {q[:60]}")
        results = tavily_search(q, max_results=MAX_RESULTS_PER_QUERY or 4)
        diag["hits"] += len(results)
        for r in results:
            snippet = (r.get("content") or r.get("raw_content") or "")[:1500]
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

    added = 0
    updated = 0
    now = datetime.now().isoformat()
    for item in extracted:
        title = (item.get("title") or "").strip()
        if len(title) < 5:
            continue
        iso = normalize_date_to_iso(item.get("date") or "")
        if iso and not is_future(iso):
            continue
        key = title.lower()
        if key in by_title:
            by_title[key]["last_seen"] = now
            updated += 1
            continue
        if any(fuzzy_match(title, e.get("title", "")) for e in by_title.values()):
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
        tip = "Tavily returned empty — check credits"
    elif diag["extracted"] == 0:
        tip = diag["ai_error"] or "AI returned 0 events — check Groq key/model/logs"
    elif added == 0:
        tip = "All candidates filtered as past or duplicate"

    result = {
        "added": added,
        "updated": updated,
        "total": len(final),
        "message": f"Collected {added} new, updated {updated}. Total: {len(final)}",
        "timestamp": now,
        "diag": diag,
        "tip": tip,
    }
    print(f"OK {result['message']} tip={tip}")
    return result


def seed_from_demo() -> int:
    demo = [
        {"id": "demo1", "emoji": "🎸", "cat": "Muziki", "title": "Kariakoo Groove Night — Vol. XIV", "date": "Ijumaa, Ag. 29", "date_iso": "2026-08-29", "time": "20:00", "loc": "Mlimani City Arena", "price": "TZS 15,000", "sponsored": False, "desc": "Usiku mkubwa wa muziki wa live Dar es Salaam.", "city": "Dar es Salaam"},
        {"id": "demo2", "emoji": "⚽", "cat": "Michezo", "title": "Simba SC vs Yanga SC — Dar Derby", "date": "Jumamosi, Ag. 30", "date_iso": "2026-08-30", "time": "15:00", "loc": "Benjamin Mkapa Stadium", "price": "TZS 5,000", "sponsored": True, "desc": "Mechi kati ya Simba SC na Young Africans.", "city": "Dar es Salaam"},
        {"id": "demo3", "emoji": "🌅", "cat": "Usiku", "title": "Sunset Rooftop — Coco Beach", "date": "Kila Ijumaa", "date_iso": "2026-08-29", "time": "18:00", "loc": "Coco Beach Hotel", "price": "TZS 10,000", "sponsored": False, "desc": "Rooftop na bahari.", "city": "Dar es Salaam"},
        {"id": "demo4", "emoji": "🍳", "cat": "Chakula", "title": "Dar Food Festival 2026", "date": "Ag. 29 – 31", "date_iso": "2026-08-29", "time": "10:00", "loc": "Mnazi Mmoja Grounds", "price": "Bure", "sponsored": True, "desc": "Tamasha la vyakula.", "city": "Dar es Salaam"},
        {"id": "demo5", "emoji": "💻", "cat": "Teknolojia", "title": "TechDar Bootcamp — AI & Web", "date": "Sept 5–7", "date_iso": "2026-09-05", "time": "09:00", "loc": "UDSM Innovation Hub", "price": "TZS 50,000", "sponsored": False, "desc": "Kozi ya AI na web.", "city": "Dar es Salaam"},
        {"id": "demo6", "emoji": "🎤", "cat": "Muziki", "title": "Bongo Flava Live — Uhuru Gardens", "date": "Jumapili, Ag. 31", "date_iso": "2026-08-31", "time": "17:00", "loc": "Uhuru Gardens", "price": "TZS 8,000", "sponsored": False, "desc": "Wasanii wa Bongo Flava.", "city": "Dar es Salaam"},
        {"id": "demo7", "emoji": "🏃", "cat": "Michezo", "title": "Dar es Salaam Marathon 2026", "date": "Sept 13", "date_iso": "2026-09-13", "time": "06:00", "loc": "Uhuru Monument", "price": "TZS 20,000", "sponsored": True, "desc": "Mbio za 42km.", "city": "Dar es Salaam"},
        {"id": "demo8", "emoji": "🎨", "cat": "Sanaa", "title": "Bagamoyo Arts Festival", "date": "Sept 19–21", "date_iso": "2026-09-19", "time": "Siku nzima", "loc": "Bagamoyo", "price": "TZS 3,000", "sponsored": False, "desc": "Sanaa za jadi na kisasa.", "city": "Dar es Salaam"},
    ]
    now = datetime.now().isoformat()
    for e in demo:
        e["last_seen"] = now
        e["created_at"] = now
        e["likes"] = 0
        e["dislikes"] = 0
    save_events(demo)
    print(f"Seeded {len(demo)} demos")
    return len(demo)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_from_demo()
    else:
        collect_once()
