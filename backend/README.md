# SmartCityAI — Backend

FastAPI backend for the Multi-Agent AI Framework. Runs today on rule-based
stub predictions instead of trained models, so the full API contract, agent
reasoning, and orchestration logic can be built, tested, and connected to
the frontend before `models/*.pkl` exist.

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs (interactive): http://localhost:8000/docs

## Endpoints

| Method | Path                        | Matches frontend client.js call |
|--------|-----------------------------|----------------------------------|
| GET    | `/api/cities`                | `fetchCities()`                 |
| GET    | `/api/predictions/{cityId}`  | `fetchCityMetrics(cityId)`      |
| GET    | `/api/recommendations/{cityId}` | `fetchRecommendations(cityId)` |
| POST   | `/api/whatif/{cityId}`       | `runWhatIfScenario(cityId, scenario)` |

Response field names are camelCase (via Pydantic aliasing) so they match
`frontend/src/data/mockData.js` exactly — connecting the two is just
flipping `USE_MOCK = false` in `frontend/src/api/client.js`.

## Structure

```
app/
├── main.py                    # FastAPI app, CORS, router registration
├── routers/                   # one file per endpoint group
│   ├── cities.py
│   ├── predictions.py
│   ├── recommendations.py
│   └── whatif.py
├── schemas/models.py          # Pydantic request/response models
├── data/city_data.py          # seeded city metrics (mirrors frontend mock)
└── services/
    ├── models/stub_models.py  # placeholders for the 5 trained .pkl models
    ├── agents/                # water, urban, environment, industry,
    │                          # citizen, coordinator — rule-based for now
    ├── agent_pipeline.py       # runs all agents in order for a city
    └── optimizer.py           # what-if scenario math (stand-in for NSGA-II)
```

## What's real vs. what's a stub

**Real, and won't change when models are trained:**
- API routes, request/response schemas, CORS setup
- Agent architecture — five stakeholder agents + coordinator, each reading
  a shared `predictions` dict and returning `{agent, tone, text}`
- Orchestration flow: predictions → agents → coordinator → response

**Stubbed, and designed to be swapped in one place:**
- `services/models/stub_models.py` — each function stands in for one of the
  five trained models (`urban_growth.pkl`, `water_demand.pkl`, etc). Right
  now they compute derived stats from seeded data instead of running
  inference. To wire in a real model: load it once at import time, replace
  the function body with `MODEL.predict(...)`, and nothing in the agents or
  routers needs to change — they only ever call these functions.
- `services/optimizer.py` — currently applies fixed multipliers to mimic
  the frontend's mock math. This is where NSGA-II / MOEA goes once you have
  real objective functions to optimize against.

## Next steps toward the full spec

1. Extract real feature tables from the GEE exports (per the extraction
   script) and train the 5 models — save as `.pkl` in `models/`
2. Replace each function body in `stub_models.py` with real inference
3. Replace `optimizer.py`'s multiplier logic with NSGA-II (e.g. via `pymoo`)
4. Agent reasoning logic in `services/agents/*.py` can stay largely as-is —
   the thresholds may need tuning once real prediction distributions are
   known, but the pattern (read predictions → judge → return recommendation)
   doesn't change
