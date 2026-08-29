"""
Professional DarEvents collector
- Multidimensional query generator (category, venue, location, event-type, sports)
- Tavily for discovery
- Groq (mapped to OPENAI_API_KEY + AI_BASE_URL) for extraction using the Swahili EXTRACTION_PROMPT
- Deduplication (rapidfuzz if available)
- EVT-XXXXXXXX id generation
- Confidence scoring
- Save canonical data/events.json (max MAX_EVENTS)
- No demo seeding
"""

import json
import os
import re
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from dateutil import parser as date_parser

from config import (
    TAVILY_API_KEY, OPENAI_API_KEY, AI_BASE_URL, AI_MODEL,
    EVENTS_FILE, SPONSORED_FILE, DATA_DIR, MAX_EVENTS, DAYS_AHEAD, MAX_RESULTS_PER_QUERY,
    CATEGORY_QUERIES, VENUE_QUERIES, LOCATION_QUERIES, EVENT_TYPE_QUERIES, SPORTS_QUERIES
)
from models import Event

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
    # Sponsored first, then newest (created_at desc)
    def sort_key(e):
        return (not e.get("sponsored", False), -(int(datetime.fromisoformat(e.get("created_at") or datetime.now().isoformat()).timestamp())))
    events.sort(key=sort_key)
    _save_json(EVENTS_FILE, events)


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


# fuzzy match
try:
    from rapidfuzz import fuzz

    def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
        if not a or not b:
            return False
        score = fuzz.token_sort_ratio(a, b) / 100.0
        return score >= threshold
except Exception:
    def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return False
        inter = len(a_set & b_set)
        return inter / max(len(a_set), len(b_set)) >= threshold


# EXTRACTION_PROMPT (Swahili) — use user's provided prompt exactly with placeholder
EXTRACTION_PROMPT = '''
Wewe ni AI Event Intelligence Engine ya DarEvents.

Kazi yako ni kuchambua search results na kutambua MATUKIO HALISI yanayoweza kuhudhuriwa na watu Tanzania, hasa Dar es Salaam.

MUHIMU:

CATEGORY SI sawa na EVENT au VENUE.

CATEGORY ni broad event classification kama:
michezo
technology
muziki
dini
biashara
elimu
sanaa
chakula
usiku
familia
afya
burudani
mikutano
maonesho
community
nyingine

EVENT ni tukio lenyewe.

VENUE ni mahali tukio litakapofanyika.

LOCATION ni eneo/mji.

Mfano:

"Simba SC vs Yanga SC"
→ title/event

"michezo"
→ category

"Benjamin Mkapa Stadium"
→ venue

"Mlimani City"
→ venue

"Mlimani Park"
→ venue

Usiwahi kuweka venue, team, artist, event name au location kama main category.

MATUKIO YAWE YA KWELI TU.

Usibuni:
- tarehe
- muda
- bei
- venue
- source
- event
- URL

Kama information haipo, tumia null.

Tukio lazima liwe upcoming.
Ondoa matukio yaliyopita.

Kwa kila tukio toa JSON:

{
  "title": "...",
  "category": "...",
  "subcategory": "...",
  "venue": "...",
  "location": "Dar es Salaam",
  "address": null,
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "price": "...",
  "description": "...",
  "source_url": "...",
  "source_name": "...",
  "confidence": "high|medium|low"
}

RULES:

1. Return JSON array ONLY.
2. No markdown.
3. No explanation.
4. Return [] if there is no real event.
5. Do not invent information.
6. Every event must have evidence in the search result.
7. Prefer official event pages, organizers, venues, ticketing platforms and reputable sources.
8. Do not duplicate the same event from multiple sources.
9. If several sources describe the same event, merge them.
10. Preserve the real venue name.
11. Preserve the real event title.
12. Categorize correctly.
13. Mlimani City and Mlimani Park are VENUES/LOCATIONS, never categories.
14. Simba SC, Yanga SC and other teams are entities/events, never categories.
15. Concert, conference, match, seminar etc. can be subcategories/event types, but not automatically main categories.

SEARCH RESULTS:
{search_results}
'''


def tavily_search(query: str, max_results: int = 5) -> List[Dict]:
    if not TAVILY_API_KEY:
        print("⚠️  TAVILY_API_KEY missing — skipping search")
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        resp = client.search(query=query, search_depth="advanced", max_results=max_results, include_raw_content=True)
        return resp.get("results", [])
    except Exception as e:
        print(f"Tavily error: {e}")
        return []


def ai_extract_events(search_results_text: str) -> List[Dict]:
    if not OPENAI_API_KEY or not search_results_text.strip():
        print("⚠️ AI key missing or empty search — skipping extraction")
        return []
    try:
        # Map to openai-like client; Groq provides OpenAI-compatible endpoints in config
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=AI_BASE_URL)
        prompt = EXTRACTION_PROMPT.format(search_results=search_results_text)
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You extract structured event data as pure JSON array only."},
                {"role": "user", "content": prompt[:12000]}
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"AI extraction error: {e}")
        return []


def score_source_quality(source_url: Optional[str], title: Optional[str], text_snippet: Optional[str]) -> str:
    if not source_url:
        return "low"
    u = source_url.lower()
    # Simple heuristics
    high_indicators = ["ticket", "eventbrite", "tickethub", "official", "org", "stadium", "mkapa", "mlimani", "ticketmaster"]
    medium_indicators = ["facebook.com", "instagram.com", "twitter.com", "youtube.com", "news", "daily", "theguardian", "voa"]
    if any(k in u for k in high_indicators):
        return "high"
    if any(k in u for k in medium_indicators):
        return "medium"
    # look at snippet
    if text_snippet and len(text_snippet) > 200 and ("ticket" in text_snippet.lower() or "venue" in text_snippet.lower()):
        return "medium"
    return "low"


def normalize_category(cat: Optional[str]) -> str:
    if not cat:
        return "nyingine"
    c = cat.strip().lower()
    mapping = {
        "michezo": "michezo",
        "sports": "michezo",
        "technology": "technology",
        "tech": "technology",
        "muziki": "muziki",
        "music": "muziki",
        "dini": "dini",
        "religious": "dini",
        "biashara": "biashara",
        "business": "biashara",
        "elimu": "elimu",
        "education": "elimu",
        "sanaa": "sanaa",
        "art": "sanaa",
        "chakula": "chakula",
        "food": "chakula",
        "usiku": "usiku",
        "nightlife": "usiku",
        "familia": "familia",
        "family": "familia",
        "afya": "afya",
        "health": "afya",
        "burudani": "burudani",
        "mikutano": "mikutano",
        "maonesho": "maonesho",
        "community": "community",
        "other": "nyingine",
        "nyingine": "nyingine",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return "nyingine"


def dedupe_and_merge(existing: List[Dict], candidates: List[Dict]) -> List[Dict]:
    now = datetime.now().isoformat()
    existing_by_key = { (e.get('title','').lower().strip(), e.get('date','')): e for e in existing }
    # We'll attempt fuzzy merge by title+date+venue
    for c in candidates:
        title = (c.get('title') or '').strip()
        date = c.get('date')
        venue = c.get('venue') or ''
        iso = normalize_date_to_iso(date) if date else c.get('date')
        if iso and not is_future(iso):
            continue
        merged = None
        for e in existing:
            if fuzzy_match(title, e.get('title','')) and (not iso or not e.get('date') or iso == e.get('date')):
                merged = e
                break
        if merged:
            # merge fields conservatively
            merged['last_seen'] = now
            merged['description'] = merged.get('description') or c.get('description')
            merged['price'] = merged.get('price') or c.get('price')
            # preserve highest confidence
            conf_order = {'low':0,'medium':1,'high':2}
            if conf_order.get(c.get('confidence','low'),0) > conf_order.get(merged.get('confidence','low'),0):
                merged['confidence'] = c.get('confidence')
                merged['source_url'] = c.get('source_url') or merged.get('source_url')
            # ensure venue/location present
            merged['venue'] = merged.get('venue') or c.get('venue')
            merged['location'] = merged.get('location') or c.get('location')
        else:
            # New event
            eid = make_evt_id()
            event = {
                'id': eid,
                'title': title,
                'category': normalize_category(c.get('category')),
                'subcategory': c.get('subcategory'),
                'venue': c.get('venue'),
                'location': c.get('location') or 'Dar es Salaam',
                'address': c.get('address'),
                'date': normalize_date_to_iso(c.get('date')) or c.get('date'),
                'time': c.get('time'),
                'price': c.get('price'),
                'description': c.get('description'),
                'source_url': c.get('source_url'),
                'source_name': c.get('source_name'),
                'image_url': c.get('image_url'),
                'confidence': c.get('confidence','low'),
                'sponsored': bool(c.get('sponsored', False)),
                'created_at': now,
                'last_seen': now,
            }
            existing.append(event)
    # cleanup expired
    final = [e for e in existing if is_future(e.get('date'))]
    # limit
    final = final[:MAX_EVENTS]
    return final


def generate_queries() -> List[str]:
    qs = []
    qs.extend(CATEGORY_QUERIES)
    qs.extend(VENUE_QUERIES)
    qs.extend(LOCATION_QUERIES)
    qs.extend(EVENT_TYPE_QUERIES)
    qs.extend(SPORTS_QUERIES)
    # Remove duplicates and preserve order
    seen = set()
    out = []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def collect_once() -> Dict[str, Any]:
    print(f"🚀 Starting collection @ {datetime.now().isoformat()}")
    existing = load_events()
    queries = generate_queries()
    raw_blocks = []
    maxr = MAX_RESULTS_PER_QUERY or 5
    for q in queries:
        print(f"Searching: {q}")
        results = tavily_search(q, max_results=maxr)
        for r in results:
            url = r.get('url')
            title = r.get('title')
            snippet = (r.get('raw_content') or r.get('content') or '')[:3000]
            raw_blocks.append(f"URL: {url}\nTitle: {title}\n{snippet}")
    combined = "\n\n---\n\n".join(raw_blocks)
    extracted = ai_extract_events(combined)
    print(f"AI extracted {len(extracted)} candidates")
    # map extracted to canonical candidate structure
    candidates = []
    for e in extracted:
        cand = {
            'title': e.get('title'),
            'category': e.get('category'),
            'subcategory': e.get('subcategory'),
            'venue': e.get('venue'),
            'location': e.get('location'),
            'address': e.get('address'),
            'date': e.get('date'),
            'time': e.get('time'),
            'price': e.get('price'),
            'description': e.get('description'),
            'source_url': e.get('source_url'),
            'source_name': e.get('source_name'),
            'image_url': e.get('image_url'),
            'confidence': e.get('confidence') or score_source_quality(e.get('source_url'), e.get('title'), ''),
            'sponsored': False,
        }
        candidates.append(cand)
    final = dedupe_and_merge(existing, candidates)
    save_events(final)
    added = len(final) - len(existing) if len(final) >= len(existing) else 0
    result = {
        'added': added,
        'updated': 0,
        'total': len(final),
        'message': f'Collected {added} new. Total live: {len(final)}',
        'timestamp': datetime.now().isoformat()
    }
    print(f"✅ {result['message']}")
    return result


if __name__ == '__main__':
    # Standalone run: perform one collection cycle
    collect_once()
