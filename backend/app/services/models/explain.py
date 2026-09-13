"""
Feature attribution for the three tree-based models.

Per-prediction attributions come from SHAP's TreeExplainer. Models 1 and 3 are
sklearn Pipelines (ColumnTransformer + tree ensemble), so the row is transformed
first and the explainer runs on the final estimator with the transformed feature
names; one-hot columns are folded back onto their source feature so the caller
sees `state`, not `state_Kerala`. Model 2 is a bare LightGBM classifier, so its
raw features go straight in.

If SHAP is not installed or an explainer cannot be constructed, the caller gets
`None` and the API reports attributions as unavailable. Nothing is invented.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_ONE_HOT_JOINER = "_"


@lru_cache(maxsize=1)
def shap_available() -> bool:
    try:
        import shap  # noqa: F401
    except ImportError:
        logger.warning("shap is not installed — feature attributions will be unavailable")
        return False
    return True


def _final_estimator(model: Any) -> tuple[Any, Any | None]:
    """Split a Pipeline into (tree estimator, preprocessor) or (model, None)."""
    steps = getattr(model, "named_steps", None)
    if not steps:
        return model, None
    preprocessor = steps.get("preprocess")
    estimator = steps.get("clf")
    if estimator is None:
        *_, estimator = steps.values()
    return estimator, preprocessor


def _transformed_names(preprocessor: Any, fallback: list[str]) -> list[str]:
    try:
        return [str(n) for n in preprocessor.get_feature_names_out()]
    except Exception:  # noqa: BLE001 - older transformers may not implement it
        return fallback


def _source_feature(transformed_name: str, raw_features: list[str]) -> str:
    """Map a transformed column name back to the raw feature it came from."""
    name = transformed_name.split("__", 1)[-1]  # strip ColumnTransformer prefix
    if name in raw_features:
        return name
    # One-hot columns look like "state_Kerala"; match the longest raw-feature prefix.
    candidates = [f for f in raw_features if name.startswith(f + _ONE_HOT_JOINER)]
    return max(candidates, key=len) if candidates else name


@lru_cache(maxsize=8)
def _explainer(model_key: str, model_id: int, model: Any):
    """Build and cache a TreeExplainer. `model_id` keeps the cache key unique."""
    import shap

    estimator, _ = _final_estimator(model)
    explainer = shap.TreeExplainer(estimator)
    logger.info("Built SHAP TreeExplainer for %s (%s)", model_key, type(estimator).__name__)
    return explainer


def _shap_row(model_key: str, model: Any, X: pd.DataFrame, class_index: int):
    """SHAP values for a single row, as (values, feature_names)."""
    estimator, preprocessor = _final_estimator(model)
    raw_features = list(X.columns)

    if preprocessor is not None:
        matrix = preprocessor.transform(X)
        if hasattr(matrix, "toarray"):
            matrix = matrix.toarray()
        names = _transformed_names(preprocessor, raw_features)
        data = pd.DataFrame(np.asarray(matrix, dtype=float), columns=names)
    else:
        data = X.astype(float)
        names = raw_features

    explainer = _explainer(model_key, id(model), model)
    values = explainer.shap_values(data, check_additivity=False)

    arr = np.asarray(values)
    # Shapes seen in practice: (1, n), (1, n, n_classes), (n_classes, 1, n).
    if arr.ndim == 3:
        arr = arr[0, :, class_index] if arr.shape[0] == 1 else arr[class_index, 0, :]
    elif arr.ndim == 2:
        arr = arr[0]
    return np.asarray(arr, dtype=float), names


def explain_prediction(
    model_key: str,
    model: Any,
    X: pd.DataFrame,
    *,
    class_index: int = 1,
    top_n: int = 8,
) -> list[dict] | None:
    """Top contributing features for one prediction.

    Returns a list of `{feature, importance, direction, shap_value}`, ordered by
    absolute contribution. `importance` is the share of the row's total absolute
    attribution, so the values sum to at most 1 across all features. `direction`
    is "positive" when the feature pushed the prediction towards the class of
    interest and "negative" when it pushed away. Returns None if SHAP cannot run.
    """
    if not shap_available():
        return None
    try:
        values, names = _shap_row(model_key, model, X, class_index)
    except Exception as exc:  # noqa: BLE001 - SHAP raises many estimator-specific types
        logger.warning("SHAP attribution failed for %s: %s", model_key, exc)
        return None

    if values.shape[0] != len(names):
        logger.warning(
            "SHAP returned %d values for %d features on %s — skipping attribution",
            values.shape[0], len(names), model_key,
        )
        return None

    raw_features = list(X.columns)
    # Fold one-hot columns back onto their source feature, summing contributions.
    folded: dict[str, float] = {}
    for name, value in zip(names, values):
        source = _source_feature(name, raw_features)
        folded[source] = folded.get(source, 0.0) + float(value)

    total = sum(abs(v) for v in folded.values())
    if total == 0:
        return []

    ranked = sorted(folded.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
    return [
        {
            "feature": feature,
            "importance": round(abs(value) / total, 4),
            "direction": "positive" if value > 0 else "negative" if value < 0 else "neutral",
            "shap_value": round(value, 6),
        }
        for feature, value in ranked
    ]


def global_importances(frame: pd.DataFrame | None, top_n: int = 15) -> list[dict] | None:
    """Normalise a training-time feature-importance CSV into API shape."""
    if frame is None or frame.empty:
        return None
    df = frame.copy()
    if df.shape[1] < 2:
        return None
    feature_col, value_col = df.columns[0], df.columns[1]
    df = df.rename(columns={feature_col: "feature", value_col: "importance"})
    df = df[["feature", "importance"]].dropna().head(top_n)
    return [
        {"feature": str(r.feature), "importance": round(float(r.importance), 6)}
        for r in df.itertuples()
    ]
