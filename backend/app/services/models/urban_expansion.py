"""
Model 2 — Urban Expansion Suitability.

The trained artifact is a LightGBM 3-class classifier over a forward-validation
target: features describe the *historical* state of a 1 km cell at T0 (2000) and
the label is which tercile of subsequent built-up growth the cell fell into by
T1 (2020).

    features at T0  ->  growth observed between T0 and T1  ->  class
    built_t0, building density/height/presence, elevation, slope,
    depression index, annual rainfall, lat, lon, is_core, city, state

    class 0 = RED     lowest growth tercile    avoid / unsuitable
    class 1 = YELLOW  middle growth tercile    conditional
    class 2 = GREEN   highest growth tercile   preferred growth

This is the defensible framing the specification asks for: the model learns which
characteristics preceded actual expansion, rather than memorising where the city
is already built. Road density was excluded at training time because OpenStreetMap
coverage existed for only 3 of the 45 cities — recorded in the artifact's own
feature list, and repeated in the model card.

CONTINUOUS SCORE
The head-line `suitability_score` is the expected class value:

    score = P(YELLOW) * 0.5 + P(GREEN) * 1.0

which is bounded to [0, 1], monotone in development favourability, and derived
only from calibrated class probabilities — no arbitrary rescaling. The GREEN /
YELLOW / RED label is argmax of the class probabilities, i.e. the exact decision
rule the reported accuracy was measured under. Setting URBAN_CLASS_FROM_SCORE
switches labelling to configurable score thresholds instead.

ECOLOGICAL GUARD
A high growth-propensity score is a statement about development pressure, not an
environmental endorsement. This module therefore never emits a bare GREEN: it
also returns `constraints` describing terrain and rainfall limits at the cell, and
the Coordinator layer is responsible for reconciling suitability against flood and
water evidence before any recommendation is made.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.core import config
from app.core.errors import InferenceError
from app.services.models import explain, feature_store, registry

logger = logging.getLogger(__name__)

MODEL_KEY = "model2_urban_expansion"
MODEL_NAME = "Urban Expansion Suitability"

CLASS_LABELS = {0: "RED", 1: "YELLOW", 2: "GREEN"}
CLASS_MEANING = {
    "GREEN": "Suitable — preferred growth direction",
    "YELLOW": "Conditional — requires further consideration",
    "RED": "Avoid — unsuitable or high-risk for expansion",
}
# Weight applied to each class when collapsing probabilities to one score.
_SCORE_WEIGHTS = {0: 0.0, 1: 0.5, 2: 1.0}


def feature_order() -> list[str]:
    return feature_store.model_feature_order(registry.urban_expansion_model())


def _clean(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(number) else round(number, 6)


def _label_from_config() -> dict[int, str]:
    """Class-to-label mapping, preferring the artifact's own feature_list.json."""
    raw = registry.model2_config().get("label_map")
    if not raw:
        return CLASS_LABELS
    return {int(k): str(v).upper() for k, v in raw.items()}


def suitability_score(probabilities: np.ndarray, classes: np.ndarray) -> float:
    """Collapse class probabilities into a continuous [0, 1] suitability score."""
    score = sum(
        _SCORE_WEIGHTS.get(int(cls), 0.0) * float(p) for cls, p in zip(classes, probabilities)
    )
    return float(np.clip(score, 0.0, 1.0))


def _classify(score: float, probabilities: np.ndarray, classes: np.ndarray) -> tuple[str, str]:
    """Return (label, the rule that produced it)."""
    labels = _label_from_config()
    if config.URBAN_CLASS_FROM_SCORE:
        if score >= config.URBAN_SCORE_GREEN_THRESHOLD:
            label = "GREEN"
        elif score >= config.URBAN_SCORE_YELLOW_THRESHOLD:
            label = "YELLOW"
        else:
            label = "RED"
        rule = (
            f"score thresholds (GREEN >= {config.URBAN_SCORE_GREEN_THRESHOLD}, "
            f"YELLOW >= {config.URBAN_SCORE_YELLOW_THRESHOLD})"
        )
        return label, rule

    predicted = int(classes[int(np.argmax(probabilities))])
    return labels.get(predicted, "UNKNOWN"), "argmax of class probabilities (as validated)"


def _constraints(row: pd.Series) -> list[dict]:
    """Deterministic site constraints read from the terrain and rainfall layers.

    These are measured limits, computed in code, not model predictions. They exist
    so a favourable growth score is never presented without its physical caveats.
    """
    out = []
    slope = _clean(row.get("slope_deg"))
    depression = _clean(row.get("depression_index_m"))
    rainfall = _clean(row.get("rainfall_annual_mm"))
    built_t0 = _clean(row.get("built_t0"))

    if slope is not None and slope >= 15:
        out.append({
            "constraint": "steep_terrain",
            "severity": "high" if slope >= 25 else "moderate",
            "reason": f"Slope of {slope:.1f} degrees raises construction cost and erosion risk.",
            "measured": {"slope_deg": slope},
        })
    if depression is not None and depression >= 2:
        out.append({
            "constraint": "local_depression",
            "severity": "high" if depression >= 5 else "moderate",
            "reason": (
                f"The cell sits {depression:.1f} m below its surroundings, so surface "
                f"water collects here."
            ),
            "measured": {"depression_index_m": depression},
        })
    if rainfall is not None and rainfall >= 1500:
        out.append({
            "constraint": "high_rainfall",
            "severity": "moderate",
            "reason": (
                f"Annual rainfall of {rainfall:.0f} mm demands drainage capacity sized "
                f"for intense events."
            ),
            "measured": {"rainfall_annual_mm": rainfall},
        })
    if built_t0 is not None and built_t0 >= 0.5:
        out.append({
            "constraint": "already_substantially_built",
            "severity": "low",
            "reason": (
                f"{built_t0 * 100:.0f}% of the cell was already built up at the "
                f"{config.M2_T0_YEAR} baseline, so there is limited room for new expansion."
            ),
            "measured": {"built_fraction_t0": built_t0},
        })
    return out


def predict(grid_id: str, *, explain_prediction: bool = True) -> dict:
    """Score one grid cell for urban expansion suitability."""
    model = registry.urban_expansion_model()
    row = feature_store.urban_expansion_row(grid_id)
    features = feature_order()

    missing = [f for f in features if f not in row.index]
    if missing:
        raise InferenceError(
            "The Model 2 feature table is missing columns the trained model requires.",
            detail={"missing_features": missing},
        )

    X = row[features].to_frame().T.astype(float)
    incomplete = [f for f in features if pd.isna(row[f])]

    try:
        probabilities = model.predict_proba(X)[0]
    except Exception as exc:  # noqa: BLE001
        raise InferenceError(
            f"Model 2 inference failed for grid cell {grid_id}.",
            detail={"reason": str(exc)},
        ) from exc

    classes = np.asarray(model.classes_)
    score = suitability_score(probabilities, classes)
    label, rule = _classify(score, probabilities, classes)
    labels = _label_from_config()

    result = {
        "model": MODEL_NAME,
        "model_key": MODEL_KEY,
        "algorithm": registry.model2_config().get("best_model", "LightGBM"),
        "grid_id": str(row["grid_id"]),
        "city": str(row.get("city", "unknown")),
        "state": str(row.get("state", "unknown")),
        "lat": _clean(row.get("lat")),
        "lon": _clean(row.get("lon")),
        # Model output
        "suitability_score": round(score, 4),
        "suitability_class": label,
        "class_meaning": CLASS_MEANING.get(label, "Unknown"),
        "confidence": round(float(np.max(probabilities)), 4),
        "class_probabilities": {
            labels.get(int(cls), str(cls)): round(float(p), 4)
            for cls, p in zip(classes, probabilities)
        },
        "classification_rule": rule,
        "score_definition": "P(YELLOW)*0.5 + P(GREEN)*1.0, bounded to [0, 1]",
        # Observed context
        "observed": {
            "built_fraction_t0": _clean(row.get("built_t0")),
            "built_fraction_t1": _clean(row.get("built_t1")),
            "built_growth_t0_t1": _clean(row.get("built_growth_t0_t1")),
            "t0_year": config.M2_T0_YEAR,
            "t1_year": config.M2_T1_YEAR,
            "elevation_m": _clean(row.get("elevation_m")),
            "slope_deg": _clean(row.get("slope_deg")),
            "depression_index_m": _clean(row.get("depression_index_m")),
            "rainfall_annual_mm": _clean(row.get("rainfall_annual_mm")),
            "building_count_total": _clean(row.get("building_count_total")),
            "building_presence_mean": _clean(row.get("building_presence_mean")),
        },
        "constraints": _constraints(row),
        "incomplete_features": incomplete,
    }

    if explain_prediction:
        green_index = int(np.argmax(probabilities))
        result["feature_attribution"] = explain.explain_prediction(
            MODEL_KEY, model, X, class_index=green_index
        )

    logger.info(
        "Model 2 %s: score=%.4f class=%s confidence=%.4f",
        grid_id, score, label, result["confidence"],
    )
    return result


def predict_city(city: str, *, limit: int | None = None) -> list[dict]:
    """Batch-score every cell in a city — the map layer's data source."""
    model = registry.urban_expansion_model()
    table = feature_store.subset_for_city(feature_store.urban_expansion_table(), city)
    if limit is not None:
        table = table.head(limit)

    features = feature_order()
    probabilities = model.predict_proba(table[features].astype(float))
    classes = np.asarray(model.classes_)
    labels = _label_from_config()

    records = []
    for (_, row), probs in zip(table.iterrows(), probabilities):
        score = suitability_score(probs, classes)
        label, _ = _classify(score, probs, classes)
        records.append(
            {
                "grid_id": str(row["grid_id"]),
                "city": str(row.get("city", "unknown")),
                "lat": _clean(row.get("lat")),
                "lon": _clean(row.get("lon")),
                "suitability_score": round(score, 4),
                "suitability_class": label,
                "confidence": round(float(np.max(probs)), 4),
                "class_probabilities": {
                    labels.get(int(c), str(c)): round(float(p), 4)
                    for c, p in zip(classes, probs)
                },
            }
        )
    distribution: dict[str, int] = {}
    for r in records:
        distribution[r["suitability_class"]] = distribution.get(r["suitability_class"], 0) + 1
    logger.info("Model 2 batch for %s: %d cells, distribution=%s", city, len(records), distribution)
    return records


def metrics() -> dict:
    """Validation evidence for Model 2."""
    comparison = registry.model2_metrics()
    cfg = registry.model2_config()

    selected_name = cfg.get("best_model")
    selected = None
    if comparison is not None and "model" in comparison.columns and selected_name:
        match = comparison[comparison["model"] == selected_name]
        if not match.empty:
            selected = match.iloc[0].replace({np.nan: None}).to_dict()

    return {
        "model": MODEL_NAME,
        "algorithm": selected_name,
        "task": (
            "3-class forward-validation classification — which tercile of subsequent "
            "built-up growth does this cell fall into?"
        ),
        "forward_validation": {
            "t0_year": cfg.get("t0_year", config.M2_T0_YEAR),
            "t1_year": cfg.get("t1_year", config.M2_T1_YEAR),
            "design": (
                "Predictors describe the cell's state at T0. The label is the tercile "
                "of GHSL built-up growth observed between T0 and T1. The model therefore "
                "learns which historical characteristics preceded actual expansion, rather "
                "than reproducing present-day urban density."
            ),
            "target_construction": "GHSL built_fraction(T1) - built_fraction(T0), tercile-binned",
        },
        "label_map": cfg.get("label_map"),
        "class_meaning": CLASS_MEANING,
        "features": cfg.get("features"),
        "data_sources": [
            "GHSL (built-up surface, 1975/1990/2000/2015/2020 epochs)",
            "Google Open Buildings (building count, height, presence)",
            "SRTM (elevation, slope, depression index)",
            "CHIRPS (annual rainfall)",
            "1 km city grid registry (lat, lon, is_core, city, state)",
        ],
        "selected_model_metrics": selected,
        "all_model_comparison": (
            comparison.replace({np.nan: None}).to_dict(orient="records")
            if comparison is not None else None
        ),
        "metrics_source": (
            "metrics_comparison.csv from the training run. The training run did not "
            "save a city-level split manifest for this model, so these figures are "
            "reported as documented training-run metrics. Run "
            "scripts/evaluation/evaluate_urban_expansion.py for a reproducible "
            "city-holdout evaluation of the shipped artifact."
        ),
        "global_feature_importance": None,
        "limitations": [
            "Road density was excluded: OpenStreetMap coverage existed for only 3 of "
            "the 45 cities, so the feature could not be built consistently.",
            "The target is growth propensity, not environmental desirability. A GREEN "
            "cell is where expansion historically happened, which is why flood and "
            "water evidence must be reconciled against it before any recommendation.",
            "Terciles are defined across the whole 45-city pool, so classes are "
            "relative to the national distribution rather than to each city.",
            "city_code/state_code are ordinal encodings of nominal categories, which "
            "imposes an arbitrary ordering the tree splits can exploit.",
            "Growth observed over 2000-2020 need not continue under changed policy.",
        ],
    }
