# Data Contracts

Every payload shape in one place. Captured from a live run against grid cell
**`Agra_86833145`** — not hand-written.

Kind markers: **M** measured · **P** predicted · **R** rule-derived · **I** interpreted.

---

## The spatial framework

Every model is indexed by the same `grid_id`, so all layers describe identical squares.

| Property | Value |
|---|---|
| Cell size | 1 km |
| CRS | EPSG:4326 (geographic degrees) |
| Coverage | 45 Indian cities, 108,642 cells |
| City extent | 25 km radius disc around the centre |
| Cells per city | 2,089 (Thiruvananthapuram) to 2,956 (Srinagar), 2,414 mean |
| Source | `city_grid_1km_metadata.csv` (`SmartCityAI_city_boundaries` export) |

```
grid_id | city | state | lat | lon | is_core
```

No coordinate transformation happens anywhere in the backend, so coordinate systems
cannot be silently mixed.

---

## Grid cell record — **M**

```json
{
  "grid_id": "Agra_86833145",
  "city": "Agra",
  "state": "Uttar Pradesh",
  "lat": 27.176176692751397,
  "lon": 78.00520769655562,
  "is_core": 0,
  "distance_km": 0.205
}
```

`distance_km` appears only when resolved from coordinates.

---

## Model inputs

| Model | Features | Source table | Order recovered from |
|---|---|---|---|
| 1 · Surface Water | 28 | `final_grid_dataset_water.csv` (pre-merged) | `feature_names_in_` |
| 2 · Urban Expansion | 13 | rebuilt from GHSL + Open Buildings + SRTM + CHIRPS | `booster_.feature_name()` |
| 3 · Flood Risk | 38 | `final_grid_dataset.csv` (pre-merged) | `feature_names_in_` |

All are a single-row `pandas` DataFrame. **Missing values stay NaN** — never imputed.

---

## Model 1 output — **P** + **M**

```json
{
  "model": "Surface Water Monitoring",
  "model_key": "model1_surface_water",
  "algorithm": "xgboost",
  "grid_id": "Agra_86833145", "city": "Agra", "state": "Uttar Pradesh",
  "lat": 27.176177, "lon": 78.005208,

  "water_body_probability": 0.1551,
  "is_water_body": false,
  "classification": "non_water_body",
  "decision_threshold": 0.5169,

  "observed": {
    "water_occurrence_pct": 0.0, "water_fraction": 0.0,
    "water_seasonality_months": 0.0, "water_recurrence_pct": 75.0,
    "water_max_extent_pct": 0.0, "water_max_extent_fraction": 0.0
  },
  "water_body_status": {
    "status": "none",
    "seasonality_months": 0.0, "occurrence_pct": 0.0,
    "inter_annual_reliability": "high", "recurrence_pct": 75.0,
    "water_body_threshold_pct": 25.0,
    "basis": "Global Surface Water (JRC GSW) observations — measured, not predicted"
  },
  "incomplete_features": [],
  "feature_attribution": [ ... ]
}
```

| Field | Kind | Notes |
|---|---|---|
| `water_body_probability` | **P** | Model output |
| `classification` | **P** | `probability >= decision_threshold` |
| `observed.*` | **M** | JRC GSW satellite record |
| `water_body_status` | **R** | Deterministic reading of the measured layer |

`status` ∈ `permanent` (≥75%) · `seasonal` (≥25%) · `ephemeral` (>0) · `none` · `unknown`

---

## Model 2 output — **P** + **M** + **R**

```json
{
  "model": "Urban Expansion Suitability",
  "algorithm": "LightGBM",

  "suitability_score": 0.6324,
  "suitability_class": "YELLOW",
  "class_meaning": "Conditional — requires further consideration",
  "confidence": 0.6983,
  "class_probabilities": { "RED": 0.1449, "YELLOW": 0.6983, "GREEN": 0.1568 },
  "score_definition": "P(YELLOW)*0.5 + P(GREEN)*1.0, bounded to [0, 1]",
  "classification_rule": "argmax of class probabilities (as validated)",

  "observed": {
    "built_fraction_t0": 0.305, "built_fraction_t1": 0.339,
    "built_growth_t0_t1": 0.034, "t0_year": 2000, "t1_year": 2020,
    "elevation_m": 170.081, "slope_deg": 4.747,
    "depression_index_m": -0.14, "rainfall_annual_mm": 483.61,
    "building_count_total": 11.395, "building_presence_mean": 0.285
  },
  "constraints": [],
  "incomplete_features": [],
  "feature_attribution": null
}
```

| Class | Meaning | Growth tercile |
|---|---|---|
| GREEN | Suitable — preferred growth direction | highest |
| YELLOW | Conditional — requires further consideration | middle |
| RED | Avoid — unsuitable or high-risk | lowest |

**The score measures propensity for expansion, learned from where growth historically
occurred (2000→2020). It is not a judgement that expansion there is desirable.**

`constraints` entries are **R**, each carrying its measurement:

```json
{
  "constraint": "high_rainfall",
  "severity": "moderate",
  "reason": "Annual rainfall of 1826 mm demands drainage capacity sized for intense events.",
  "measured": { "rainfall_annual_mm": 1825.66 }
}
```

---

## Model 3 output — **P** + **M** + **R**

```json
{
  "model": "Urban Flood Risk",
  "algorithm": "random_forest",

  "flood_probability": 0.4261,
  "risk_level": "MODERATE",
  "risk_meaning": "Moderate flood susceptibility — resilience measures required",
  "flood_predicted": false,
  "decision_threshold": 0.5718,
  "risk_bands": { "high_at_or_above": 0.6, "moderate_at_or_above": 0.3 },

  "observed": {
    "historical_flood_label": 0,
    "historical_flood_events": 0.0, "historical_flood_fraction": 0.0,
    "flood_record_source": "Global_Flood_Database",
    "flood_record_period": "2000_2018",
    "elevation_m": 170.081, "slope_deg": 4.747,
    "water_occurrence_pct": 0.0,
    "rainfall_annual_mm_mean": 483.61, "rainfall_annual_mm_max": 626.72,
    "built_fraction_2020": 0.339
  },
  "risk_drivers": [],
  "feature_attribution": [ ... ]
}
```

| Band | Condition |
|---|---|
| HIGH | p ≥ 0.60 |
| MODERATE | 0.30 ≤ p < 0.60 |
| LOW | p < 0.30 |

Bands bracket the tuned operating threshold (0.5718), so MODERATE spans the region where
the model is least certain. Both edges are configurable.

`risk_drivers` are **R**, computed from the measured layers:

```json
{
  "driver": "low_elevation",
  "reason": "Elevation of 3 m leaves little gravity drainage head.",
  "measured": { "elevation_m": 3.07 }
}
```

Drivers: `low_elevation` · `flat_terrain` · `local_depression` ·
`surface_water_presence` · `high_rainfall_exposure` · `impervious_surface` ·
`rapid_urbanisation`

---

## SHAP attribution — **R** over **P**

```json
[
  { "feature": "ndvi", "importance": 0.264, "direction": "positive", "shap_value": 1.263 },
  { "feature": "ndbi", "importance": 0.164, "direction": "negative", "shap_value": -0.783 }
]
```

| Value | Meaning |
|---|---|
| `importance` | Share of the row's total absolute attribution |
| `direction` | `positive` pushed towards the class of interest |
| `null` (whole field) | SHAP unavailable — **never approximated** |

One-hot columns are folded back onto their source feature, so callers see `state`, not
`state_Kerala`.

---

## Agent result — **I**

```python
class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    summary: str
    findings: list[str]
    risks: list[str]
    recommendations: list[str]
    uncertainty: str
    interpretation_confidence: Literal["high", "medium", "low"]
```

**No numeric field exists**, so an agent cannot return a competing prediction.
`interpretation_confidence` is the agent's confidence in its own reading, never a model
probability.

Wrapped for transport:

```json
{
  "domain": "flood",
  "agent": "Flood / Resilience Agent",
  "model": "Urban Flood Risk",
  "result": { ...AgentResult... },
  "evidence": { ...what the LLM was shown... },
  "source": "llm",
  "llm_model": "openai/gpt-oss-120b",
  "note": null
}
```

`source` is `llm` or `deterministic_fallback`; when it falls back, `note` carries why.

---

## Coordinator signals — **P** condensed

```json
{
  "water": { "available": true, "is_water_body": false,
             "water_body_probability": 0.1551, "status": "none",
             "inter_annual_reliability": "high" },
  "urban": { "available": true, "suitability_class": "YELLOW",
             "suitability_score": 0.6324, "confidence": 0.6983, "constraints": [] },
  "flood": { "available": true, "flood_probability": 0.4261,
             "risk_level": "MODERATE", "drivers": [] },
  "building": { "available": false, "recommendation_count": 0,
                "high_priority_count": null }
}
```

## Detected conflict — **R**

```json
{
  "type": "growth_pressure_vs_flood_exposure",
  "severity": "moderate",
  "between": ["urban", "flood"],
  "description": "The area shows YELLOW expansion suitability while flood risk is MODERATE (probability 43%).",
  "implication": "Growth pressure and flood exposure coincide, which is how flood-exposed development happens. Expansion should not proceed unrestricted."
}
```

| Type | Fires when | Severity |
|---|---|---|
| `growth_pressure_vs_flood_exposure` | GREEN/YELLOW + HIGH/MODERATE flood | high / moderate |
| `growth_pressure_vs_water_body` | GREEN/YELLOW on a water-body cell | high |
| `growth_pressure_vs_water_availability` | favourable + unreliable water | moderate |
| `water_body_with_flood_exposure` | water body + elevated flood | high |
| `low_suitability_despite_low_hazard` | RED + LOW flood | low |

## Coordinator result — **I** over an **R** skeleton

```python
class CoordinatorResult(BaseModel):
    overall_recommendation: Literal["proceed", "proceed_with_conditions",
        "proceed_with_strong_mitigation", "discourage", "insufficient_evidence"]
    headline: str
    rationale: str
    trade_offs: list[TradeOff]      # between: list[str], tension: str, resolution: str
    conditions: list[str]
    priority_actions: list[str]
    evidence_gaps: list[str]
```

The verdict is decided by deterministic rules; the LLM may make it **more** cautious,
never less.

---

## NASA POWER climatology — **M**

```json
{
  "source": "NASA POWER",
  "endpoint": "temporal/climatology/point",
  "requested": { "latitude": 27.1767, "longitude": 78.0072 },
  "resolved_grid_point": { "latitude": 27.0, "longitude": 78.0 },
  "solar_kwh_m2_day": 4.878,
  "temperature_c": 26.54,
  "temperature_max_c": 49.01,
  "temperature_min_c": 0.03,
  "humidity_pct": 44.09,
  "wind_speed_m_s": 1.92,
  "rainfall_annual_mm": 626.4,
  "monthly_rainfall_mm": { "JAN": 0.62, "...": "..." },
  "wettest_month": "JUL",
  "monsoon_concentration": 0.849
}
```

**`temperature_max_c` and `temperature_min_c` are observed extremes**, not typical daily
highs and lows — 49.01 °C is Agra's record. Labelled "record high"/"record low" in the UI.

Annual rainfall is the sum of monthly mm/day rates weighted by each month's real length.

---

## Building recommendation — **R**

```json
{
  "recommendation": "Design for passive cooling: ...",
  "category": "thermal_comfort",
  "priority": "HIGH",
  "reason": "Mean annual temperature is 26.54°C, with a record high of 49.01°C, and relative humidity averages 44.09%. Dry air makes thermal mass and evaporative cooling effective.",
  "triggering_data": { "temperature_c": 26.54, "temperature_max_c": 49.01, "humidity_pct": 44.09 },
  "calculations": {
    "estimated_floor_area_sqm": 330.0,
    "required_openable_area_sqm": 41.2,
    "openable_area_share_of_floor": 0.125,
    "formula": "openable_area_m2 = floor_area_m2 * openable_area_share"
  },
  "guideline_basis": [{
    "parameter": "thermal.openable_area_share_of_floor",
    "value": 0.125, "unit": "fraction", "origin": "guideline",
    "note": "Eco-Niwas Samhita requires openable window area of at least 12.5% ...",
    "source_title": "Eco-Niwas Samhita (Energy Conservation Building Code - Residential)",
    "source_publisher": "Bureau of Energy Efficiency (BEE), Government of India"
  }]
}
```

Categories: `water` · `energy` · `thermal_comfort` · `flood_resilience` · `green_cover` ·
`site_planning`. Priorities: `HIGH` · `MEDIUM` · `LOW`.

`origin` is `guideline` (published reference, **compliance not verified**) or
`project_assumption` (**no regulatory weight**).

## Skipped rule — **R**

```json
{
  "rule": "Flood resilience (elevated-risk measures)",
  "reason": "Modelled flood probability is 10%, in the LOW band. ... the model's recall is moderate, so LOW means no evidence of flood exposure rather than proof of safety.",
  "triggering_data": { "flood_probability": 0.1, "risk_level": "LOW" }
}
```

---

## Microplastic screening — **P**

```json
{
  "model": "Microplastic Screening",
  "architecture": "resnet18 (timm, ImageNet pretrained)",
  "task": "binary image classification (screening)",
  "detections": [],
  "count": 0,
  "confidence": 0.9923,
  "classification": "no_microplastic_detected",
  "microplastic_detected": false,
  "class_probabilities": { "no_microplastic_detected": 0.9923,
                           "microplastic_candidate": 0.0077 },
  "input": {
    "mode": "polarimetric_triplet",
    "channels": { "R": "reflectance", "A": "angle of polarisation",
                  "P": "degree of polarisation" },
    "model_input_size": 96,
    "received_sizes": { "R": [43, 75], "A": [43, 75], "P": [43, 75] }
  },
  "warnings": [],
  "disclaimer": "Image-based screening only; does not determine chemical composition, polymer type, or absolute concentration. ..."
}
```

`count` is **images flagged (0 or 1), never particles**. `region` is always
`whole_image`, because HMPD carries image-level labels only.

---

## GeoJSON layer — **P** + **M**

```json
{
  "type": "FeatureCollection",
  "crs": { "type": "name", "properties": { "name": "EPSG:4326" } },
  "features": [{
    "type": "Feature",
    "id": "Agra_86793117",
    "geometry": { "type": "Polygon", "coordinates": [[ [77.9642, 26.9477], "..." ]] },
    "properties": {
      "grid_id": "Agra_86793117", "city": "Agra",
      "water_body_probability": 0.0809, "is_water_body": false,
      "classification": "non_water_body", "observed_occurrence_pct": 0.0,
      "lat": 26.952192, "lon": 77.969275
    }
  }]
}
```

Per layer, the property carrying the class and the value:

| Layer | Class property | Value property |
|---|---|---|
| `urban` | `suitability_class` | `suitability_score` |
| `flood` | `risk_level` | `flood_probability` |
| `water` | `classification` | `water_body_probability` |

---

## Error envelope

One shape for every failure:

```json
{
  "error": "model_unavailable",
  "message": "Model 3 (Flood Risk) is not available. The trained artifact could not be loaded.",
  "detail": {
    "model": "Model 3 (Flood Risk)",
    "expected_file": "BEST_MODEL_random_forest.joblib",
    "config_key": "FLOOD_MODEL_PATH",
    "remedy": "Set FLOOD_MODEL_PATH in .env to the artifact location."
  }
}
```

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_input` | 400 / 422 | Outside the accepted domain |
| `grid_not_found` | 404 | Not on the 1 km grid |
| `model_unavailable` | 503 | Artifact missing; names file and config key |
| `dataset_unavailable` | 503 | Feature dataset missing |
| `upstream_unavailable` | 502 | NASA POWER or Groq unreachable |
| `inference_failed` | 500 | Model loaded but prediction failed |

Error detail carries file **names**, never filesystem paths.

---

## Pipeline state

```python
class CityState(TypedDict, total=False):
    location: dict
    building_params: dict | None
    options: dict

    water_result: dict        # P — never mutated after writing
    urban_result: dict        # P
    flood_result: dict        # P
    building_result: dict     # R

    water_analysis: dict      # I
    urban_analysis: dict      # I
    flood_analysis: dict      # I
    building_analysis: dict   # I

    coordinator_result: dict  # I over an R skeleton

    errors: Annotated[list[dict], operator.add]
    trace: Annotated[list[str], operator.add]
```

The `*_result` / `*_analysis` split is the architectural boundary, and it is visible in
the API response: a consumer can read the raw number beside the interpretation of it.
