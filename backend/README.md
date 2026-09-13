# SmartCityAI — Backend

FastAPI backend serving four trained models, a deterministic rules engine, and a
LangGraph multi-agent layer interpreted by Groq.

See the [project README](../README.md) for installation, configuration and the full API
reference, and [docs/architecture.md](../docs/architecture.md) for the design.

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Docs at http://localhost:8000/docs · readiness at http://localhost:8000/api/models/status

## Layout

```
app/
├── main.py                 app, CORS, error handlers, startup warm-up
├── core/                   config, errors, grid, logging, building guidelines
├── routers/                system, water, urban, flood, microplastics, building, agents
├── schemas/                requests.py, responses.py
├── services/
│   ├── models/             registry, feature_store, explain, one module per model
│   └── building_planner/   nasa_power, site_analyzer, recommendation_engine
└── agents/                 graph, state, schemas, llm, and the five agents
scripts/                    download, preprocess, features, evaluation
tests/                      207 offline tests + 8 opt-in live integration tests
```

Nothing lives in `main.py` beyond app wiring; every path resolves through
`app/core/config.py`.

## Tests

```bash
pytest                                            # 207 tests, offline, no Groq key
SMARTCITY_LIVE_TESTS=1 pytest tests/test_integration_live.py    # real Groq + NASA POWER
```

## Evaluation

```bash
python -m scripts.evaluation.evaluate_models --model all          # M1/M3 reproduction
python -m scripts.evaluation.evaluate_urban_expansion --out build/  # M2 forward validation
python -m scripts.features.build_urban_expansion_features --out build/ --with-target
```
