# Model Card — Model 3: Urban Flood Risk

## Purpose

Predict flood susceptibility for a 1 km grid cell, so development can be directed away
from flood-exposed land, or conditioned on resilience measures where it proceeds.

## What this model is

A **Random Forest classifier** inside a scikit-learn `Pipeline` (`ColumnTransformer` +
`RandomForestClassifier`), selected over XGBoost, LightGBM, Extra Trees and logistic
regression during training.

Hyper-parameters: `n_estimators=200`, `max_depth=16`, `min_samples_leaf=10`,
`max_features='sqrt'`.

## Input features (38)

| Group | Features |
|---|---|
| Location | `lat`, `lon`, `is_core`, `state` (categorical) |
| Terrain | `elevation_m`, `slope_deg`, `depression_index_m` |
| Surface water | `water_occurrence_pct`, `water_fraction`, `water_seasonality_months`, `water_recurrence_pct`, `water_max_extent_pct`, `water_max_extent_fraction` |
| Built-up history | `built_fraction_1975/1990/2000/2015/2020`, `built_surface_m2_2020`, `built_fraction_growth` |
| Building density | `building_count_total`, `building_height_mean`, `building_presence_mean` |
| Rainfall | `rainfall_annual_mm_mean/max/std`, `rainfall_m01..m12_climatology` |

Feature order is read from the fitted estimator's own `feature_names_in_`.

## Output

```json
{
  "flood_probability": 0.6746,
  "risk_level": "HIGH",
  "risk_meaning": "High flood susceptibility — development should be restricted or heavily mitigated",
  "decision_threshold": 0.5718,
  "risk_bands": {"high_at_or_above": 0.6, "moderate_at_or_above": 0.3},
  "risk_drivers": [
    {
      "driver": "low_elevation",
      "reason": "Elevation of 3 m leaves little gravity drainage head.",
      "measured": {"elevation_m": 3.07}
    }
  ]
}
```

### Risk bands

| Band | Condition | Meaning |
|---|---|---|
| **HIGH** | p ≥ 0.60 | Development should be restricted or heavily mitigated |
| **MODERATE** | 0.30 ≤ p < 0.60 | Resilience measures required |
| **LOW** | p < 0.30 | Standard drainage design expected to suffice |

**Rationale for these edges.** The tuned operating threshold is **0.5718**, selected on
the validation cities by maximising a composite score. The bands bracket it: MODERATE
spans the region around the decision boundary where the model is least certain, HIGH sits
clearly above it, LOW clearly below. Both edges are configurable
(`FLOOD_RISK_HIGH_THRESHOLD`, `FLOOD_RISK_MODERATE_THRESHOLD`) and reported by
`GET /api/flood-risk/thresholds`.

### Risk drivers

Each prediction carries deterministic drivers computed in code from the measured layers —
low elevation, flat terrain, local depression, surface-water presence, high rainfall
exposure, impervious surface, rapid urbanisation. These are **measurements**, provided so
an explanation can cite evidence rather than paraphrasing the probability back.

## Target

`flood_label` — observed inundation from the **Global Flood Database** (MODIS events,
2000–2018), aggregated onto the 1 km grid.

Positive-class rate in training: **12.3%** (`scale_pos_weight` 7.16).

## Training data

45 Indian cities on the 1 km grid; **108,642 cells**. Sources: Global Flood Database,
SRTM, CHIRPS, JRC Global Surface Water, GHSL built-up time series, Google Open Buildings.

## Validation strategy

**City-based holdout** — and here it matters more than anywhere else in the project.
Neighbouring 1 km cells are strongly spatially correlated: a single flood event covers
many adjacent cells, so a random cell-level split would place the same event on both
sides of the split and report badly inflated skill.

The 45 cities are partitioned into disjoint groups:

| Split | Cities | Cells |
|---|---|---|
| Train | 31 | 74,906 |
| Validation | 7 | 17,214 |
| Test (unseen) | 7 | 16,522 |

Test cities: Bhopal, Chennai, Jabalpur, Jaipur, Mysuru, Surat, Varanasi.

## Metrics

Decision threshold **0.5718**. All figures recomputed from the artifact and matching the
training run's saved `test_metrics_comparison.csv` to four decimal places.

### Unseen-city test set

| Metric | Value |
|---|---|
| Precision | **0.7046** |
| Recall | **0.4637** |
| F1 | **0.5593** |
| ROC-AUC | **0.8518** |
| PR-AUC | **0.6097** |

### All splits

| Split | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|
| Train | 0.6538 | 0.9408 | 0.7715 | 0.9857 | 0.9190 |
| Validation | 0.6472 | 0.5249 | 0.5796 | 0.8788 | 0.6388 |
| Test | 0.7046 | 0.4637 | 0.5593 | 0.8518 | 0.6097 |

Validation and test performance agree closely (F1 0.580 vs 0.559), which is good
evidence the city-holdout estimate is stable rather than a lucky split.

### Model comparison on the unseen test set

| Model | Threshold | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| **Random Forest** (selected) | 0.5718 | 0.7046 | 0.4637 | **0.5593** | 0.8518 | **0.6097** |
| LightGBM | 0.6817 | 0.6612 | 0.4651 | 0.5461 | 0.8638 | 0.6022 |
| Extra Trees | 0.4766 | 0.7236 | 0.4150 | 0.5275 | **0.8693** | 0.6180 |
| XGBoost | 0.6540 | 0.5513 | 0.4441 | 0.4919 | 0.8587 | 0.5679 |
| Logistic regression | 0.2315 | 0.1666 | **0.9594** | 0.2838 | 0.7944 | 0.3278 |

Logistic regression illustrates why F1 and PR-AUC drove selection rather than recall
alone: it catches 96% of flood cells but with 17% precision, so five of every six alerts
would be false.

### Per-city performance on unseen cities

| City | Cells | Positive rate | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|
| Mysuru | 2,133 | 0.059 | 0.717 | 0.865 | **0.784** | 0.985 | 0.865 |
| Chennai | 2,151 | 0.168 | 0.767 | 0.655 | 0.706 | 0.947 | 0.823 |
| Surat | 2,352 | 0.137 | 0.581 | 0.813 | 0.678 | 0.936 | 0.728 |
| Bhopal | 2,416 | 0.122 | 0.951 | 0.461 | 0.621 | 0.859 | 0.710 |
| Varanasi | 2,493 | 0.200 | 0.825 | 0.341 | 0.483 | 0.820 | 0.659 |
| Jaipur | 2,563 | 0.027 | 0.600 | 0.177 | 0.273 | 0.721 | 0.237 |
| Jabalpur | 2,414 | 0.176 | 0.465 | 0.109 | **0.176** | 0.607 | 0.285 |

**Consult this table before relying on a result for a specific city.** Performance ranges
from strong (Mysuru, F1 0.78, ROC-AUC 0.985) to poor (Jabalpur, F1 0.18, ROC-AUC 0.61 —
barely above random). Jaipur's very low positive rate (2.7%) makes the shared threshold
too conservative there.

### Feature importance (global, from training)

| Feature | Importance |
|---|---|
| `water_max_extent_pct` | 0.082 |
| `water_max_extent_fraction` | 0.081 |
| `elevation_m` | 0.060 |
| `lat` | 0.056 |
| `water_recurrence_pct` | 0.045 |
| `lon` | 0.040 |
| `water_occurrence_pct` | 0.038 |

Surface-water extent and elevation dominate, which is physically sensible. That `lat` and
`lon` rank fourth and sixth is a caution: the model is partly memorising *where* floods
were recorded, not only what makes a place flood-prone. Per-prediction SHAP attributions
are available on every response.

## Limitations

- **Label observation quality varies.** Flood labels come from satellite-observed
  inundation, whose detection depends on cloud cover, revisit timing and how long water
  stood. **Absence of a label is not proof a cell never flooded**, and short or
  cloud-obscured events are systematically under-recorded.
- **Labels end in 2018.** Drainage infrastructure built since is invisible to the model,
  so it may overstate risk where mitigation has been completed.
- **Moderate recall (0.464).** Over half of flood-prone cells in unseen cities are
  missed. **A LOW result is absence of evidence, not evidence of safety** — stated in the
  API response and in every agent narrative.
- **Severe per-city variance.** F1 ranges 0.18–0.78; ROC-AUC falls to 0.607 for Jabalpur.
- **Pluvial flooding is only implicit.** Drainage-capacity (sewer overload) flooding is
  represented only through built-up fraction and rainfall, never through actual drainage
  network data. Urban flash flooding from undersized drains is largely invisible.
- **Spatial coordinates as features.** `lat`/`lon` importance means some location
  memorisation; this will not transfer to a new region.
- **Global threshold.** One threshold across cities whose positive rates range 0.03–0.20.
- **1 km resolution.** Far coarser than the sub-100 m scale at which urban flooding is
  usually experienced. A cell is not uniformly at risk.
- **No hydraulic modelling.** This is statistical susceptibility, not a hydrodynamic flood
  model, and produces no flood depth, extent or return period.

## Known biases

Cities with dense, well-observed flood records are better predicted than those with
sparse ones — partly reflecting observation quality rather than true flood risk. Cells
near permanent water are more readily flagged than cells that flood from drainage
overload, because the surface-water features dominate.

## Intended use

Screening at city scale to steer development away from flood-exposed land, and to trigger
resilience requirements where development proceeds. **Not** suitable for flood insurance
pricing, design flood levels, individual property assessment, or emergency response.
Design flood levels must come from municipal records and hydraulic study.

## Reproducing these numbers

```bash
cd backend
python -m scripts.evaluation.evaluate_models --model flood
```
