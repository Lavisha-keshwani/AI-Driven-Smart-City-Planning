"""
Model 3 — Urban Flood Risk.

The trained artifact is a Random Forest inside an sklearn Pipeline that predicts
flood susceptibility for a 1 km cell from terrain (SRTM elevation, slope,
depression index), Global Surface Water statistics, the GHSL built-up time series
(1975 through 2020 plus growth), Open Buildings density, and CHIRPS rainfall
climatology. Labels come from the Global Flood Database observed-inundation record.

Validation is city-based, which matters here more than anywhere else in the
project: neighbouring 1 km cells are strongly spatially correlated, so a random
cell-level split would let the model see the same flood event from both sides of
the split and report inflated skill. The training run partitioned the 45 cities
into disjoint train / validation / unseen-test groups, and the metrics this module
reports come from that unseen-city test group.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.core import config
from app.core.errors import InferenceError
from app.services.models import explain, feature_store, registry

logger = logging.getLogger(__name__)

MODEL_KEY = "model3_flood_risk"
MODEL_NAME = "Urban Flood Risk"

RISK_MEANING = {
    "HIGH": "High flood susceptibility — development should be restricted or heavily mitigated",
    "MODERATE": "Moderate flood susceptibility — resilience measures required",
    "LOW": "Low flood susceptibility — standard drainage design expected to suffice",
}


def operating_threshold() -> float:
    """The decision threshold the training run tuned for the selected algorithm."""
    thresholds = registry.model3_thresholds()
    value = thresholds.get(config.M3_ALGORITHM)
    if value is None:
        raise InferenceError(
            "Model 3 has no tuned decision threshold for the configured algorithm, "
            "so a flood classification cannot be issued.",
            detail={"algorithm": config.M3_ALGORITHM, "available": sorted(thresholds)},
        )
    return float(value)


def feature_order() -> list[str]:
    return feature_store.model_feature_order(registry.flood_risk_model())


def _clean(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(number) else round(number, 6)


def risk_level(probability: float) -> str:
    """Band a flood probability into LOW / MODERATE / HIGH.

    Band edges are configurable (FLOOD_RISK_MODERATE_THRESHOLD,
    FLOOD_RISK_HIGH_THRESHOLD) and documented in the model card. The defaults
    bracket the tuned operating threshold (0.572), so MODERATE spans the region
    around the decision boundary where the model is least certain, HIGH sits
    clearly above it, and LOW clearly below.
    """
    if probability >= config.FLOOD_RISK_HIGH_THRESHOLD:
        return "HIGH"
    if probability >= config.FLOOD_RISK_MODERATE_THRESHOLD:
        return "MODERATE"
    return "LOW"


def _drivers(row: pd.Series) -> list[dict]:
    """Measured physical conditions relevant to flooding at this cell.

    Deterministic readings of the input layers, provided so an explanation can
    cite evidence rather than paraphrasing the probability back at the reader.
    """
    out = []
    elevation = _clean(row.get("elevation_m"))
    slope = _clean(row.get("slope_deg"))
    depression = _clean(row.get("depression_index_m"))
    water_occurrence = _clean(row.get("water_occurrence_pct"))
    rainfall_max = _clean(row.get("rainfall_annual_mm_max"))
    built_2020 = _clean(row.get("built_fraction_2020"))
    built_growth = _clean(row.get("built_fraction_growth"))

    if elevation is not None and elevation < 20:
        out.append({
            "driver": "low_elevation",
            "reason": f"Elevation of {elevation:.0f} m leaves little gravity drainage head.",
            "measured": {"elevation_m": elevation},
        })
    if slope is not None and slope < 1:
        out.append({
            "driver": "flat_terrain",
            "reason": f"Slope of {slope:.2f} degrees means water drains away slowly.",
            "measured": {"slope_deg": slope},
        })
    if depression is not None and depression >= 2:
        out.append({
            "driver": "local_depression",
            "reason": f"The cell sits {depression:.1f} m below its surroundings, so water pools.",
            "measured": {"depression_index_m": depression},
        })
    if water_occurrence is not None and water_occurrence > 5:
        out.append({
            "driver": "surface_water_presence",
            "reason": (
                f"Surface water is present here {water_occurrence:.0f}% of the time, "
                f"indicating proximity to a channel or water body."
            ),
            "measured": {"water_occurrence_pct": water_occurrence},
        })
    if rainfall_max is not None and rainfall_max >= 1200:
        out.append({
            "driver": "high_rainfall_exposure",
            "reason": f"Wettest year on record delivered {rainfall_max:.0f} mm of rainfall.",
            "measured": {"rainfall_annual_mm_max": rainfall_max},
        })
    if built_2020 is not None and built_2020 >= 0.4:
        out.append({
            "driver": "impervious_surface",
            "reason": (
                f"{built_2020 * 100:.0f}% of the cell is built up, so rainfall runs off "
                f"rather than infiltrating."
            ),
            "measured": {"built_fraction_2020": built_2020},
        })
    if built_growth is not None and built_growth >= 0.1:
        out.append({
            "driver": "rapid_urbanisation",
            "reason": (
                "Built-up area grew sharply over the GHSL record, which typically "
                "outpaces drainage upgrades."
            ),
            "measured": {"built_fraction_growth": built_growth},
        })
    return out


def predict(grid_id: str, *, explain_prediction: bool = True) -> dict:
    """Predict flood susceptibility for one grid cell."""
    model = registry.flood_risk_model()
    row = feature_store.flood_risk_row(grid_id)
    features = feature_order()

    missing = [f for f in features if f not in row.index]
    if missing:
        raise InferenceError(
            "The Model 3 feature table is missing columns the trained model requires.",
            detail={"missing_features": missing},
        )

    X = row[features].to_frame().T
    incomplete = [f for f in features if pd.isna(row[f])]

    try:
        probability = float(model.predict_proba(X)[0, 1])
    except Exception as exc:  # noqa: BLE001
        raise InferenceError(
            f"Model 3 inference failed for grid cell {grid_id}.",
            detail={"reason": str(exc)},
        ) from exc

    threshold = operating_threshold()
    level = risk_level(probability)

    result = {
        "model": MODEL_NAME,
        "model_key": MODEL_KEY,
        "algorithm": config.M3_ALGORITHM,
        "grid_id": str(row["grid_id"]),
        "city": str(row.get("city", "unknown")),
        "state": str(row.get("state", "unknown")),
        "lat": _clean(row.get("lat")),
        "lon": _clean(row.get("lon")),
        # Model output
        "flood_probability": round(probability, 4),
        "risk_level": level,
        "risk_meaning": RISK_MEANING[level],
        "flood_predicted": bool(probability >= threshold),
        "decision_threshold": round(threshold, 4),
        "risk_bands": {
            "high_at_or_above": config.FLOOD_RISK_HIGH_THRESHOLD,
            "moderate_at_or_above": config.FLOOD_RISK_MODERATE_THRESHOLD,
        },
        # Observed context
        "observed": {
            "historical_flood_label": (
                int(row["flood_label"]) if "flood_label" in row.index
                and pd.notna(row.get("flood_label")) else None
            ),
            "historical_flood_events": _clean(row.get("flood_event_count")),
            "historical_flood_fraction": _clean(row.get("flood_fraction")),
            "flood_record_source": (
                str(row.get("flood_source")) if pd.notna(row.get("flood_source")) else None
            ),
            "flood_record_period": (
                str(row.get("flood_period")) if pd.notna(row.get("flood_period")) else None
            ),
            "elevation_m": _clean(row.get("elevation_m")),
            "slope_deg": _clean(row.get("slope_deg")),
            "depression_index_m": _clean(row.get("depression_index_m")),
            "water_occurrence_pct": _clean(row.get("water_occurrence_pct")),
            "rainfall_annual_mm_mean": _clean(row.get("rainfall_annual_mm_mean")),
            "rainfall_annual_mm_max": _clean(row.get("rainfall_annual_mm_max")),
            "built_fraction_2020": _clean(row.get("built_fraction_2020")),
        },
        "risk_drivers": _drivers(row),
        "incomplete_features": incomplete,
    }

    if explain_prediction:
        result["feature_attribution"] = explain.explain_prediction(
            MODEL_KEY, model, X, class_index=1
        )

    logger.info(
        "Model 3 %s: p=%.4f -> %s (threshold %.4f)", grid_id, probability, level, threshold
    )
    return result


def predict_city(city: str, *, limit: int | None = None) -> list[dict]:
    """Batch-predict flood risk for every cell in a city."""
    model = registry.flood_risk_model()
    table = feature_store.subset_for_city(feature_store.flood_risk_table(), city)
    if limit is not None:
        table = table.head(limit)

    features = feature_order()
    probabilities = model.predict_proba(table[features])[:, 1]

    records = []
    for (_, row), probability in zip(table.iterrows(), probabilities):
        probability = float(probability)
        records.append(
            {
                "grid_id": str(row["grid_id"]),
                "city": str(row.get("city", "unknown")),
                "lat": _clean(row.get("lat")),
                "lon": _clean(row.get("lon")),
                "flood_probability": round(probability, 4),
                "risk_level": risk_level(probability),
                "historical_flood_label": (
                    int(row["flood_label"]) if "flood_label" in row.index
                    and pd.notna(row.get("flood_label")) else None
                ),
            }
        )
    distribution: dict[str, int] = {}
    for r in records:
        distribution[r["risk_level"]] = distribution.get(r["risk_level"], 0) + 1
    logger.info("Model 3 batch for %s: %d cells, distribution=%s", city, len(records), distribution)
    return records


def metrics() -> dict:
    """Validation evidence for Model 3."""
    test = registry.model3_test_metrics()
    run_config = registry.model3_run_config()
    split = registry.model3_city_split()
    city_metrics = registry.model3_city_metrics()

    selected = None
    if test is not None and "model" in test.columns:
        match = test[test["model"] == config.M3_ALGORITHM]
        if not match.empty:
            selected = match.iloc[0].replace({np.nan: None}).to_dict()

    return {
        "model": MODEL_NAME,
        "algorithm": config.M3_ALGORITHM,
        "task": "binary classification — flood susceptibility of a 1 km cell",
        "target": registry.model3_feature_list().get("target", "flood_label"),
        "target_definition": (
            "Observed inundation from the Global Flood Database, aggregated onto the "
            "1 km analysis grid"
        ),
        "validation_strategy": (
            "City-based holdout. The 45 cities are partitioned into disjoint train, "
            "validation and unseen-test groups, so no city contributes cells to more "
            "than one split. A random cell-level split would leak spatially — adjacent "
            "1 km cells share the same flood events — and would overstate performance."
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
        "risk_bands": {
            "high_at_or_above": config.FLOOD_RISK_HIGH_THRESHOLD,
            "moderate_at_or_above": config.FLOOD_RISK_MODERATE_THRESHOLD,
            "rationale": (
                "Bands bracket the tuned operating threshold so MODERATE covers the "
                "uncertain region around the decision boundary."
            ),
        },
        "class_balance_train": run_config.get("class_balance_train"),
        "hyperparameters": run_config.get("best_model_params"),
        "global_feature_importance": explain.global_importances(
            registry.model3_feature_importances()
        ),
        "metrics_source": "reproduced from the training run's saved outputs",
        "data_sources": [
            "Global Flood Database (observed inundation labels)",
            "SRTM (elevation, slope, depression index)",
            "CHIRPS (rainfall climatology, annual and monthly)",
            "Global Surface Water (occurrence, seasonality, recurrence, extent)",
            "GHSL (built-up time series 1975-2020)",
            "Google Open Buildings (building count, height, presence)",
        ],
        "limitations": [
            "Flood labels come from satellite-observed inundation, whose detection "
            "quality varies with cloud cover, revisit timing and event duration. "
            "Absence of a label is not proof a cell never flooded.",
            "Labels cover 2000-2018, so drainage built after that period is not reflected.",
            "Performance varies substantially by city; consult city_wise_performance "
            "before relying on a result for a specific city.",
            "Pluvial (drainage-capacity) flooding is only implicitly represented, "
            "through built-up fraction and rainfall, not through sewer network data.",
            "Recall at the tuned threshold is moderate, so a LOW result should be read "
            "as absence of evidence rather than evidence of safety.",
        ],
    }
