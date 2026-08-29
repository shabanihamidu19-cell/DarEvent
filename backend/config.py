import os
from dotenv import load_dotenv

load_dotenv()

def _env(name: str, default: str = "") -> str:
    """Read env; treat empty string as missing (Render often leaves blanks)."""
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip()

# API Keys (Groq + Tavily only)
TAVILY_API_KEY = _env("TAVILY_API_KEY")
GROQ_API_KEY = _env("GROQ_API_KEY")

# Default: Groq is the only supported AI provider by default for this deployment.
if GROQ_API_KEY:
    # We map the Groq key into the variable names used elsewhere in the code so
    # existing code that expects OPENAI_API_KEY / AI_BASE_URL works with Groq.
    OPENAI_API_KEY = GROQ_API_KEY
    AI_BASE_URL = _env("AI_BASE_URL", "https://api.groq.com/openai/v1")
    AI_MODEL = _env("AI_MODEL", "llama-3.3-70b-versatile")
else:
    # No default fallback — require GROQ_API_KEY to be present.
    OPENAI_API_KEY = ""
    AI_BASE_URL = ""
    AI_MODEL = ""

# Paths
DATA_DIR = _env("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
SPONSORED_FILE = os.path.join(DATA_DIR, "sponsored.json")

# Collection settings (kept compact here; expand in future commits)
CITIES = ["Dar es Salaam", "Arusha", "Mwanza", "Zanzibar", "Dodoma", "Mbeya"]
SEARCH_QUERIES = [
    "upcoming events Dar es Salaam Tanzania this week next month",
    "matukio yanayokuja Dar es Salaam 2026",
    "concerts festivals sports Dar es Salaam upcoming",
    "Eventbrite Dar es Salaam events",
    "Super Dome Dar es Salaam events",
    "live music nightlife Dar es Salaam this weekend",
]

MAX_EVENTS = int(_env("MAX_EVENTS", "300"))
DAYS_AHEAD = int(_env("DAYS_AHEAD", "60"))
MAX_RESULTS_PER_QUERY = int(_env("MAX_RESULTS_PER_QUERY", "5"))
