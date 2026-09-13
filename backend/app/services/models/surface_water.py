"""
Model 1 — Surface Water Monitoring.

What the trained artifact actually is: an XGBoost classifier inside an sklearn
Pipeline that predicts whether a 1 km grid cell is a surface-water body, from
terrain, rainfall climatology, spectral indices (NDWI-family NDBI/NDVI), land
cover and temperature. The target was defined as Global Surface Water occurrence
at or above the threshold the training run recorded (25%).

This is a classifier, not the water-fraction regressor an earlier draft of the
project documentation described. The R2 = 0.995 / 0.985 figures in that document
belong to a different, regression-based lineage that this repository's saved
artifacts do not correspond to, so they are never reported here. What this module
exposes are the metrics the shipped artifact actually produced on its unseen-city
holdout, read from the training run's own output files.

Alongside the prediction, each response carries the *observed* Global Surface
Water statistics for the cell (occurrence, seasonality, recurrence, maximum
extent). Those are measurements, and are labelled as such so they are never
confused with the model output.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.core import config
from app.core.errors import InferenceError
from app.services.models import explain, feature_store, registry

logger = logging.getLogger(__name__)

MODEL_KEY = "model1_surface_water"
MODEL_NAME = "Surface Water Monitoring"

_OBSERVED_WATER_COLUMNS = [
    "water_occurrence_pct",
    "water_fraction",
    "water_seasonality_months",
    "water_recurrence_pct",
    "water_max_extent_pct",
    "water_max_extent_fraction",
]


def operating_threshold() -> float:
    """The decision threshold the training run tuned for the selected algorithm."""
    thresholds = registry.model1_thresholds()
    value = thresholds.get(config.M1_ALGORITHM)
    if value is None:
        raise InferenceError(
            "Model 1 has no tuned decision threshold for the configured algorithm, "
            "so a classification cannot be issued.",
            detail={"algorithm": config.M1_ALGORITHM, "available": sorted(thresholds)},
        )
    return float(value)


def feature_order() -> list[str]:
    return feature_store.model_feature_order(registry.surface_water_model())


def _clean(value) -> float | None:
    """JSON-safe float, preserving missingness as null instead of a fake zero."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(number) else round(number, 6)


def _observed_water(row: pd.Series) -> dict:
    return {col: _clean(row.get(col)) for col in _OBSERVED_WATER_COLUMNS if col in row.index}


def _water_status(row: pd.Series) -> dict:
    """Read the observed Global Surface Water statistics into a water-body status.

    A deterministic reading of the measured layer, not an inference:
      permanent  — surface water present essentially year round
      seasonal   — present for part of each year
      ephemeral  — detected occasionally, below the water-body threshold
      none       — never detected as water

    `inter_annual_reliability` reports the GSW recurrence metric, which measures
    how consistently water returns from one year to the next. A seasonal cell with
    high recurrence is a dependable seasonal water body; low recurrence marks a
    cell where water appeared only in some years.

    No extent trend is derived here. The `water_max_extent_pct` column in this
    dataset is on a different scale from `water_occurrence_pct`, so differencing
    the two would not measure contraction. Multi-year water-body stability is
    reported per city instead, from the training run's own monitoring summary —
    see `city_water_body_summary()`.
    """
    occurrence = _clean(row.get("water_occurrence_pct"))
    months = _clean(row.get("water_seasonality_months"))
    recurrence = _clean(row.get("water_recurrence_pct"))

    if occurrence is None:
        status = "unknown"
    elif occurrence >= 75:
        status = "permanent"
    elif occurrence >= config.WATER_OCCURRENCE_THRESHOLD_PCT:
        status = "seasonal"
    elif occurrence > 0:
        status = "ephemeral"
    else:
        status = "none"

    if recurrence is None:
        reliability = "unknown"
    elif recurrence >= 75:
        reliability = "high"
    elif recurrence >= 40:
        reliability = "moderate"
    elif recurrence > 0:
        reliability = "low"
    else:
        reliability = "none"

    return {
        "status": status,
        "seasonality_months": months,
        "occurrence_pct": occurrence,
        "inter_annual_reliability": reliability,
        "recurrence_pct": recurrence,
        "water_body_threshold_pct": config.WATER_OCCURRENCE_THRESHOLD_PCT,
        "basis": "Global Surface Water (JRC GSW) observations — measured, not predicted",
    }


def predict(grid_id: str, *, explain_prediction: bool = True) -> dict:
    """Classify one grid cell as a surface-water body.

    Returns the model probability, the classification at the tuned threshold, the
    observed Global Surface Water statistics, a deterministic water-body status
    reading and (when SHAP is available) the top contributing features.
    """
    model = registry.surface_water_model()
    row = feature_store.surface_water_row(grid_id)
    features = feature_order()

    missing = [f for f in features if f not in row.index]
    if missing:
        raise InferenceError(
            "The Model 1 feature table is missing columns the trained model requires.",
            detail={"missing_features": missing},
        )

    X = row[features].to_frame().T
    incomplete = [f for f in features if pd.isna(row[f])]

    try:
        probability = float(model.predict_proba(X)[0, 1])
    except Exception as exc:  # noqa: BLE001 - estimator-specific failures
        raise InferenceError(
            f"Model 1 inference failed for grid cell {grid_id}.",
            detail={"reason": str(exc)},
        ) from exc

    threshold = operating_threshold()
    is_water_body = probability >= threshold

    result = {
        "model": MODEL_NAME,
        "model_key": MODEL_KEY,
        "algorithm": config.M1_ALGORITHM,
        "grid_id": str(row["grid_id"]),
        "city": str(row.get("city", "unknown")),
        "state": str(row.get("state", "unknown")),
        "lat": _clean(row.get("lat")),
        "lon": _clean(row.get("lon")),
        # Model output
        "water_body_probability": round(probability, 4),
        "is_water_body": bool(is_water_body),
        "classification": "water_body" if is_water_body else "non_water_body",
        "decision_threshold": round(threshold, 4),
        # Measured layers, kept explicitly separate from the prediction
        "observed": _observed_water(row),
        "water_body_status": _water_status(row),
        "incomplete_features": incomplete,
    }

    if explain_prediction:
        result["feature_attribution"] = explain.explain_prediction(
            MODEL_KEY, model, X, class_index=1
        )

    logger.info(
        "Model 1 %s: p=%.4f threshold=%.4f -> %s",
        grid_id, probability, threshold, result["classification"],
    )
    return result


def predict_city(city: str, *, limit: int | None = None) -> list[dict]:
    """Batch-classify every cell in a city in one vectorised pass."""
    model = registry.surface_water_model()
    table = feature_store.subset_for_city(feature_store.surface_water_table(), city)
    if limit is not None:
        table = table.head(limit)

    features = feature_order()
    probabilities = model.predict_proba(table[features])[:, 1]
    threshold = operating_threshold()

    records = []
    for (_, row), probability in zip(table.iterrows(), probabilities):
        is_water = bool(probability >= threshold)
        records.append(
            {
                "grid_id": str(row["grid_id"]),
                "city": str(row.get("city", "unknown")),
                "lat": _clean(row.get("lat")),
                "lon": _clean(row.get("lon")),
                "water_body_probability": round(float(probability), 4),
                "is_water_body": is_water,
                "classification": "water_body" if is_water else "non_water_body",
                "observed_occurrence_pct": _clean(row.get("water_occurrence_pct")),
            }
        )
    logger.info(
        "Model 1 batch for %s: %d cells, %d classified as water bodies",
        city, len(records), sum(r["is_water_body"] for r in records),
    )
    return records


def city_water_body_summary(city: str | None = None) -> list[dict]:
    """Per-city water-body monitoring summary produced by the training run."""
    frame = registry.model1_water_body_summary()
    if frame is None:
        return []
    df = frame.copy()
    if city and "city" in df.columns:
        df = df[df["city"].astype(str).str.lower() == city.strip().lower()]
    return df.replace({np.nan: None}).to_dict(orient="records")


def metrics() -> dict:
    """Validation evidence for Model 1, read from the training run's outputs."""
    test = registry.model1_test_metrics()
    run_config = registry.model1_run_config()
    split = registry.model1_city_split()
    city_metrics = registry.model1_city_metrics()

    selected = None
    if test is not None and "model" in test.columns:
        match = test[test["model"] == config.M1_ALGORITHM]
        if not match.empty:
            selected = match.iloc[0].replace({np.nan: None}).to_dict()

    return {
        "model": MODEL_NAME,
        "algorithm": config.M1_ALGORITHM,
        "task": "binary classification — is this 1 km cell a surface-water body?",
        "target": registry.model1_feature_list().get("target", "is_water_body"),
        "target_definition": (
            "Global Surface Water occurrence >= "
            f"{registry.model1_feature_list().get('water_occurrence_threshold', config.WATER_OCCURRENCE_THRESHOLD_PCT)}%"
        ),
        "validation_strategy": (
            "City-based holdout: cities are partitioned into train / validation / "
            "unseen-test groups so no city contributes cells to more than one split. "
            "This prevents the spatial leakage a random cell-level split would cause."
        ),
        "city_split": {
            "train_cities": split.get("train_cities", []),
            "val_cities": split.get("val_cities", []),
            "test_cities": split.get("test_cities", []),
        },
        "selected_model_metrics": selected,
        "all_model_comparison": (
            test.replace({np.nan: None}).to_dict(orient="records") if test is not None else None
        ),
        "city_wise_performance": (
            city_metrics.replace({np.nan: None}).to_dict(orient="records")
            if city_metrics is not None else None
        ),
        "decision_threshold": operating_threshold(),
        "class_balance_train": run_config.get("class_balance_train"),
        "hyperparameters": run_config.get("best_model_params"),
        "global_feature_importance": explain.global_importances(
            registry.model1_feature_importances()
        ),
        "metrics_source": "reproduced from the training run's saved outputs",
        "limitations": [
            "Spectral indices (NDVI/NDBI) dominate the feature importances, so the "
            "model inherits their sensitivity to season, cloud cover and image date.",
            "Trained on 45 Indian cities; behaviour outside that geography is unvalidated.",
            "Recall at the tuned threshold is moderate, so small or narrow water "
            "bodies are more likely to be missed than falsely reported.",
            "State is a model input, so predictions carry regional priors that may not "
            "transfer to a newly added state.",
        ],
    }
