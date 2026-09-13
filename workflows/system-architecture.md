# System Architecture

Four levels of increasing detail, then the runtime concerns: request lifecycle,
concurrency, caching and failure handling.

---

## Level 1 — System context

Who and what the system talks to.

```mermaid
graph TB
    citizen([Citizen<br/>plot-level decisions])
    planner([Urban planner<br/>city-level decisions])
    evaluator([Academic evaluator<br/>metrics and limitations])

    subgraph system[SmartCityAI]
        app[Multi-Agent Decision<br/>Support System]
    end

    groq[[Groq API<br/>openai/gpt-oss-120b<br/>interpretation only]]
    nasa[[NASA POWER API<br/>solar + meteorology<br/>no API key]]
    osm[[OpenStreetMap<br/>basemap tiles]]

    artifacts[(Trained artifacts<br/>4 models, ~6.5 GB)]
    layers[(Geospatial layers<br/>108,642 cells x 45 cities)]

    citizen -->|plot details| app
    planner -->|city, grid cell| app
    evaluator -->|metrics queries| app

    app -->|"evidence (M/P/R)"| groq
    groq -->|"narrative (I)"| app
    app -->|lat, lon| nasa
    nasa -->|"climatology (M)"| app
    osm -->|tiles| app

    artifacts -.->|loaded once at startup| app
    layers -.->|cached in memory| app

    app -->|"recommendation + evidence + limitations"| citizen
    app -->|"suitability, flood, water maps"| planner
    app -->|"holdout metrics, SHAP, per-city tables"| evaluator

    classDef ext fill:#1B383C,stroke:#4CC9C0,color:#EAF4F2
    classDef store fill:#142B2E,stroke:#C08B3F,color:#EAF4F2
    class groq,nasa,osm ext
    class artifacts,layers store
```

**External dependencies and what happens without them**

| Dependency | Required? | Without it |
|---|---|---|
| Groq | No | Agents emit deterministic summaries, labelled `deterministic_fallback` |
| NASA POWER | For the Building Planner | `502 upstream_unavailable`; affected rules skip and say why. **No fallback values.** |
| OpenStreetMap | No | Map renders grid cells on a blank ground |
| Model artifacts | Yes, per model | `503 model_unavailable` naming the file and config key |

---

## Level 2 — Containers

```mermaid
graph TB
    subgraph browser[Browser]
        react["React SPA<br/>Vite · Tailwind · Leaflet<br/>:5173"]
    end

    subgraph server[Python process]
        api["FastAPI<br/>:8000<br/>33 endpoints"]
        models["Model services<br/>singleton registry"]
        rules["Rules engine<br/>Building Planner"]
        agents["LangGraph<br/>5 agents"]
    end

    subgraph disk[Filesystem]
        m1[(Model 1<br/>XGBoost pipeline)]
        m2[(Model 2<br/>LightGBM)]
        m3[(Model 3<br/>Random Forest)]
        m4[(Model 4<br/>ResNet18)]
        csv[(Feature tables<br/>+ grid registry)]
    end

    groq[[Groq]]
    nasa[[NASA POWER]]

    react <-->|JSON over HTTP| api
    api --> models
    api --> rules
    api --> agents
    agents --> models
    agents --> rules
    rules --> models
    rules --> nasa
    agents <--> groq
    models --> m1 & m2 & m3 & m4
    models --> csv

    classDef ext fill:#1B383C,stroke:#4CC9C0,color:#EAF4F2
    classDef store fill:#142B2E,stroke:#C08B3F,color:#EAF4F2
    class groq,nasa ext
    class m1,m2,m3,m4,csv store
```

Everything runs in **one Python process**. The models are tree ensembles plus one
ResNet18 on CPU, so no model server, GPU or message broker is needed — it runs on a
laptop.

---

## Level 3 — Components

```mermaid
graph TB
    subgraph routers["app/routers/ — HTTP boundary"]
        r_sys[system.py<br/>health, status, grid]
        r_w[water.py]
        r_u[urban.py]
        r_f[flood.py]
        r_m[microplastics.py]
        r_b[building.py]
        r_a[agents.py]
    end

    subgraph core["app/core/ — cross-cutting"]
        cfg[config.py<br/>every path, env-driven]
        grid[grid.py<br/>1 km grid, EPSG:4326]
        err[errors.py<br/>exception to HTTP envelope]
        log[logging_config.py<br/>request-id correlation]
        guide[building_guidelines.py<br/>cited parameters]
    end

    subgraph svc_models["app/services/models/"]
        reg[registry.py<br/>lru_cache singletons]
        fs[feature_store.py<br/>feature assembly]
        exp[explain.py<br/>SHAP]
        sw[surface_water.py]
        ue[urban_expansion.py]
        fr[flood_risk.py]
        mp[microplastic.py]
    end

    subgraph svc_bp["app/services/building_planner/"]
        np_[nasa_power.py]
        sa[site_analyzer.py]
        re_[recommendation_engine.py]
    end

    subgraph ag["app/agents/"]
        graph_[graph.py<br/>StateGraph]
        state[state.py<br/>CityState]
        sch[schemas.py<br/>structured output]
        llm[llm.py<br/>Groq + guardrails]
        a_w[water_agent]
        a_u[urban_agent]
        a_f[flood_agent]
        a_b[building_agent]
        a_c[coordinator_agent]
    end

    r_w --> sw
    r_u --> ue
    r_f --> fr
    r_m --> mp
    r_b --> sa & re_
    r_a --> graph_
    r_sys --> reg & grid

    sw & ue & fr --> fs & reg & exp
    mp --> reg
    fs --> cfg
    reg --> cfg
    sa --> sw & ue & fr & np_
    re_ --> guide
    graph_ --> a_w & a_u & a_f & a_b & a_c
    a_w --> sw
    a_u --> ue
    a_f --> fr
    a_b --> sa & re_
    a_w & a_u & a_f & a_b & a_c --> llm & sch
    graph_ --> state
```

### Component responsibilities

| Component | Owns | Must never |
|---|---|---|
| `core/config.py` | Every filesystem path and key | Be bypassed by a hard-coded path |
| `core/grid.py` | The 1 km grid; id lookup, nearest-cell, GeoJSON | Transform coordinates between CRSs |
| `models/registry.py` | Loading artifacts once | Reload per request |
| `models/feature_store.py` | Feature-table assembly and row lookup | Impute a missing value |
| `models/*.py` | Inference, thresholds, banding | Explain itself in prose |
| `building_planner/nasa_power.py` | External meteorology | Substitute fallback values |
| `building_planner/recommendation_engine.py` | Which rules fire, and every number | Consult an LLM |
| `agents/llm.py` | Groq calls, guardrails, degradation | Let an invalid response through |
| `agents/coordinator_agent.py` | Conflict detection, baseline verdict | Let the LLM loosen a verdict |

---

## Level 4 — Deployment

```mermaid
graph LR
    subgraph dev[Developer laptop]
        vite["vite dev<br/>:5173"]
        uvicorn["uvicorn --reload<br/>:8000"]
        fs_[(models/ ~6.5 GB<br/>not in git)]
    end

    subgraph net[Internet]
        g[[Groq API]]
        n[[NASA POWER]]
        t[[OSM tiles]]
    end

    vite -->|CORS-restricted| uvicorn
    uvicorn --> fs_
    uvicorn -->|HTTPS| g
    uvicorn -->|HTTPS| n
    vite -->|HTTPS| t
```

**Resource profile, measured**

| Aspect | Value |
|---|---|
| Startup (model warm-up) | ~5 s |
| Resident memory | ~1.5 GB, dominated by the three feature tables |
| Single-cell prediction | < 100 ms per model, including SHAP |
| Whole-city layer (2,571 cells) | ~1 s, vectorised |
| Full 5-agent pipeline | 20–25 s, dominated by Groq round trips |
| Artifacts on disk | ~6.5 GB |

---

## Request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as RequestIdMiddleware
    participant V as Pydantic schema
    participant G as core/grid
    participant FS as feature_store
    participant R as registry
    participant M as Model
    participant X as explain (SHAP)
    participant EH as Error handler

    C->>MW: POST /api/flood-risk
    MW->>MW: assign request id, log
    MW->>V: validate body
    alt invalid
        V-->>EH: ValidationError
        EH-->>C: 422 invalid_input
    end
    V->>G: resolve grid_id / snap lat,lon
    alt not on the grid
        G-->>EH: GridNotFoundError
        EH-->>C: 404 grid_not_found + city list
    end
    G->>FS: row for grid_id
    FS->>FS: cached table lookup
    FS->>R: model singleton
    alt artifact missing
        R-->>EH: ModelUnavailableError
        EH-->>C: 503 + file + config key
    end
    R->>M: predict_proba(X)
    M->>M: apply tuned threshold, band
    M->>X: SHAP attribution
    X-->>M: top features (or null)
    M-->>MW: result
    MW-->>C: 200 + X-Request-ID
```

Every log line carries the request id via a `ContextVar`, so one request is traceable
end to end: request → inference → agent → coordinator → response.

---

## The LangGraph execution model

```mermaid
stateDiagram-v2
    [*] --> validate_input
    validate_input --> water_agent
    validate_input --> urban_agent
    validate_input --> flood_agent

    state "concurrent superstep" as par {
        water_agent
        urban_agent
        flood_agent
    }

    water_agent --> building_gate
    urban_agent --> building_gate
    flood_agent --> building_gate

    building_gate --> building_agent: building_params supplied
    building_gate --> coordinator: otherwise
    building_agent --> coordinator
    coordinator --> [*]
```

**Why the barrier works.** Three edges into `building_gate` mean LangGraph will not
execute it until all three inbound nodes complete. No merge reducer is needed because
each agent writes only its own `*_result` and `*_analysis` keys. The two keys several
nodes append to — `errors` and `trace` — carry `operator.add` reducers.

**The concurrency is measured, not assumed.**
`tests/test_agents.py::TestGraph::test_domain_agents_run_concurrently` instruments the
three agents and asserts their execution windows overlap, that more than one thread is
used, and that wall time is below the serial sum: **5.92 s against 14.18 s of summed
work, across three threads.**

### State

```python
class CityState(TypedDict, total=False):
    location: dict
    building_params: dict | None
    options: dict

    water_result: dict        # P — model output, never mutated after writing
    urban_result: dict        # P
    flood_result: dict        # P
    building_result: dict     # R — rules output

    water_analysis: dict      # I — agent interpretation
    urban_analysis: dict      # I
    flood_analysis: dict      # I
    building_analysis: dict   # I

    coordinator_result: dict  # I, over a deterministic skeleton

    errors: Annotated[list[dict], operator.add]
    trace: Annotated[list[str], operator.add]
```

The `*_result` / `*_analysis` split is the architectural boundary. A caller can always
read the raw model number beside the interpretation of it and confirm they agree.

---

## Caching

```mermaid
graph LR
    subgraph proc[Process lifetime]
        a["registry<br/>4 model artifacts"]
        b["feature_store<br/>3 tables x 108,642 rows"]
        c["grid registry<br/>108,642 cells"]
        d["SHAP explainers<br/>one per model"]
        e["compiled LangGraph"]
    end
    subgraph bounded[Bounded caches]
        f["NASA POWER<br/>lru_cache 256<br/>keyed on a 0.5 deg grid"]
        g["ChatGroq clients<br/>lru_cache 4"]
    end
```

NASA POWER responses are cached on a 0.5° grid because that is the API's own
reanalysis resolution — neighbouring requests would return the same cell anyway.

---

## Failure-mode map

```mermaid
graph TB
    req[Request] --> q1{Input valid?}
    q1 -->|no| e1[422 invalid_input<br/>field-level detail]
    q1 -->|yes| q2{On the 1 km grid?}
    q2 -->|no| e2[404 grid_not_found<br/>+ covered cities]
    q2 -->|yes| q3{Artifact loaded?}
    q3 -->|no| e3[503 model_unavailable<br/>+ file + config key]
    q3 -->|yes| q4{Dataset present?}
    q4 -->|no| e4[503 dataset_unavailable]
    q4 -->|yes| pred[Prediction P]
    pred --> q5{SHAP available?}
    q5 -->|no| n1[attribution: null<br/>never approximated]
    q5 -->|yes| n2[attribution included]
    n1 & n2 --> q6{NASA POWER reachable?}
    q6 -->|no| e5[502 upstream_unavailable<br/>dependent rules skip and say why]
    q6 -->|yes| q7{Groq reachable?}
    q7 -->|no| n3[deterministic_fallback<br/>+ reason in note]
    q7 -->|yes| n4[LLM narrative I]
    n3 & n4 --> ok[200 + evidence + gaps]

    classDef err fill:#2A1512,stroke:#E2583E,color:#F0836D
    classDef degraded fill:#2A2312,stroke:#E3A93C,color:#F0C571
    class e1,e2,e3,e4,e5 err
    class n1,n3 degraded
```

**The invariant across every branch:** nothing is ever silently replaced with a
plausible-looking value. A degraded response says which part degraded and why.

---

## Where the governing rule is enforced

| Enforcement | Location |
|---|---|
| Agent schemas have no numeric prediction field | `agents/schemas.py` |
| Model output and interpretation are separate state keys | `agents/state.py` |
| Evidence is assembled from model output in code, not by the LLM | `agents/base.py` |
| Conflict detection and baseline verdict are deterministic | `agents/coordinator_agent.py` |
| The LLM may tighten a verdict, never loosen it | `agents/coordinator_agent.py` |
| Guardrails prepended to every prompt | `agents/llm.py` |
| Responses are schema-validated before entering the graph | `agents/llm.py` |

The verdict guard, concretely — verdicts are ordered by permissiveness, and if the LLM
returns one more permissive than the deterministic baseline, the baseline is kept and
the attempted override is recorded in `note`:

```python
_PERMISSIVENESS = {
    "proceed": 0,
    "proceed_with_conditions": 1,
    "proceed_with_strong_mitigation": 2,
    "discourage": 3,
    "insufficient_evidence": 4,
}
```

Covered by `test_llm_cannot_loosen_the_deterministic_verdict`.
