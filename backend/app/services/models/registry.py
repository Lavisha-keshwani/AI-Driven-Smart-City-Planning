"""
Model registry — loads every trained artifact exactly once.

All four models are process-level singletons behind `lru_cache`, so a request
never pays to deserialise a model or re-read a metrics file. A missing artifact
is not fatal at import time: it is reported through `models_status()` and turns
into a 503 `model_unavailable` on the endpoints that need it.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.core import config
from app.core.errors import ModelUnavailableError

logger = logging.getLogger(__name__)


# ── Generic loaders ──────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | None:
    if not path.exists():
        logger.warning("JSON not found: %s", path.name)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read %s: %s", path.name, exc)
        return None


def _load_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        logger.warning("CSV not found: %s", path.name)
        return None
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        logger.error("Failed to read %s: %s", path.name, exc)
        return None


def _load_estimator(path: Path, label: str) -> Any | None:
    """Deserialise a joblib/pickle estimator, returning None if unavailable."""
    if not path.exists():
        logger.warning("%s artifact not found at %s", label, path)
        return None
    try:
        estimator = joblib.load(path)
    except Exception as exc:  # noqa: BLE001 - any unpickling failure is a load failure
        logger.error("%s failed to load from %s: %s", label, path, exc)
        return None
    logger.info("Loaded %s (%s) from %s", label, type(estimator).__name__, path.name)
    return estimator


def _require(estimator: Any | None, label: str, path: Path, config_key: str) -> Any:
    if estimator is None:
        raise ModelUnavailableError(
            f"{label} is not available. The trained artifact could not be loaded.",
            detail={
                "model": label,
                "expected_file": path.name,
                "config_key": config_key,
                "remedy": f"Set {config_key} in .env to the artifact location.",
            },
        )
    return estimator


# ── Model 1 — Surface Water Monitoring ───────────────────────────────────────

@lru_cache(maxsize=1)
def _model1() -> Any | None:
    return _load_estimator(config.SURFACE_WATER_MODEL_PATH, "Model 1 (Surface Water)")


def surface_water_model() -> Any:
    return _require(
        _model1(), "Model 1 (Surface Water)",
        config.SURFACE_WATER_MODEL_PATH, "SURFACE_WATER_MODEL_PATH",
    )


@lru_cache(maxsize=1)
def model1_feature_list() -> dict:
    return _load_json(config.M1_METRICS_DIR / "feature_list.json") or {}


@lru_cache(maxsize=1)
def model1_thresholds() -> dict:
    return _load_json(config.M1_METRICS_DIR / "thresholds.json") or {}


@lru_cache(maxsize=1)
def model1_city_split() -> dict:
    return _load_json(config.M1_METRICS_DIR / "city_split.json") or {}


@lru_cache(maxsize=1)
def model1_run_config() -> dict:
    """The training run's own configuration record (hyper-parameters, splits)."""
    matches = sorted(config.M1_METRICS_DIR.glob("run_config_*.json"))
    return _load_json(matches[-1]) if matches else {}


@lru_cache(maxsize=1)
def model1_test_metrics() -> pd.DataFrame | None:
    return _load_csv(config.M1_METRICS_DIR / "test_metrics_comparison.csv")


@lru_cache(maxsize=1)
def model1_city_metrics() -> pd.DataFrame | None:
    return _load_csv(config.M1_METRICS_DIR / f"city_wise_performance_{config.M1_ALGORITHM}.csv")


@lru_cache(maxsize=1)
def model1_feature_importances() -> pd.DataFrame | None:
    return _load_csv(config.M1_METRICS_DIR / f"{config.M1_ALGORITHM}_feature_importances.csv")


@lru_cache(maxsize=1)
def model1_water_body_summary() -> pd.DataFrame | None:
    """Per-city surface-water body monitoring summary produced during training."""
    return _load_csv(config.M1_METRICS_DIR / "city_water_body_monitoring_summary.csv")


# ── Model 2 — Urban Expansion Suitability ────────────────────────────────────

@lru_cache(maxsize=1)
def _model2() -> Any | None:
    return _load_estimator(config.URBAN_MODEL_PATH, "Model 2 (Urban Expansion)")


def urban_expansion_model() -> Any:
    return _require(
        _model2(), "Model 2 (Urban Expansion)", config.URBAN_MODEL_PATH, "URBAN_MODEL_PATH"
    )


@lru_cache(maxsize=1)
def model2_config() -> dict:
    cfg = _load_json(config.M2_FEATURES_JSON)
    if cfg is None:
        raise ModelUnavailableError(
            "Model 2 feature list is missing. Its feature order cannot be inferred safely.",
            detail={
                "expected_file": config.M2_FEATURES_JSON.name,
                "config_key": "MODEL2_FEATURES_JSON",
            },
        )
    return cfg


@lru_cache(maxsize=1)
def model2_metrics() -> pd.DataFrame | None:
    return _load_csv(config.M2_METRICS_CSV)


# ── Model 3 — Urban Flood Risk ───────────────────────────────────────────────

@lru_cache(maxsize=1)
def _model3() -> Any | None:
    return _load_estimator(config.FLOOD_MODEL_PATH, "Model 3 (Flood Risk)")


def flood_risk_model() -> Any:
    return _require(
        _model3(), "Model 3 (Flood Risk)", config.FLOOD_MODEL_PATH, "FLOOD_MODEL_PATH"
    )


@lru_cache(maxsize=1)
def model3_feature_list() -> dict:
    return _load_json(config.M3_METRICS_DIR / "feature_list.json") or {}


@lru_cache(maxsize=1)
def model3_thresholds() -> dict:
    return _load_json(config.M3_METRICS_DIR / "thresholds.json") or {}


@lru_cache(maxsize=1)
def model3_city_split() -> dict:
    return _load_json(config.M3_METRICS_DIR / "city_split.json") or {}


@lru_cache(maxsize=1)
def model3_run_config() -> dict:
    matches = sorted(config.M3_METRICS_DIR.glob("run_config_*.json"))
    return _load_json(matches[-1]) if matches else {}


@lru_cache(maxsize=1)
def model3_test_metrics() -> pd.DataFrame | None:
    return _load_csv(config.M3_METRICS_DIR / "test_metrics_comparison.csv")


@lru_cache(maxsize=1)
def model3_city_metrics() -> pd.DataFrame | None:
    return _load_csv(config.M3_METRICS_DIR / f"city_wise_performance_{config.M3_ALGORITHM}.csv")


@lru_cache(maxsize=1)
def model3_feature_importances() -> pd.DataFrame | None:
    return _load_csv(config.M3_METRICS_DIR / f"{config.M3_ALGORITHM}_feature_importances.csv")


# ── Model 4 — Microplastic Screening ─────────────────────────────────────────

@lru_cache(maxsize=1)
def model4_config() -> dict:
    return _load_json(config.M4_CONFIG_JSON) or {}


@lru_cache(maxsize=1)
def model4_cv_results() -> pd.DataFrame | None:
    return _load_csv(config.M4_CV_RESULTS_CSV)


@lru_cache(maxsize=1)
def _model4() -> Any | None:
    """Rebuild the ResNet18 graph and load the trained weights onto the CPU."""
    path = config.MICROPLASTIC_MODEL_PATH
    if not path.exists():
        logger.warning("Model 4 artifact not found at %s", path)
        return None
    try:
        import timm
        import torch

        model = timm.create_model("resnet18", pretrained=False, num_classes=2, in_chans=3)
        state = torch.load(path, map_location="cpu", weights_only=True)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state)
        model.eval()
    except Exception as exc:  # noqa: BLE001 - torch/timm raise many unrelated types
        logger.error("Model 4 failed to load from %s: %s", path, exc)
        return None
    logger.info("Loaded Model 4 (Microplastic ResNet18) from %s", path.name)
    return model


def microplastic_model() -> Any:
    return _require(
        _model4(), "Model 4 (Microplastic Screening)",
        config.MICROPLASTIC_MODEL_PATH, "MICROPLASTIC_MODEL_PATH",
    )


# ── Status reporting ─────────────────────────────────────────────────────────

def _entry(label: str, kind: str, path: Path, estimator: Any | None) -> dict:
    return {
        "name": label,
        "kind": kind,
        "loaded": estimator is not None,
        "artifact_present": path.exists(),
        "artifact": path.name,
        "implementation": type(estimator).__name__ if estimator is not None else None,
    }


def models_status() -> dict:
    """Load-state of every model, for /health and /api/models/status."""
    m1, m2, m3 = _model1(), _model2(), _model3()
    m4 = _model4()
    models = {
        "model1_surface_water": _entry(
            "Surface Water Monitoring", "classifier",
            config.SURFACE_WATER_MODEL_PATH, m1,
        ),
        "model2_urban_expansion": _entry(
            "Urban Expansion Suitability", "classifier", config.URBAN_MODEL_PATH, m2,
        ),
        "model3_flood_risk": _entry(
            "Urban Flood Risk", "classifier", config.FLOOD_MODEL_PATH, m3,
        ),
        "model4_microplastic": _entry(
            "Microplastic Screening", "cnn", config.MICROPLASTIC_MODEL_PATH, m4,
        ),
    }
    datasets = {
        "model1_dataset": config.M1_DATASET.exists(),
        "model3_dataset": config.M3_DATASET.exists(),
        "grid_metadata": config.GRID_METADATA_CSV.exists(),
        "ghsl_layers": config.GHSL_DIR.exists(),
        "open_buildings": config.OPEN_BUILDINGS_DIR.exists(),
        "srtm": config.SRTM_CSV.exists(),
        "chirps": config.CHIRPS_DIR.exists(),
        "surface_water_layer": config.SURFACE_WATER_LAYER_CSV.exists(),
    }
    return {
        "models": models,
        "datasets": datasets,
        "all_models_loaded": all(m["loaded"] for m in models.values()),
        "all_datasets_present": all(datasets.values()),
    }


def warm_up() -> dict:
    """Eagerly load every model so the first request is not the slow one."""
    status = models_status()
    logger.info(
        "Model warm-up: %d/%d models loaded, %d/%d datasets present",
        sum(m["loaded"] for m in status["models"].values()), len(status["models"]),
        sum(status["datasets"].values()), len(status["datasets"]),
    )
    return status
