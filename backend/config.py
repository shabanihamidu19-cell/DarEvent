import os
from dotenv import load_dotenv

load_dotenv()

# API Keys (set these in .env on the server)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# AI provider (OpenAI-compatible). Priority: Groq → xAI → OpenAI
# Groq free tier: https://console.groq.com  (llama models, very cheap/fast)
_groq = os.getenv("GROQ_API_KEY", "")
_xai = os.getenv("XAI_API_KEY", "")
_openai = os.getenv("OPENAI_API_KEY", "")

if _groq:
    OPENAI_API_KEY = _groq
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
    AI_MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
elif _xai:
    OPENAI_API_KEY = _xai
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.x.ai/v1")
    AI_MODEL = os.getenv("AI_MODEL", "grok-3-mini")
else:
    OPENAI_API_KEY = _openai
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

# Paths
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
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

# How many events to keep max
MAX_EVENTS = 300
# Days ahead to collect
DAYS_AHEAD = 60
