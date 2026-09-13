"""
Feature store — assembles each model's inference feature table from the same
source layers its training pipeline consumed.

Models 1 and 3 shipped pre-merged datasets, so those are read directly. Model 2
did not, so its table is rebuilt here from GHSL, Open Buildings, SRTM and CHIRPS
joined on `grid_id`. All three tables are cached for the process lifetime.

Two invariants this module enforces:

  * Feature ORDER comes from the fitted estimator itself (`feature_names_in_`,
    or the LightGBM booster's own feature names), never from a hand-written
    list that could drift out of sync with the artifact.
  * Missing values are left as NaN. Both model families handle NaN natively, and
    imputing a plausible value here would fabricate evidence the model then
    treats as observed.
"""

from __future__ import annotations

import glob
import logging
from functools import lru_cache

import pandas as pd

from app.core import config
from app.core.errors import DatasetUnavailableError, GridNotFoundError
from app.services.models import registry

logger = logging.getLogger(__name__)


def _read_csv(path, label: str, config_key: str) -> pd.DataFrame:
    if not path.exists():
        raise DatasetUnavailableError(
            f"{label} is required for inference but was not found.",
            detail={"expected_file": path.name, "config_key": config_key},
        )
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise DatasetUnavailableError(
            f"{label} could not be parsed.",
            detail={"file": path.name, "reason": str(exc)},
        ) from exc


def model_feature_order(model) -> list[str]:
    """Recover the exact training-time feature order from a fitted estimator."""
    names = getattr(model, "feature_names_in_", None)
    if names is not None:
        return [str(n) for n in names]
    booster = getattr(model, "booster_", None)
    if booster is not None:
        return list(booster.feature_name())
    raise DatasetUnavailableError(
        "The trained estimator does not record its feature names, so the "
        "inference feature order cannot be verified against training.",
        detail={"estimator": type(model).__name__},
    )


# ── Model 1 — Surface Water ──────────────────────────────────────────────────

@lru_cache(maxsize=1)
def surface_water_table() -> pd.DataFrame:
    """Pre-merged Model 1 grid dataset, with the binary target materialised.

    `is_water_body` is the training target: a cell counts as a water body when
    the Global Surface Water occurrence at that cell meets the threshold the
    training run recorded. It is an observation, not a prediction.
    """
    df = _read_csv(config.M1_DATASET, "Model 1 grid dataset", "MODEL1_DATASET")
    df = df.drop_duplicates("grid_id").reset_index(drop=True)

    threshold = float(
        registry.model1_feature_list().get(
            "water_occurrence_threshold", config.WATER_OCCURRENCE_THRESHOLD_PCT
        )
    )
    if "is_water_body" not in df.columns and "water_occurrence_pct" in df.columns:
        df["is_water_body"] = (df["water_occurrence_pct"] >= threshold).astype(int)

    logger.info("Model 1 feature table: %d cells, %d columns", len(df), df.shape[1])
    return df


# ── Model 3 — Flood Risk ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def flood_risk_table() -> pd.DataFrame:
    """Pre-merged Model 3 grid dataset (flood labels + all predictors)."""
    df = _read_csv(config.M3_DATASET, "Model 3 grid dataset", "MODEL3_DATASET")
    df = df.drop_duplicates("grid_id").reset_index(drop=True)
    logger.info("Model 3 feature table: %d cells, %d columns", len(df), df.shape[1])
    return df


# ── Model 2 — Urban Expansion ────────────────────────────────────────────────

def _open_buildings() -> pd.DataFrame:
    """Concatenate the per-city Open Buildings exports into one table."""
    files = sorted(glob.glob(str(config.OPEN_BUILDINGS_DIR / "openbuildings_*.csv")))
    if not files:
        raise DatasetUnavailableError(
            "No Open Buildings exports found. Model 2 requires building-density "
            "features and will not substitute zeros for them.",
            detail={
                "expected_pattern": "openbuildings_*.csv",
                "config_key": "OPEN_BUILDINGS_DIR",
            },
        )
    cols = ["grid_id", "building_count_total", "building_height_mean", "building_presence_mean"]
    frames = []
    for path in files:
        frame = pd.read_csv(path)
        missing = [c for c in cols if c not in frame.columns]
        if missing:
            raise DatasetUnavailableError(
                "An Open Buildings export is missing required columns.",
                detail={"file": path.rsplit("\\", 1)[-1], "missing_columns": missing},
            )
        frames.append(frame[cols])
    ob = pd.concat(frames, ignore_index=True).drop_duplicates("grid_id")
    logger.info("Open Buildings: %d cells from %d city exports", len(ob), len(files))
    return ob


@lru_cache(maxsize=1)
def urban_expansion_table() -> pd.DataFrame:
    """Rebuild the Model 2 feature table from its source layers.

    Layers, matching the training pipeline:
      GHSL built_fraction at T0 (the historical state)  -> built_t0
      Open Buildings                                    -> building density/height
      SRTM                                              -> elevation, slope, depression
      CHIRPS                                            -> annual rainfall
      Grid registry                                     -> lat, lon, is_core, city, state

    `built_t1` (the later GHSL epoch) is joined too. It is not a model input —
    it is the observation the forward-validation target is derived from, and the
    evaluation pipeline reads it from here.

    `city_code`/`state_code` are the alphabetical category codes pandas assigns
    over the full 45-city grid, which is what the training script produced. That
    reconstruction was verified against the trained model: predictions agree with
    the tercile-binned GHSL growth target on 85.4% of cells, against the 83.5%
    test accuracy the training run reported.
    """
    meta = _read_csv(config.GRID_METADATA_CSV, "Grid metadata", "GRID_METADATA_CSV")
    meta = meta[["grid_id", "city", "state", "lat", "lon", "is_core"]].drop_duplicates("grid_id")

    ghsl_t0 = _read_csv(
        config.GHSL_DIR / f"ghsl_features_{config.M2_T0_YEAR}_FIXED.csv",
        f"GHSL built-up layer for T0 ({config.M2_T0_YEAR})", "GHSL_DIR",
    )[["grid_id", "built_fraction"]].rename(columns={"built_fraction": "built_t0"})

    ghsl_t1 = _read_csv(
        config.GHSL_DIR / f"ghsl_features_{config.M2_T1_YEAR}_FIXED.csv",
        f"GHSL built-up layer for T1 ({config.M2_T1_YEAR})", "GHSL_DIR",
    )[["grid_id", "built_fraction"]].rename(columns={"built_fraction": "built_t1"})

    srtm = _read_csv(config.SRTM_CSV, "SRTM terrain layer", "SRTM_CSV")[
        ["grid_id", "elevation_m", "slope_deg", "depression_index_m"]
    ]
    chirps = _read_csv(
        config.CHIRPS_DIR / f"chirps_features_{config.M2_RAINFALL_YEAR}.csv",
        f"CHIRPS rainfall layer ({config.M2_RAINFALL_YEAR})", "CHIRPS_DIR",
    )[["grid_id", "rainfall_annual_mm"]]

    df = (
        meta.merge(ghsl_t0, on="grid_id", how="left")
        .merge(ghsl_t1, on="grid_id", how="left")
        .merge(_open_buildings(), on="grid_id", how="left")
        .merge(srtm.drop_duplicates("grid_id"), on="grid_id", how="left")
        .merge(chirps.drop_duplicates("grid_id"), on="grid_id", how="left")
    )

    # Alphabetical category codes over the full grid — the training-time encoding.
    df["city_code"] = df["city"].astype("category").cat.codes
    df["state_code"] = df["state"].astype("category").cat.codes

    # Growth between the two GHSL epochs: the forward-validation observation.
    df["built_growth_t0_t1"] = df["built_t1"] - df["built_t0"]

    incomplete = int(df[model_feature_order(registry.urban_expansion_model())].isna().any(axis=1).sum())
    logger.info(
        "Model 2 feature table: %d cells, %d columns (%d cells with incomplete features)",
        len(df), df.shape[1], incomplete,
    )
    return df


# ── Row lookup ───────────────────────────────────────────────────────────────

def _row(table: pd.DataFrame, grid_id: str, model_label: str) -> pd.Series:
    hit = table[table["grid_id"] == grid_id]
    if hit.empty:
        raise GridNotFoundError(
            f"grid_id '{grid_id}' is not present in the {model_label} feature table.",
            detail={"model": model_label, "grid_id": grid_id},
        )
    return hit.iloc[0]


def surface_water_row(grid_id: str) -> pd.Series:
    return _row(surface_water_table(), grid_id, "Surface Water (Model 1)")


def urban_expansion_row(grid_id: str) -> pd.Series:
    return _row(urban_expansion_table(), grid_id, "Urban Expansion (Model 2)")


def flood_risk_row(grid_id: str) -> pd.Series:
    return _row(flood_risk_table(), grid_id, "Flood Risk (Model 3)")


def subset_for_city(table: pd.DataFrame, city: str) -> pd.DataFrame:
    """All rows for one city, matched case-insensitively."""
    hit = table[table["city"].astype(str).str.lower() == city.strip().lower()]
    if hit.empty:
        raise GridNotFoundError(
            f"No grid cells for city '{city}' in this feature table.",
            detail={"city": city},
        )
    return hit
