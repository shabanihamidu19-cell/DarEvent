# DarEvents — Automated Events Platform (Tanzania)

**Jukwaa la matukio linalojisimamia** — data inakusanywa otomatiki kwa Tavily + AI.

## Features

- ✅ **Automated collection** (Tavily + AI structured extraction)
- ✅ **Sponsored / Ads always first**
- ✅ **Anyone can post an event** (“Weka Tukio”) — free for now + duration selector (demo $1 / 2 days)
- ✅ Self-managing: dedup, expire old, max 300
- ✅ Polished Swahili frontend (stronger than local competitors)
- ✅ M-Pesa ready UI, filters, map, digest
- ✅ Ready for cron / Docker / any VPS


## Project Structure

```
darevents/
├── backend/
│   ├── main.py          # FastAPI app
│   ├── collector.py     # Tavily + AI collector
│   ├── config.py
│   ├── models.py
│   └── requirements.txt
├── frontend/
│   └── index.html       # Dynamic UI (fetches /api/events)
├── data/
│   ├── events.json      # Live events (auto-updated)
│   └── sponsored.json
├── scripts/
│   └── run_collector.sh
├── .env.example
└── README.md
```

## Quick Start (Local)

```bash
cd darevents/backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Seed demo data (works without keys)
python collector.py seed

# Run API + frontend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

## Production (Server)

1. Copy `.env.example` → `.env` and put your real keys:
   ```
   TAVILY_API_KEY=tvly-...
   OPENAI_API_KEY=...          # or xAI key
   AI_BASE_URL=https://api.x.ai/v1   # if using Grok
   AI_MODEL=grok-beta
   ```

2. Install & run:
   ```bash
   pip install -r backend/requirements.txt
   cd backend
   python collector.py seed          # first time
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

3. **Auto-collect every 6 hours** (cron example):
   ```cron
   0 */6 * * * cd /path/to/darevents/backend && /path/to/venv/bin/python collector.py >> /var/log/darevents-collect.log 2>&1
   ```

   Or enable APScheduler inside `main.py` (uncomment the scheduler block).

4. Trigger manually:
   ```bash
   curl -X POST http://localhost:8000/api/collect
   ```

## Sponsored Events (Ads first)

```bash
# Mark event as sponsored
curl -X POST "http://localhost:8000/api/sponsored/EVENT_ID?sponsored=true"
```

Sponsored events are **always sorted to the top**.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events` | List events (sponsored first) |
| GET | `/api/events/{id}` | Single event |
| POST | `/api/collect` | Trigger collection |
| POST | `/api/seed` | Seed demo data |
| POST | `/api/sponsored/{id}` | Mark/unmark sponsored |
| GET | `/api/health` | Health check |
| GET | `/docs` | Swagger UI |

## How Automation Works

1. **Tavily** searches multiple queries about Dar/Tanzania events.
2. **AI** (OpenAI / xAI / Claude) extracts clean structured JSON.
3. Deduplication (fuzzy title + date).
4. Old events dropped, max 300 kept.
5. Frontend polls `/api/events` every 10 min (or on load).

## Notes

- Without API keys the site still works with the seeded demo events.
- Put keys **only** in server `.env` — never in frontend or git.
- Ready for Railway, Render, DigitalOcean, VPS, or any Linux server.
