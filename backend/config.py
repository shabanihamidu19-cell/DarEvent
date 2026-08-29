import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip()

# API Keys (Groq + Tavily preferred)
TAVILY_API_KEY = _env("TAVILY_API_KEY")
GROQ_API_KEY = _env("GROQ_API_KEY")

# Default: Groq is the primary AI provider for this deployment.
if GROQ_API_KEY:
    OPENAI_API_KEY = GROQ_API_KEY
    AI_BASE_URL = _env("AI_BASE_URL", "https://api.groq.com/openai/v1")
    AI_MODEL = _env("AI_MODEL", "llama-3.3-70b-versatile")
else:
    OPENAI_API_KEY = ""
    AI_BASE_URL = ""
    AI_MODEL = ""

# Paths
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _env("DATA_DIR", str(ROOT / "data"))
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
SPONSORED_FILE = os.path.join(DATA_DIR, "sponsored.json")

# Limits & rotation
MAX_EVENTS = int(_env("MAX_EVENTS", "300"))
DAYS_AHEAD = int(_env("DAYS_AHEAD", "60"))
MAX_RESULTS_PER_QUERY = int(_env("MAX_RESULTS_PER_QUERY", "5"))
SEARCH_ROTATION = int(_env("SEARCH_ROTATION", "3"))

# Cities (focus)
CITIES = ["Dar es Salaam"]

# CATEGORY searches (main categories in Swahili & English hints)
CATEGORY_QUERIES = [
    "michezo Dar es Salaam events Tanzania 2026",
    "technology tech events Dar es Salaam Tanzania 2026",
    "muziki concerts Dar es Salaam Tanzania 2026",
    "dini religious events Dar es Salaam Tanzania 2026",
    "biashara business networking Dar es Salaam 2026",
    "elimu education seminars Dar es Salaam 2026",
    "sanaa art exhibitions Dar es Salaam 2026",
    "chakula food festivals Dar es Salaam 2026",
    "usiku nightlife Dar es Salaam 2026",
    "familia family events Dar es Salaam 2026",
    "afya health events Dar es Salaam 2026",
    "burudani entertainment Dar es Salaam 2026",
    "mikutano meetups Dar es Salaam 2026",
    "maonesho trade fairs Dar es Salaam 2026",
    "community community events Dar es Salaam 2026",
    "nyingine other events Dar es Salaam 2026",
]

# VENUE-first discovery
VENUE_QUERIES = [
    "Mlimani City events",
    "Mlimani Park events",
    "Benjamin Mkapa Stadium events",
    "National Stadium Dar es Salaam events",
    "Julius Nyerere International Convention Centre events",
    "Warehouse Dar es Salaam events",
    "The Slipway Dar es Salaam events",
    "Masaki Dar es Salaam events",
    "Coco Beach events Dar es Salaam",
    "Posta Dar es Salaam events",
    "Kariakoo Dar es Salaam events",
    "Mbezi Dar es Salaam events",
    "Sinza Dar es Salaam events",
    "Mikocheni Dar es Salaam events",
    "Oysterbay Dar es Salaam events",
    "Upanga Dar es Salaam events",
]

# LOCATION-first discovery
LOCATION_QUERIES = [
    "events Masaki Dar es Salaam",
    "events Mikocheni Dar es Salaam",
    "events Oysterbay Dar es Salaam",
    "events Sinza Dar es Salaam",
    "events Kariakoo Dar es Salaam",
    "events Upanga Dar es Salaam",
    "events Posta Dar es Salaam",
    "events Mbezi Dar es Salaam",
    "events Kinondoni Dar es Salaam",
    "events Ilala Dar es Salaam",
    "events Temeke Dar es Salaam",
    "events Ubungo Dar es Salaam",
    "events Kigamboni Dar es Salaam",
]

# EVENT-TYPE discovery
EVENT_TYPE_QUERIES = [
    "concerts Dar es Salaam",
    "live music Dar es Salaam",
    "football matches Dar es Salaam",
    "sports events Dar es Salaam",
    "technology conferences Dar es Salaam",
    "tech meetups Dar es Salaam",
    "hackathons Dar es Salaam",
    "seminars Dar es Salaam",
    "workshops Dar es Salaam",
    "business conferences Dar es Salaam",
    "religious conferences Dar es Salaam",
    "church events Dar es Salaam",
    "Islamic events Dar es Salaam",
    "food festivals Dar es Salaam",
    "art exhibitions Dar es Salaam",
    "family events Dar es Salaam",
    "comedy shows Dar es Salaam",
    "nightlife events Dar es Salaam",
    "trade fairs Dar es Salaam",
    "exhibitions Dar es Salaam",
]

# SPORTS discovery
SPORTS_QUERIES = [
    "Simba SC upcoming matches Tanzania",
    "Yanga SC upcoming matches Tanzania",
    "Azam FC upcoming matches Tanzania",
    "Tanzania Premier League fixtures",
    "CAF matches Dar es Salaam",
    "football matches Dar es Salaam",
    "basketball events Dar es Salaam",
    "boxing events Dar es Salaam",
    "athletics events Tanzania",
]

# Combined default (used by older code paths)
SEARCH_QUERIES = CATEGORY_QUERIES[:6] + VENUE_QUERIES[:6] + LOCATION_QUERIES[:6]
