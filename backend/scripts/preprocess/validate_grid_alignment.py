"""
Validate that every source layer aligns on the common 1 km grid.

    input          the grid registry and every source layer
    checks         grid_id coverage, duplicate keys, coordinate agreement,
                   CRS consistency, value ranges, missing-value accounting
    output         a pass/fail report printed as tables and written as JSON

Why this exists. Every model in this project is joined by `grid_id`, so a silent
misalignment — a layer covering different cells, duplicated keys inflating a join, or
coordinates disagreeing between exports — would corrupt features without raising an
error anywhere. This script is the guard: it verifies the spatial framework holds before
any feature table is trusted, and reports a non-zero exit code if it does not.

Usage:
    python -m scripts.preprocess.validate_grid_alignment
    python -m scripts.preprocess.validate_grid_alignment --out build/
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import config  # noqa: E402
from app.core.grid import grid_metadata  # noqa: E402

# Tolerance for centroid agreement between layers, in degrees. 1e-6 degrees is about
# 0.11 m, far finer than the 1 km cell, so anything looser indicates a real mismatch.
COORDINATE_TOLERANCE_DEG = 1e-6

# Physically plausible ranges. A value outside these is a data problem, not a model one.
VALUE_RANGES = {
    "elevation_m": (-500, 9000),
    "slope_deg": (0, 90),
    "water_occurrence_pct": (0, 100),
    "water_recurrence_pct": (0, 100),
    "water_fraction": (0, 1),
    "built_fraction": (0, 1),
    "built_fraction_2020": (0, 1),
    "rainfall_annual_mm": (0, 15000),
    "building_presence_mean": (0, 1),
    "lat": (-90, 90),
    "lon": (-180, 180),
}


def _layers() -> dict[str, Path]:
    """Every source layer, keyed by name. Open Buildings and CHIRPS are globbed."""
    layers = {
        "grid_registry": config.GRID_METADATA_CSV,
        "srtm": config.SRTM_CSV,
        "surface_water": config.SURFACE_WATER_LAYER_CSV,
        "model1_dataset": config.M1_DATASET,
        "model3_dataset": config.M3_DATASET,
    }
    for year in (1975, 1990, 2000, 2015, 2020):
        path = config.GHSL_DIR / f"ghsl_features_{year}_FIXED.csv"
        if path.exists():
            layers[f"ghsl_{year}"] = path
    for path in sorted(config.CHIRPS_DIR.glob("chirps_features_*.csv")):
        layers[f"chirps_{path.stem.split('_')[-1]}"] = path
    return layers


def _load(name: str, path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        print(f"  {name:24s} UNREADABLE: {exc}")
        return None


def _open_buildings() -> pd.DataFrame | None:
    files = sorted(glob.glob(str(config.OPEN_BUILDINGS_DIR / "openbuildings_*.csv")))
    if not files:
        return None
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Directory for the JSON report.")
    args = parser.parse_args()

    print("=" * 78)
    print("Spatial framework validation")
    print("=" * 78)
    print(f"\nGrid: {config.GRID_CELL_SIZE_M} m cells, CRS {config.GRID_CRS}")

    registry = grid_metadata()
    reference = set(registry["grid_id"])
    print(f"Registry: {len(registry):,} cells across {registry['city'].nunique()} cities")

    report: dict = {
        "grid": {
            "cell_size_m": config.GRID_CELL_SIZE_M,
            "crs": config.GRID_CRS,
            "cells": int(len(registry)),
            "cities": int(registry["city"].nunique()),
        },
        "layers": {},
        "failures": [],
    }

    def fail(message: str) -> None:
        report["failures"].append(message)
        print(f"  FAIL: {message}")

    # ── Registry integrity ───────────────────────────────────────────────────
    print("\n[1] Registry integrity")
    if registry["grid_id"].duplicated().any():
        fail(f"Registry has {int(registry['grid_id'].duplicated().sum())} duplicate grid_ids")
    else:
        print("  grid_id is unique")

    for column in ("lat", "lon"):
        low, high = VALUE_RANGES[column]
        outside = int(((registry[column] < low) | (registry[column] > high)).sum())
        if outside:
            fail(f"Registry has {outside} cells with {column} outside [{low}, {high}]")
    print("  coordinates are within the valid geographic domain")

    # ── Per-layer alignment ──────────────────────────────────────────────────
    print("\n[2] Layer alignment on grid_id")
    layers = _layers()
    frames: dict[str, pd.DataFrame] = {}

    for name, path in layers.items():
        if not path.exists():
            print(f"  {name:24s} MISSING  {path.name}")
            report["layers"][name] = {"present": False, "file": path.name}
            continue
        frame = _load(name, path)
        if frame is None or "grid_id" not in frame.columns:
            fail(f"{name} has no grid_id column")
            continue
        frames[name] = frame

        ids = set(frame["grid_id"])
        duplicates = int(frame["grid_id"].duplicated().sum())
        missing_from_layer = len(reference - ids)
        extra_in_layer = len(ids - reference)

        entry = {
            "present": True,
            "file": path.name,
            "rows": int(len(frame)),
            "unique_grid_ids": len(ids),
            "duplicate_grid_ids": duplicates,
            "registry_cells_absent": missing_from_layer,
            "cells_not_in_registry": extra_in_layer,
            "coverage_fraction": round(len(ids & reference) / max(len(reference), 1), 6),
        }
        report["layers"][name] = entry

        status = "ok"
        if duplicates:
            status = "DUPLICATES"
            fail(f"{name} has {duplicates} duplicate grid_ids, which would inflate a join")
        if extra_in_layer:
            status = "EXTRA CELLS"
            fail(f"{name} has {extra_in_layer} grid_ids absent from the registry")
        if missing_from_layer:
            status = f"{entry['coverage_fraction']:.1%} coverage"

        print(
            f"  {name:24s} {entry['rows']:>8,} rows  "
            f"coverage {entry['coverage_fraction']:>7.2%}  {status}"
        )

    # Open Buildings is many files, so it is checked separately.
    open_buildings = _open_buildings()
    if open_buildings is None:
        print(f"  {'open_buildings':24s} MISSING")
        report["layers"]["open_buildings"] = {"present": False}
    else:
        ids = set(open_buildings["grid_id"])
        duplicates = int(open_buildings["grid_id"].duplicated().sum())
        entry = {
            "present": True,
            "files": len(glob.glob(str(config.OPEN_BUILDINGS_DIR / "openbuildings_*.csv"))),
            "rows": int(len(open_buildings)),
            "unique_grid_ids": len(ids),
            "duplicate_grid_ids": duplicates,
            "cells_not_in_registry": len(ids - reference),
            "coverage_fraction": round(len(ids & reference) / max(len(reference), 1), 6),
        }
        report["layers"]["open_buildings"] = entry
        frames["open_buildings"] = open_buildings
        if duplicates:
            fail(f"open_buildings has {duplicates} duplicate grid_ids across its city files")
        print(
            f"  {'open_buildings':24s} {entry['rows']:>8,} rows  "
            f"coverage {entry['coverage_fraction']:>7.2%}  "
            f"({entry['files']} city files)"
        )

    # ── Coordinate agreement ─────────────────────────────────────────────────
    print(f"\n[3] Coordinate agreement with the registry (tolerance {COORDINATE_TOLERANCE_DEG})")
    registry_coords = registry.set_index("grid_id")[["lat", "lon"]]

    for name, frame in frames.items():
        if name == "grid_registry" or not {"lat", "lon"} <= set(frame.columns):
            continue
        layer_coords = frame.drop_duplicates("grid_id").set_index("grid_id")[["lat", "lon"]]
        common = registry_coords.index.intersection(layer_coords.index)
        if not len(common):
            continue

        delta_lat = (registry_coords.loc[common, "lat"] - layer_coords.loc[common, "lat"]).abs()
        delta_lon = (registry_coords.loc[common, "lon"] - layer_coords.loc[common, "lon"]).abs()
        worst = float(max(delta_lat.max(), delta_lon.max()))
        mismatched = int(
            ((delta_lat > COORDINATE_TOLERANCE_DEG) | (delta_lon > COORDINATE_TOLERANCE_DEG)).sum()
        )

        report["layers"][name]["max_coordinate_delta_deg"] = worst
        report["layers"][name]["cells_with_coordinate_mismatch"] = mismatched

        if mismatched:
            fail(
                f"{name} disagrees with the registry on {mismatched} cell centroids "
                f"(worst {worst:.3e} degrees), so it may be on a different grid"
            )
        else:
            print(f"  {name:24s} agrees (worst delta {worst:.3e} degrees)")

    # ── Value ranges ─────────────────────────────────────────────────────────
    print("\n[4] Value ranges")
    range_issues = []
    for name, frame in frames.items():
        for column, (low, high) in VALUE_RANGES.items():
            if column not in frame.columns:
                continue
            values = pd.to_numeric(frame[column], errors="coerce")
            outside = int(((values < low) | (values > high)).sum())
            if outside:
                range_issues.append({
                    "layer": name, "column": column, "outside_range": outside,
                    "expected": [low, high],
                    "observed_min": float(values.min()), "observed_max": float(values.max()),
                })
    report["value_range_issues"] = range_issues
    if range_issues:
        print(pd.DataFrame(range_issues).to_string(index=False))
        for issue in range_issues:
            fail(
                f"{issue['layer']}.{issue['column']} has {issue['outside_range']} values "
                f"outside {issue['expected']}"
            )
    else:
        print("  every checked column lies within its physically plausible range")

    # ── Missing-value accounting ─────────────────────────────────────────────
    print("\n[5] Missing values in the model feature tables")
    missing_report: dict = {}
    for name, table_getter in (
        ("model1_dataset", lambda: frames.get("model1_dataset")),
        ("model3_dataset", lambda: frames.get("model3_dataset")),
    ):
        frame = table_getter()
        if frame is None:
            continue
        nulls = frame.isna().sum()
        nulls = nulls[nulls > 0]
        missing_report[name] = {
            column: {
                "nulls": int(count),
                "fraction": round(float(count) / len(frame), 6),
            }
            for column, count in nulls.items()
        }
        if len(nulls):
            print(f"  {name}:")
            for column, count in nulls.items():
                print(f"    {column:36s} {int(count):>7,} ({count / len(frame):.2%})")
        else:
            print(f"  {name}: complete")
    report["missing_values"] = missing_report

    # ── Temporal alignment ───────────────────────────────────────────────────
    print("\n[6] Temporal alignment")
    ghsl_years = sorted(
        int(k.split("_")[1]) for k in report["layers"] if k.startswith("ghsl_")
        and report["layers"][k].get("present")
    )
    chirps_years = sorted(
        int(k.split("_")[1]) for k in report["layers"] if k.startswith("chirps_")
        and report["layers"][k].get("present")
    )
    report["temporal"] = {
        "ghsl_epochs": ghsl_years,
        "chirps_years": chirps_years,
        "model2_t0": config.M2_T0_YEAR,
        "model2_t1": config.M2_T1_YEAR,
        "model2_rainfall_year": config.M2_RAINFALL_YEAR,
    }
    print(f"  GHSL epochs available : {ghsl_years}")
    print(f"  CHIRPS years available: {chirps_years}")
    print(
        f"  Model 2 forward validation: T0={config.M2_T0_YEAR} -> T1={config.M2_T1_YEAR}, "
        f"rainfall from {config.M2_RAINFALL_YEAR}"
    )

    for year, label in (
        (config.M2_T0_YEAR, "T0"), (config.M2_T1_YEAR, "T1"),
    ):
        if year not in ghsl_years:
            fail(f"Model 2 {label} epoch {year} has no GHSL layer")
    if config.M2_RAINFALL_YEAR not in chirps_years:
        fail(f"Model 2 rainfall year {config.M2_RAINFALL_YEAR} has no CHIRPS layer")
    if config.M2_T0_YEAR >= config.M2_T1_YEAR:
        fail("Model 2 T0 is not earlier than T1, so the target is not forward-looking")
    if not report["failures"]:
        print("  forward-validation epochs are present and correctly ordered")

    # ── Verdict ──────────────────────────────────────────────────────────────
    report["passed"] = not report["failures"]
    print("\n" + "=" * 78)
    if report["passed"]:
        print("PASS — every layer aligns on the common 1 km grid.")
    else:
        print(f"FAIL — {len(report['failures'])} problem(s) found:")
        for failure in report["failures"]:
            print(f"  - {failure}")
    print("=" * 78)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        destination = args.out / "grid_alignment_report.json"
        destination.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nReport written to {destination}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
