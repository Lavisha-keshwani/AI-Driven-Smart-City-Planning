# Architecture

## The governing principle

> **LLM agents interpret predictive model outputs; they do not replace the predictive
> models.**

Every probability, score and classification in this system is produced by a trained
model or a deterministic rule. The language model explains those numbers, reconciles
them across domains, and says what they do not establish. It never computes one.

This is enforced structurally, not by instruction alone:

| Enforcement | Where |
|---|---|
| Agent output schemas have no numeric prediction field | `app/agents/schemas.py` |
| Model output and agent interpretation occupy separate state keys | `app/agents/state.py` |
| Evidence is assembled from model output in code, never by the LLM | `app/agents/base.py` |
| Conflict detection and the headline verdict are deterministic | `app/agents/coordinator_agent.py` |
| The LLM may tighten the verdict, never loosen it | `app/agents/coordinator_agent.py` |
| Guardrails are prepended to every prompt | `app/agents/llm.py` |

## Layers

```
                              REACT FRONTEND
                                    │
                                    ▼
                                 FASTAPI
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
     MODEL 1                     MODEL 2                     MODEL 3
  Surface Water              Urban Expansion                Flood Risk
   (XGBoost)                   (LightGBM)                (Random Forest)
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                                    ▼
                   SUSTAINABLE BUILDING PLANNER
                  (deterministic rules + NASA POWER)
                                    │
                                    ▼
                                LANGGRAPH
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   Water Agent               Urban Agent                 Flood Agent
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                            Building Agent
                                    │
                                    ▼
                              COORDINATOR
                                    │
                                    ▼
                               GROQ LLM
                                    │
                                    ▼
                    FINAL EXPLANATION + TRADE-OFFS
                          + RECOMMENDATIONS
```

Responsibilities are strictly separated:

| Layer | Role | Never does |
|---|---|---|
| ML models | prediction | explain itself in prose |
| Rules engine | deterministic calculation | guess a missing input |
| LangGraph | orchestration, state, parallelism | decide anything |
| Groq LLM | interpretation, reasoning, narrative | compute a prediction |
| Coordinator | synthesis, trade-offs | alter an underlying prediction |
| FastAPI | transport, validation, errors | hide a failure |

## The common spatial framework

Every environmental model is indexed by the same `grid_id` on a **1 km analysis grid**
covering 45 Indian cities (108,642 cells), in **EPSG:4326**.

```
grid_id | city | state | lat | lon | is_core | geometry
```

`app/core/grid.py` owns the registry. No coordinate transformation happens anywhere in
the backend, so there is no opportunity to mix coordinate systems. Cell geometry is
reconstructed as the lat/lon envelope of a 1 km cell about the exported centroid, with
the longitude half-extent scaled by `cos(latitude)` so cells stay ~1 km wide at every
latitude. Coordinates submitted by a caller are snapped to the nearest cell by
great-circle distance, and the snap distance is returned; a point more than 25 km from
any cell is rejected rather than silently attached to a distant city.

## Request flow

```
HTTP request
  │ RequestIdMiddleware assigns a request id; every log line carries it
  ▼
Pydantic request schema validates the input
  │
  ▼
app/core/grid.py resolves grid_id, or snaps lat/lon to the nearest cell
  │
  ▼
app/services/models/feature_store.py assembles the feature row
  │   feature ORDER comes from the fitted estimator itself
  ▼
app/services/models/registry.py serves the cached singleton model
  │
  ▼
model.predict_proba -> probability
  │
  ▼
threshold and banding applied from the training run's tuned values
  │
  ▼
app/services/models/explain.py computes SHAP attributions
  │
  ▼
agent wraps the result as evidence and asks the LLM to interpret it
  │
  ▼
coordinator reconciles the domains
  │
  ▼
JSON response: *_result (model output) + *_analysis (interpretation)
```

## The LangGraph graph

```
                        START
                          │
                          ▼
                   validate_input          resolve onto the 1 km grid
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     water_agent     urban_agent     flood_agent      ← one concurrent superstep
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                   building_gate           barrier: waits for all three
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
       building_agent            coordinator          conditional on building_params
              │                       │
              └───────────┬───────────┘
                          ▼
                         END
```

**The parallelism is real, and tested.** Three edges out of `validate_input` place the
domain agents in a single superstep; three edges into `building_gate` make it a barrier
LangGraph will not execute until all three complete.
`tests/test_agents.py::TestGraph::test_domain_agents_run_concurrently` asserts that the
agents' execution windows overlap, that they occupy more than one thread, and that wall
time is below the serial sum.

This needs no merge reducer because each agent writes only its own `*_result` and
`*_analysis` keys. The two keys several nodes append to — `errors` and `trace` — carry
`operator.add` reducers in `CityState`.

## Shared state

```python
class CityState(TypedDict, total=False):
    location: dict
    building_params: dict | None
    options: dict

    # Model and rules output — written by inference code, never mutated after
    water_result: dict
    urban_result: dict
    flood_result: dict
    building_result: dict

    # Agent interpretations — one key per agent, so writes never collide
    water_analysis: dict
    urban_analysis: dict
    flood_analysis: dict
    building_analysis: dict

    coordinator_result: dict

    errors: Annotated[list[dict], operator.add]
    trace: Annotated[list[str], operator.add]
```

The `*_result` / `*_analysis` split is the project's core architectural boundary. An
API consumer can always read the raw model number and the interpretation of it side by
side, and confirm they agree.

## Coordinator trade-off reasoning

Detection and narration are deliberately separated, so a genuine conflict is never
missed because the LLM overlooked it.

**1. Deterministic conflict detection** (`detect_conflicts`):

| Conflict | Condition | Severity |
|---|---|---|
| `growth_pressure_vs_flood_exposure` | GREEN/YELLOW suitability + HIGH/MODERATE flood | high / moderate |
| `growth_pressure_vs_water_body` | GREEN/YELLOW suitability on a surface-water cell | high |
| `growth_pressure_vs_water_availability` | favourable suitability + unreliable water | moderate |
| `water_body_with_flood_exposure` | surface-water cell + elevated flood risk | high |
| `low_suitability_despite_low_hazard` | RED suitability + LOW flood | low |

**2. Deterministic baseline verdict** (`_baseline_recommendation`):

| Evidence | Verdict |
|---|---|
| Fewer than two domain models available | `insufficient_evidence` |
| Cell is a surface-water body | `discourage` (ecological hard stop) |
| Suitability RED | `discourage`, whatever else is favourable |
| Suitability GREEN + flood HIGH | `proceed_with_strong_mitigation` |
| Suitability YELLOW + flood HIGH | `discourage` |
| Flood MODERATE | `proceed_with_conditions` |
| Suitability GREEN + flood LOW, no unresolved conflict | `proceed` |
| Suitability YELLOW + flood LOW | `proceed_with_conditions` |

**3. LLM narration**, constrained in one direction only. Verdicts are ordered by
permissiveness; if the LLM returns one more permissive than the baseline, the baseline
is kept and the attempted override is recorded in `note`. Additional caution is allowed.
Any deterministically detected conflict absent from the LLM's trade-offs is appended.

The ecological guarantee follows from this: a favourable urban score can never suppress
a flood or water finding, because the flood and water signals are in the baseline rule
and in the appended conflicts regardless of what the LLM writes.

## Graceful degradation

Nothing in this system substitutes a plausible-looking value for a missing input.

| Failure | Behaviour |
|---|---|
| Model artifact missing | 503 `model_unavailable`, naming the file and the config key |
| Feature dataset missing | 503 `dataset_unavailable`, naming the expected file |
| Grid cell unknown | 404 `grid_not_found`, with the valid city list |
| Coordinates outside coverage | 404, with the distance and the covered cities |
| NASA POWER unreachable | 502 `upstream_unavailable`; **no fallback climate values** |
| Groq unavailable or rate-limited | deterministic summary, `source: "deterministic_fallback"` plus the reason |
| SHAP unavailable | `feature_attribution: null`, never an approximation |
| One domain model fails mid-pipeline | that domain becomes a stated evidence gap; the Coordinator reports `insufficient_evidence` if too little remains |
| Invalid image upload | 400 `invalid_input` with remediation guidance |

Every degraded response says so. A reader can always tell which parts of a payload an
LLM touched, and which evidence was absent.

## Backend layout

```
backend/
├── app/
│   ├── main.py                      FastAPI app, CORS, error handlers, lifespan
│   ├── core/
│   │   ├── config.py                every path and key, env-driven
│   │   ├── errors.py                domain exceptions -> HTTP envelope
│   │   ├── grid.py                  the 1 km analysis grid
│   │   ├── logging_config.py        request-id correlation
│   │   └── building_guidelines.py   cited guideline parameters
│   ├── routers/                     system, water, urban, flood, microplastics,
│   │                                building, agents
│   ├── schemas/                     requests.py, responses.py
│   ├── services/
│   │   ├── models/
│   │   │   ├── registry.py          singleton model loading
│   │   │   ├── feature_store.py     feature table assembly
│   │   │   ├── explain.py           SHAP attributions
│   │   │   ├── surface_water.py     Model 1
│   │   │   ├── urban_expansion.py   Model 2
│   │   │   ├── flood_risk.py        Model 3
│   │   │   └── microplastic.py      Microplastic screening
│   │   └── building_planner/
│   │       ├── nasa_power.py        NASA POWER service layer
│   │       ├── site_analyzer.py     evidence assembly for a site
│   │       └── recommendation_engine.py   deterministic rules
│   └── agents/
│       ├── graph.py                 the LangGraph StateGraph
│       ├── state.py                 CityState
│       ├── schemas.py               structured output contracts
│       ├── llm.py                   Groq client + guardrails
│       ├── base.py                  shared agent machinery
│       ├── water_agent.py
│       ├── urban_agent.py
│       ├── flood_agent.py
│       ├── building_agent.py
│       └── coordinator_agent.py
├── scripts/
│   ├── download/                    source layer provenance
│   ├── features/                    feature table assembly
│   └── evaluation/                  validation of the shipped artifacts
└── tests/
```

## Frontend

```
frontend/src/
├── api/client.js        the only module that talks to the backend
├── hooks/useAsync.js    request state; aborts on dependency change and unmount
├── lib/domain.js        class -> colour/label/wording, one source of truth
├── components/
│   ├── ui/              Card, Badge, Meter, Disclosure, ErrorState, form controls
│   ├── map/             GridMap (Leaflet + GeoJSON), LayerPicker, MapLegend
│   ├── cell/            per-model result cards
│   ├── ai/              coordinator verdict, trade-offs, agent narratives
│   ├── technical/       SHAP, metrics, per-city performance, raw payload
│   └── microplastic/    three-channel upload
└── pages/               CityPlanner, WaterMicroplastics, BuildingPlanner
```

The interface mirrors the backend's separation of evidence. Each result leads with
plain language and the measured evidence behind it; the model name, SHAP
attributions, validation metrics, per-city performance and the raw API payload sit
behind disclosures. Every AI narrative states whether Groq wrote it or whether it
was produced deterministically, and why. `lib/domain.js` is the single place that
maps a class to a colour and a phrase, so the map, legend and panels cannot drift
apart.

The map renders GeoJSON straight from the layer endpoints — one polygon per
analysed 1 km cell — so what a user clicks is the same cell the models scored.

## Performance

| Concern | Measure |
|---|---|
| Model loading | `lru_cache` singletons, warmed at startup |
| Feature tables | loaded once per process and cached (108,642 rows each) |
| SHAP explainers | constructed once per model and cached |
| NASA POWER | `lru_cache` on a 0.5° grid, matching the API's own resolution |
| Domain agents | run concurrently, so three LLM calls cost one round trip |
| Coordinator prompt | a digest of signals and conclusions, not the raw payloads |
| Batch prediction | vectorised across a whole city in one `predict_proba` call |

Runs comfortably on a laptop: the models are tree ensembles and one ResNet18 on CPU.

## Observability

`RequestIdMiddleware` assigns each request a short id, propagated via a `ContextVar`
into every log line and returned as `X-Request-ID`. One request can be traced end to
end: request → model inference → agent → coordinator → response. The pipeline's own
`trace` list records each stage in the response body.

API keys are never logged. `llm_status()` reports only `api_key_configured: bool`, and
error envelopes carry file *names*, never filesystem paths.
