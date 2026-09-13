# Workflows

Data-flow and architecture documentation for SmartCityAI.

| Document | Covers |
|---|---|
| [system-architecture.md](system-architecture.md) | System architecture at four levels: context, container, component, deployment. Plus the request lifecycle, the LangGraph execution model, and the failure-mode map. |
| [city-planner-dataflow.md](city-planner-dataflow.md) | **Process 1 — City Planner.** Grid cell to final recommendation: three models, three agents, the Coordinator. |
| [building-planner-dataflow.md](building-planner-dataflow.md) | **Process 2 — Sustainable Building Planner.** Plot inputs to costed, cited recommendations via NASA POWER and the rules engine. |
| [water-microplastics-dataflow.md](water-microplastics-dataflow.md) | **Process 3 — Water & Microplastics.** City-wide surface-water monitoring, and the polarimetric screening pipeline. |
| [data-contracts.md](data-contracts.md) | Every payload shape in one place, as a reference. |

---

## How to read these

Diagrams are [Mermaid](https://mermaid.js.org/), which GitHub renders inline. Each
process document follows the same structure:

1. **Level 0** — a context diagram: the process as one box, with its external actors.
2. **Level 1** — the decomposition into stages.
3. **Stage-by-stage detail** — for each stage: what enters, what leaves, in what form,
   which component does the work, and what it can never do.
4. **Sequence diagram** — the same flow over time, showing what runs in parallel.
5. **Failure modes** — what happens at each stage when something is unavailable.

### Notation

Every data store and flow is labelled with the **kind** of information it carries,
because the distinction is the point of this architecture:

| Marker | Meaning |
|---|---|
| **M** measured | A satellite observation or meteorological record. Ground truth. |
| **P** predicted | Output of a trained ML model. Carries uncertainty. |
| **R** rule-derived | Deterministic calculation from cited parameters. Reproducible. |
| **I** interpreted | LLM-written prose. Explains the above; never produces a number. |

Diagram shapes:

```
[ Process ]        a transformation step
(( Store ))        a dataset or model artifact at rest
[( Database )]     a cached, in-memory table
{ Decision }       a branch
```

---

## The payloads are real

Every JSON example in these documents was captured from a live run of the system
against grid cell **`Agra_86833145`** (Agra, Uttar Pradesh, 27.1762°N 78.0052°E) on the
1 km analysis grid — not hand-written. Feature lists were read from the fitted
estimators themselves, so they match the artifacts exactly.

To regenerate any of them:

```bash
cd backend
python -c "from app.services.models import flood_risk; import json; \
print(json.dumps(flood_risk.predict('Agra_86833145'), indent=2))"
```

---

## The one rule that shapes all of this

> LLM agents **interpret** predictive model outputs; they do not replace the predictive
> models.

In flow terms: **P** and **R** data is produced upstream and passes through the agent
layer unchanged. The LLM reads it and emits only **I** data. There is no flow anywhere in
these diagrams from an LLM back into a prediction — and the code makes that structural
rather than conventional, which the architecture document details.
