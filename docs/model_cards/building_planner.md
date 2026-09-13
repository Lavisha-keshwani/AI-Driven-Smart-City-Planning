# Module Card — Sustainable Building Planner

## Purpose

Help a citizen or small developer design a more sustainable building on a specific plot,
using that site's real environmental conditions.

## Disclaimer

> **This is an advisory sustainability planning tool, not a certified structural
> engineering design or construction blueprint.** Figures are planning-stage estimates.
> Guideline references are cited as design references only: this tool **does not verify
> compliance** with the Eco-Niwas Samhita, the National Building Code, or any local
> by-law. Engage a licensed structural engineer and architect, and confirm all
> requirements with your local authority, before construction.

Returned in every response and served by `GET /api/building-planner/guidelines`.

## What this module is

**Deterministic rules, arithmetic and cited guideline parameters. No ML model, and no
LLM in the decision path.**

Whether a recommendation fires, and every number in it, is decided in
`app/services/building_planner/recommendation_engine.py`. The same inputs always produce
the same advice, and every figure can be traced to a formula and a source.

The Building Sustainability Agent adds a plain-language explanation afterwards. It is
explicitly forbidden from overriding a rule, changing a priority, or adding a
recommendation the rules did not produce.

## Inputs

| Input | Notes |
|---|---|
| `lat`, `lon` | Site location; snapped to the nearest 1 km grid cell |
| `building_type` | `residential` \| `office` \| `commercial` |
| `plot_size_sqm` | Plot area |
| `floors` | Number of floors |
| `occupants` | Expected occupancy |
| `budget_inr` | Optional |
| `roof_area_sqm` | Optional; derived from plot size when absent |
| `requirements` | Optional free text, echoed for context |

## Environmental evidence used

| Source | Provides | Kind |
|---|---|---|
| Model 3 | flood probability and risk band | model prediction |
| Model 1 | surface-water classification and observed GSW record | prediction + measurement |
| Model 2 | urban expansion suitability | model prediction |
| NASA POWER | solar irradiance, temperature, humidity, rainfall | measurement |
| SRTM / GHSL | terrain, built-up fraction | measurement |

The response keeps these separated as `model_predictions`, `measured` and `derived`, so a
reader always knows which is which.

> **Reading the temperature figures.** NASA POWER's climatology reports `T2M_MAX` and
> `T2M_MIN` as the most extreme temperatures ever observed at a location, not typical
> daily highs and lows. The planner and the UI therefore label them "record high" and
> "record low", and the passive-cooling trigger is set against that extreme (40 °C)
> rather than against an average, which a 32 °C threshold would have made almost
> universally true across India.

### NASA POWER service

`app/services/building_planner/nasa_power.py`

```python
get_nasa_power_data(latitude, longitude, start_date, end_date)   # daily series
get_climatology(latitude, longitude)                             # monthly climatology
```

Parameters retrieved: `ALLSKY_SFC_SW_DWN` (solar), `T2M`, `T2M_MAX`, `T2M_MIN`,
`PRECTOTCORR` (precipitation), `RH2M` (humidity), `WS2M` (wind).

- **No API key required** — the endpoints used are open.
- Handles timeout, connection failure, HTTP 429 rate limiting, HTTP 422 invalid
  coordinates, malformed JSON, and empty parameter blocks.
- **Never substitutes fallback climate values.** An outage raises
  `502 upstream_unavailable`; the planner then skips the rules that needed that data and
  says which, rather than advising from an invented rainfall figure.
- The `-999` missing-data sentinel is dropped, never treated as zero.
- Annual rainfall is computed by weighting each month's mm/day rate by that month's real
  length, not by a flat 30- or 365-day factor.
- Responses are cached on a 0.5° grid, matching NASA POWER's own resolution.

## Rules

Each rule emits `recommendation`, `priority`, `reason`, `triggering_data`, `calculations`
and `guideline_basis`.

| Rule | Fires when | Key calculation |
|---|---|---|
| **Rainwater harvesting** | annual rainfall ≥ 400 mm | `yield_L = roof_area_m² × (rainfall_mm / 1000) × runoff_coefficient × 1000` |
| **Rooftop solar** | irradiance ≥ 3.5 kWh/m²/day and capacity ≥ 1 kW | `generation_kWh_day = capacity_kW × irradiance × performance_ratio`; capacity = min(roof-limited, demand-matched) |
| **Passive cooling** | mean temp ≥ 28 °C, or record high ≥ 40 °C | openable area = floor_area × 0.125; strategy branches on humidity |
| **Flood resilience** | risk band MODERATE or HIGH | plinth raise 0.45 m (moderate) or 0.75 m (high) |
| **Green / permeable area** | always | `permeable_m² = (plot − plot × ground_coverage) × permeable_share`; share rises from 0.30 to 0.60 where flood risk is elevated |
| **Water conservation** | always | `saving_L_day = occupants × lpcd × (fixture_saving + greywater_share)` |
| **Water-body setback** | site within or adjacent to a water-body cell | indicative 30 m, flagged as indicative only |
| **Urban context** | suitability available | advisory, keyed to GREEN / YELLOW / RED |

### Rules that do not fire say why

A rule whose triggering evidence is missing does **not** fire, and is reported in
`skipped_rules` with the reason. Two cases matter especially:

- **Rainfall unavailable** → rainwater harvesting is skipped, citing the NASA POWER
  outage, rather than estimated from a regional average.
- **Flood model unavailable** → flood measures are skipped with: *"This is not a finding
  that the site is safe."*
- **Flood risk LOW** → elevated-risk measures are skipped, noting that the model's
  moderate recall means LOW is *"no evidence of flood exposure rather than proof of
  safety."*

### Solar sizing is capped by demand

Sizing purely to available roof area over-specifies systems. Capacity is therefore the
lesser of roof-limited and demand-matched, and the binding constraint is reported:

| Case | Roof-limited | Demand-matched | Recommended | Limited by |
|---|---|---|---|---|
| 5-person home, 250 m² plot | 8.2 kW | 3.9 kW | **3.9 kW** | estimated demand |
| 4-floor office, 800 m² plot | 26.4 kW | 127.4 kW | **26.4 kW** | roof area |

## Guideline parameters and their provenance

All parameters live in `app/core/building_guidelines.py`, each tagged with an origin:

| Origin | Meaning |
|---|---|
| `guideline` | A published reference figure, cited with publisher |
| `project_assumption` | A modelling assumption this project adopts; **no regulatory weight** |

### Sources cited

| Key | Document | Publisher |
|---|---|---|
| `eco_niwas_samhita` | Eco-Niwas Samhita (ECBC-Residential) | Bureau of Energy Efficiency (BEE) |
| `cpheeo` | Manual on Water Supply and Treatment | CPHEEO |
| `nbc_2016` | National Building Code of India 2016 | Bureau of Indian Standards |
| `mnre` | Rooftop solar programme guidance | Ministry of New and Renewable Energy |

### Selected parameters

| Parameter | Value | Origin | Source |
|---|---|---|---|
| Domestic water demand | 135 L/person/day | guideline | CPHEEO |
| Office water demand | 45 L/person/day | guideline | CPHEEO |
| Roof runoff coefficient | 0.85 | guideline | NBC 2016 |
| Openable area / floor area | 0.125 | guideline | **Eco-Niwas Samhita** |
| Record-high cooling trigger | 40 °C | project_assumption | — |
| Min visible light transmittance | 0.27 | guideline | **Eco-Niwas Samhita** |
| Cool-roof solar reflectance | 0.70 | guideline | **Eco-Niwas Samhita** |
| Rooftop area per kW | 10 m²/kW | guideline | MNRE |
| PV performance ratio | 0.75 | guideline | MNRE |
| Plinth raise (moderate / high flood) | 0.45 m / 0.75 m | guideline | NBC 2016 |
| Water-body setback | 30 m (indicative) | guideline | NBC 2016 |
| Roof share of plot | 0.55 | project_assumption | — |
| Usable roof share for PV | 0.60 | project_assumption | — |
| Ground coverage | 0.55 | project_assumption | — |
| Storage days of demand | 20 | project_assumption | — |

### On Eco-Niwas Samhita specifically

The Eco-Niwas Samhita parameters above are cited as **design references**. This tool does
**not** verify compliance with them. Eco-Niwas Samhita compliance depends on envelope
U-values, window assembly specifications, and climate-zone-specific RETV calculations that
require actual architectural drawings — none of which this tool has. No regulatory
requirement is invented, and no compliance claim is made.

Local municipal by-laws and state building regulations always govern, and are frequently
stricter than the indicative figures here (statutory water-body setbacks in particular are
often far larger than 30 m).

## Limitations

- **Advisory only.** No structural, geotechnical or hydraulic engineering.
- **No compliance verification** against any code or by-law.
- **Plot geometry is assumed, not surveyed.** Roof and footprint areas are derived from
  plot size unless supplied; real geometry, setbacks and orientation constraints will
  differ.
- **Cost and savings estimates are indicative** and omit local price variation, labour,
  and tariff structure.
- **1 km resolution on the environmental inputs.** Flood and water evidence describes the
  surrounding cell, not the plot. Site-specific survey is required for design.
- **Model limitations propagate.** The flood input inherits Model 3's moderate recall and
  per-city variance; see its model card.
- **Indian context.** Guideline parameters and demand benchmarks are Indian; they do not
  transfer without substitution.
- **Occupancy-based demand.** Water and energy estimates scale with declared occupants and
  will diverge from actual behaviour.

## Intended use

Early-stage sustainability planning conversation for a specific plot, and a structured
brief for a professional. **Not** a construction document, a compliance certificate, or a
substitute for a licensed engineer and architect.

## API

```
POST /api/building-planner                  full assessment and recommendations
GET  /api/building-planner/site?lat=&lon=   site conditions only
GET  /api/building-planner/guidelines       the full ruleset with provenance
POST /api/building-planner/nasa-power       direct NASA POWER query
```
