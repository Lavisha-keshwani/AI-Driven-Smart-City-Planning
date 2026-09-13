# Model Card — Model 1: Surface Water Monitoring

## Purpose

Decide whether a 1 km grid cell is a surface-water body, and report the observed
surface-water regime for that cell. Together these support the project's first
question: where is the water, and how dependable is it?

## What this model actually is

A **binary classifier** — an XGBoost model inside a scikit-learn `Pipeline`
(`ColumnTransformer` + `XGBClassifier`).

> **An important correction.** An earlier draft of the project documentation described
> Model 1 as a LightGBM **regressor** predicting water fraction, reporting R² = 0.995
> on a random split and R² = 0.985 on an unseen-city holdout. The artifact this
> repository ships is not that model, and those figures cannot be reproduced from it.
> They belong to a different, regression-based lineage. **This project therefore never
> reports them.** Every metric below was recomputed from the shipped artifact and
> matches the training run's own saved outputs exactly.

## Input features (28)

| Group | Features |
|---|---|
| Location | `lat`, `lon`, `is_core`, `state` (categorical) |
| Terrain | `elevation_m`, `slope_deg`, `depression_index_m` |
| Spectral | `ndbi`, `ndvi` |
| Land cover | `built`, `trees` |
| Climate | `temperature_2m_C`, `rainfall_annual_mm_2024`, `rainfall_annual_mm_mean/max/std`, `rainfall_m01..m12_climatology` |

Feature order is read from the fitted estimator's own `feature_names_in_`, never from a
hand-written list, so it cannot drift from the artifact.

## Output

```json
{
  "water_body_probability": 0.6343,
  "is_water_body": true,
  "classification": "water_body",
  "decision_threshold": 0.5169,
  "observed": {
    "water_occurrence_pct": 27.9,
    "water_seasonality_months": 7.71,
    "water_recurrence_pct": 96.3
  },
  "water_body_status": {
    "status": "seasonal",
    "inter_annual_reliability": "high",
    "basis": "Global Surface Water (JRC GSW) observations — measured, not predicted"
  }
}
```

The `observed` and `water_body_status` blocks are **measurements**, labelled as such so
they are never confused with the model's prediction.

## Target

`is_water_body` — Global Surface Water occurrence ≥ **25%** at the cell. The threshold
is recorded in the artifact's `feature_list.json` and configurable via
`WATER_OCCURRENCE_THRESHOLD_PCT`.

## Training data

45 Indian cities on the 1 km grid; **108,642 cells**. Sources: JRC Global Surface Water
1.4, SRTM, CHIRPS, Dynamic World, Sentinel-2 spectral indices.

Positive-class rate in training: **15.6%** (`scale_pos_weight` 5.41).

## Validation strategy

**City-based holdout.** The 45 cities are partitioned into disjoint train / validation /
unseen-test groups, so no city contributes cells to more than one split. A random
cell-level split would leak spatially — adjacent 1 km cells share water bodies — and
overstate performance.

| Split | Cities | Cells |
|---|---|---|
| Train | 31 | 73,876 |
| Validation | 7 | 17,296 |
| Test (unseen) | 7 | 17,470 |

Test cities: Agra, Chennai, Lucknow, Ludhiana, Mysuru, Raipur, Srinagar.

## Metrics

Decision threshold **0.5169**, tuned on the validation cities by maximising a composite
score. All figures recomputed from the artifact and matching the training run's saved
`test_metrics_comparison.csv` to four decimal places.

### Unseen-city test set

| Metric | Value |
|---|---|
| Precision | **0.8017** |
| Recall | **0.5152** |
| F1 | **0.6273** |
| ROC-AUC | **0.8614** |
| PR-AUC | **0.7274** |

### All splits

| Split | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|
| Train | 0.7201 | 0.8929 | 0.7972 | 0.9772 | 0.9161 |
| Validation | 0.4903 | 0.3816 | 0.4292 | 0.7539 | 0.4021 |
| Test | 0.8017 | 0.5152 | 0.6273 | 0.8614 | 0.7274 |

The train-to-test gap is substantial: this model does not generalise to new cities as
well as its training performance suggests.

### Per-city performance on unseen cities

| City | Cells | Positive rate | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|---|
| Chennai | 2,151 | 0.564 | 0.918 | 0.887 | **0.902** | 0.952 |
| Raipur | 2,344 | 0.412 | 0.646 | 0.402 | 0.496 | 0.709 |
| Mysuru | 2,133 | 0.170 | 0.781 | 0.333 | 0.467 | 0.785 |
| Agra | 2,571 | 0.048 | 0.575 | 0.189 | 0.284 | 0.886 |
| Lucknow | 2,553 | 0.044 | 0.435 | 0.177 | 0.252 | 0.703 |
| Srinagar | 2,956 | 0.087 | 0.412 | 0.055 | 0.097 | 0.788 |
| Ludhiana | 2,762 | 0.056 | 0.000 | 0.000 | **0.000** | 0.706 |

**Read this table before trusting a result for a specific city.** Performance ranges
from excellent (Chennai, F1 0.90) to complete failure (Ludhiana, F1 0.00 — the model
identified no water body correctly there at the tuned threshold). Cities with a low
positive rate fare worst: where water is scarce, the fixed threshold is too
conservative. ROC-AUC stays moderate even for Ludhiana (0.706), so the ranking carries
some signal even where the thresholded decision does not.

### Feature importance (global, from training)

| Feature | Importance |
|---|---|
| `state_Jharkhand` | 0.109 |
| `ndvi` | 0.105 |
| `rainfall_m06_climatology` | 0.055 |
| `elevation_m` | 0.050 |
| `state_Tamil Nadu` | 0.044 |

Per-prediction SHAP attributions are available on every response, with one-hot columns
folded back onto their source feature so callers see `state`, not `state_Kerala`.

## Limitations

- **Spectral dependence.** NDVI and NDBI dominate the importances, so the model inherits
  their sensitivity to season, cloud cover and image acquisition date. The spec's
  concern about NDWI dependence applies here to the NDWI-family indices actually used.
- **Moderate recall (0.515).** Roughly half of true water bodies in unseen cities are
  missed. A `non_water_body` result is **absence of evidence, not evidence of absence**.
  Small and narrow water bodies are missed most often.
- **Severe per-city variance.** F1 ranges 0.00–0.90 across the seven unseen cities.
- **Regional priors.** `state` is an input and carries high importance, so predictions
  embed regional priors. A newly added state has no learned prior; retraining is
  required before its predictions should be trusted.
- **Geographic scope.** 45 Indian cities only. Behaviour elsewhere is unvalidated.
- **Threshold is global.** One threshold is applied to every city despite positive rates
  ranging 0.04–0.56. Per-city thresholds would likely help considerably.
- **1 km resolution.** A cell is classified as a whole; sub-kilometre features are not
  resolved.

## Known biases

Water-scarce cities are systematically under-detected: the shared threshold suits
water-rich cities far better. State one-hot features mean the model has effectively
learned per-region base rates, which will misfire where a region's hydrology has
changed.

## Intended use

Screening and monitoring at city scale, alongside the observed GSW record. **Not**
suitable for regulatory water-body delineation, property boundary decisions, or any
purpose requiring a guaranteed detection.

## Reproducing these numbers

```bash
cd backend
python -m scripts.evaluation.evaluate_models --model water
```

Prints every figure above and asserts agreement with the training run's saved metrics.
