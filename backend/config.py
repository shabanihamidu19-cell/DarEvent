import os
from dotenv import load_dotenv

load_dotenv()

def _env(name: str, default: str = "") -> str:
    """Read env; treat empty string as missing (Render often leaves blanks)."""
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip()

# API Keys
TAVILY_API_KEY = _env("TAVILY_API_KEY")

# AI provider priority: Groq → xAI → OpenAI
_groq = _env("GROQ_API_KEY")
_xai = _env("XAI_API_KEY")
_openai = _env("OPENAI_API_KEY")

if _groq:
    OPENAI_API_KEY = _groq
    AI_BASE_URL = _env("AI_BASE_URL", "https://api.groq.com/openai/v1")
    AI_MODEL = _env("AI_MODEL", "llama-3.3-70b-versatile")
elif _xai:
    OPENAI_API_KEY = _xai
    AI_BASE_URL = _env("AI_BASE_URL", "https://api.x.ai/v1")
    AI_MODEL = _env("AI_MODEL", "grok-3-mini")
else:
    OPENAI_API_KEY = _openai
    AI_BASE_URL = _env("AI_BASE_URL", "https://api.openai.com/v1")
    AI_MODEL = _env("AI_MODEL", "gpt-4o-mini")

# Paths
DATA_DIR = _env("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
SPONSORED_FILE = os.path.join(DATA_DIR, "sponsored.json")

# Collection settings
CITIES = ["Dar es Salaam", "Arusha", "Mwanza", "Zanzibar", "Dodoma", "Mbeya"]
SEARCH_QUERIES = [
    "upcoming events Dar es Salaam Tanzania this week next month",
    "matukio yanayokuja Dar es Salaam 2026",
    "concerts festivals sports Dar es Salaam upcoming",
    "Eventbrite Dar es Salaam events",
    "Super Dome Dar es Salaam events",
    "live music nightlife Dar es Salaam this weekend",
]

MAX_EVENTS = 300
DAYS_AHEAD = 60
