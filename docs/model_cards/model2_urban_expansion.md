# Model Card — Model 2: Urban Expansion Suitability

## Purpose

Answer: **where can the city expand, and where should it not?**

Specifically, the model learns which historical characteristics of a 1 km cell preceded
actual urban expansion, and scores new cells on that basis.

## Forward validation — the design that matters

The model is **not** trained to reproduce present-day urban density. It is trained on a
forward-validation design:

```
features at T0 (2000)  →  growth observed by T1 (2020)  →  training label
```

| Element | Value |
|---|---|
| T0 (features) | GHSL built-up epoch **2000** |
| T1 (target) | GHSL built-up epoch **2020** |
| Target | `built_fraction(T1) − built_fraction(T0)`, **tercile-binned** |
| Classes | 0 = RED (lowest growth), 1 = YELLOW (middle), 2 = GREEN (highest) |
| Tercile edges | 0.001197, 0.012363 |

This is far more defensible than predicting existing development: the model answers
"which characteristics were associated with subsequent urban expansion?", not "where is
the city already built?".

**What the label means, and does not.** The class measures **propensity for expansion**,
learned from where growth historically occurred. It is **not** a judgement that
expansion there is environmentally desirable. A GREEN label is not an approval. This
distinction is enforced downstream: the Coordinator reconciles suitability against flood
and water evidence before any recommendation, and never lets a favourable score suppress
an ecological finding.

## What this model is

A **LightGBM 3-class classifier** (`LGBMClassifier`), selected over HistGradientBoosting,
XGBoost and Random Forest during training.

## Input features (13)

| Group | Features |
|---|---|
| Historical built-up | `built_t0` (GHSL built fraction at 2000) |
| Building density | `building_count_total`, `building_height_mean`, `building_presence_mean` |
| Terrain | `elevation_m`, `slope_deg`, `depression_index_m` |
| Climate | `rainfall_annual_mm` |
| Location | `lat`, `lon`, `is_core`, `city_code`, `state_code` |

Feature order is read from the trained LightGBM booster's own feature names.

### Road density: deliberately excluded

OpenStreetMap road coverage existed for only **3 of the 45 cities**. Including it would
have encoded *data availability* rather than accessibility, so it was dropped. The
exclusion is recorded in the artifact's own `feature_list.json`
(`"note": "road density excluded — OSM only covers 3/45 cities"`) and is a genuine
limitation: accessibility is a real driver of urban growth that this model cannot see.

### Categorical encoding — a reconstruction, and how it was verified

`city_code` and `state_code` are alphabetical pandas category codes over the full
45-city grid. The training script did **not** document this encoding, so this repository
reconstructed it. The reconstruction was then verified empirically: predictions agree
with the tercile-binned growth target on **85.4%** of cells. A mismatched encoding would
have collapsed agreement towards chance (33% for three balanced classes). This check runs
as a test (`test_urban_expansion_agrees_with_forward_validation_target`) and in
`scripts/evaluation/evaluate_urban_expansion.py`.

## Output

```json
{
  "suitability_score": 0.8686,
  "suitability_class": "GREEN",
  "class_meaning": "Suitable — preferred growth direction",
  "confidence": 0.751,
  "class_probabilities": {"RED": 0.0137, "YELLOW": 0.2352, "GREEN": 0.751},
  "score_definition": "P(YELLOW)*0.5 + P(GREEN)*1.0, bounded to [0, 1]",
  "classification_rule": "argmax of class probabilities (as validated)",
  "constraints": [
    {
      "constraint": "high_rainfall",
      "severity": "moderate",
      "reason": "Annual rainfall of 1826 mm demands drainage capacity sized for intense events.",
      "measured": {"rainfall_annual_mm": 1825.66}
    }
  ]
}
```

### The continuous score

```
suitability_score = P(YELLOW) × 0.5 + P(GREEN) × 1.0
```

The expected class value: bounded to [0, 1], monotone in development favourability, and
derived only from the model's calibrated class probabilities. No arbitrary rescaling.

### Classification thresholds

**Default: argmax of the class probabilities** — the exact decision rule the reported
83.5% accuracy was measured under. This is why it is the default: any other rule would
mean the published accuracy no longer describes what the API returns.

An alternative score-threshold rule is available and configurable:

| Variable | Default | Meaning |
|---|---|---|
| `URBAN_CLASS_FROM_SCORE` | `false` | `true` switches to score thresholds |
| `URBAN_SCORE_GREEN_THRESHOLD` | `0.66` | GREEN at or above |
| `URBAN_SCORE_YELLOW_THRESHOLD` | `0.33` | YELLOW at or above |

The defaults are the tercile boundaries of the [0, 1] score range, consistent with a
tercile-derived target. The rule actually in force is reported on every prediction as
`classification_rule`, and by `GET /api/urban-expansion/thresholds`.

### Site constraints

Alongside the score, each prediction carries deterministic constraints computed in code
from the measured terrain and rainfall layers — steep slope, local depression, high
rainfall, already-built-out. These are **measurements, not predictions**, and exist so a
favourable score is never presented without its physical caveats.

## Training data

45 Indian cities on the 1 km grid; **108,642 cells**. Sources: GHSL (built-up surface,
1975/1990/2000/2015/2020), Google Open Buildings, SRTM, CHIRPS.

Class balance is exactly even by construction (36,214 cells per class), because the
target is tercile-binned.

## Metrics

### Training run's reported comparison

| Model | Accuracy | Precision (macro) | Recall (macro) | F1 (macro) | ROC-AUC (OvR) |
|---|---|---|---|---|---|
| **LightGBM** (selected) | **0.8352** | 0.8368 | 0.8350 | 0.8357 | 0.9524 |
| HistGradientBoosting | 0.8351 | 0.8367 | 0.8348 | 0.8356 | 0.9525 |
| XGBoost | 0.8348 | 0.8363 | 0.8345 | 0.8352 | 0.9524 |
| RandomForest | 0.8277 | 0.8300 | 0.8274 | 0.8284 | 0.9486 |

> **A caveat on the validation strategy.** The training run saved
> `metrics_comparison.csv` but **no city-split manifest**, so the 0.8352 accuracy cannot
> be attributed to a spatial holdout. It is reported here as a *documented training-run
> metric*, not as a verified generalisation estimate. This is the weakest validation
> evidence of the three geospatial models, and it is the model's main methodological gap.

### Spatial validation supplied by this project

`scripts/evaluation/evaluate_urban_expansion.py` supplies the missing spatial view:

| Measure | Value |
|---|---|
| Pooled accuracy (all 108,642 cells) | 0.8537 |
| Macro F1 | 0.8543 |
| ROC-AUC (OvR) | 0.9634 |
| Per-city accuracy: mean | 0.8544 |
| Per-city accuracy: range | **0.798 – 0.924** |
| Per-city accuracy: std | 0.0338 |

Per-class performance:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| RED | 0.91 | 0.87 | 0.89 | 36,214 |
| YELLOW | 0.77 | 0.80 | 0.79 | 36,214 |
| GREEN | 0.88 | 0.89 | 0.88 | 36,214 |

Confusion matrix (rows observed, columns predicted):

|  | RED | YELLOW | GREEN |
|---|---|---|---|
| **RED** | 31,660 | 4,436 | 118 |
| **YELLOW** | 2,911 | 28,900 | 4,403 |
| **GREEN** | 59 | 3,963 | 32,192 |

Errors are almost entirely between adjacent classes: only 118 RED cells were called
GREEN and 59 GREEN cells called RED out of 108,642. The middle class is hardest, which is
expected — YELLOW is bounded by two tercile edges rather than one.

Per-city accuracy is notably even (std 0.034), and the weakest city (Patna, 0.798) is not
far below the strongest (Kochi, 0.924). That consistency is reassuring, but it is **not**
a clean generalisation estimate: the artifact was fitted before this script existed, and
without a split manifest these cities cannot be guaranteed unseen.

## Limitations

- **No verified spatial holdout.** The reported accuracy comes from a training run that
  saved no city-split manifest. Retraining with a declared city split is the single
  highest-value improvement available to this model.
- **Road density excluded** (OSM covered 3/45 cities), so accessibility — a real driver
  of urban growth — is invisible to the model.
- **Growth propensity, not desirability.** A GREEN cell is where expansion historically
  happened. Flood and water evidence must be weighed against it, which is the
  Coordinator's job.
- **Nationally relative terciles.** Classes are cut across all 45 cities, so a GREEN cell
  is high-growth relative to the national distribution, not to its own city. A
  slow-growing city may contain few GREEN cells even where it is expanding fastest.
- **Ordinal encoding of nominal categories.** `city_code`/`state_code` impose an
  arbitrary alphabetical ordering that tree splits can exploit — Agra (0) and Ahmedabad
  (1) are adjacent for no geographic reason.
- **Historical extrapolation.** Growth observed over 2000–2020 need not continue under
  changed policy, new transport infrastructure, or altered planning regulation.
- **A 20-year window, once.** The model sees one T0→T1 transition, so it cannot separate
  a persistent pattern from a one-off 2000s building boom.

## Known biases

The model will reproduce historical development patterns, including their mistakes. If a
city historically expanded into flood-prone or ecologically sensitive land, those cells
carry high growth propensity, and the model will score them GREEN. **This is the precise
reason the Coordinator layer exists**, and why a water-body cell is an ecological hard
stop that overrides any suitability score.

## Intended use

Strategic identification of candidate growth directions at city scale, always read
together with the flood and water findings. **Not** suitable as a development permit
input, a land-valuation signal, or a standalone basis for any approval.

## Reproducing these numbers

```bash
cd backend
python -m scripts.evaluation.evaluate_urban_expansion --out build/
python -m scripts.features.build_urban_expansion_features --out build/ --with-target
```
