"""
Build the Model 2 (Urban Expansion Suitability) feature table.

    input          GHSL built-up (T0 and T1 epochs), Open Buildings, SRTM, CHIRPS,
                   and the 1 km grid registry
    preprocessing  deduplicate on grid_id; left-join every layer onto the registry so
                   the grid stays authoritative; leave gaps as NaN
    features       built_t0, building count/height/presence, elevation, slope,
                   depression index, annual rainfall, lat, lon, is_core,
                   city_code, state_code
    target         built_fraction(T1) - built_fraction(T0), tercile-binned into
                   RED / YELLOW / GREEN
    output         one CSV, plus a JSON manifest recording the layers, row counts and
                   completeness

Model 2 ships no pre-merged dataset, so this script is the reproducible definition of
its feature table — the same assembly the API performs at inference time, exported for
inspection, retraining, or extension to new cities.

Missing values are left as NaN on purpose. LightGBM handles them natively, and
imputing here would invent evidence the model would then treat as observed.

Usage:
    python -m scripts.features.build_urban_expansion_features --out build/
    python -m scripts.features.build_urban_expansion_features --out build/ --with-target
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import config  # noqa: E402
from app.services.models import feature_store, registry, urban_expansion  # noqa: E402
from scripts.evaluation.evaluate_urban_expansion import build_target  # noqa: E402

CLASS_NAMES = {0: "RED", 1: "YELLOW", 2: "GREEN"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument(
        "--with-target", action="store_true",
        help="Include the tercile-binned forward-validation target.",
    )
    parser.add_argument(
        "--city", default=None, help="Restrict the output to one city."
    )
    args = parser.parse_args()

    print("=" * 78)
    print("Model 2 feature table assembly")
    print("=" * 78)
    print("\nSource layers:")
    layers = {
        "grid_registry": config.GRID_METADATA_CSV,
        "ghsl_t0": config.GHSL_DIR / f"ghsl_features_{config.M2_T0_YEAR}_FIXED.csv",
        "ghsl_t1": config.GHSL_DIR / f"ghsl_features_{config.M2_T1_YEAR}_FIXED.csv",
        "open_buildings": config.OPEN_BUILDINGS_DIR,
        "srtm": config.SRTM_CSV,
        "chirps": config.CHIRPS_DIR / f"chirps_features_{config.M2_RAINFALL_YEAR}.csv",
    }
    for name, path in layers.items():
        print(f"  {name:16s} {'ok     ' if path.exists() else 'MISSING'} {path.name}")

    missing = [n for n, p in layers.items() if not p.exists()]
    if missing:
        print(f"\nCannot build: missing layers {', '.join(missing)}.")
        print("Point the matching variables in .env at the exports, then re-run.")
        return 1

    table = feature_store.urban_expansion_table()
    if args.city:
        table = feature_store.subset_for_city(table, args.city)

    features = urban_expansion.feature_order()
    columns = ["grid_id", "city", "state", *features, "built_t1", "built_growth_t0_t1"]
    output = table[[c for c in columns if c in table.columns]].copy()

    manifest: dict = {
        "model": "Model 2 — Urban Expansion Suitability",
        "forward_validation": {
            "t0_year": config.M2_T0_YEAR,
            "t1_year": config.M2_T1_YEAR,
            "rainfall_year": config.M2_RAINFALL_YEAR,
        },
        "source_layers": {name: str(path.name) for name, path in layers.items()},
        "feature_order": features,
        "feature_order_source": "recovered from the trained LightGBM booster",
        "rows": int(len(output)),
        "cities": int(output["city"].nunique()),
        "grid_crs": config.GRID_CRS,
        "grid_cell_size_m": config.GRID_CELL_SIZE_M,
        "missing_value_policy": (
            "Gaps are left as NaN. LightGBM handles them natively; imputing here would "
            "fabricate evidence the model would treat as observed."
        ),
        "encoding_note": (
            "city_code/state_code are alphabetical pandas category codes over the full "
            "45-city grid, reproducing the training-time encoding."
        ),
        "excluded_features": {
            "road_density": (
                "OpenStreetMap road coverage existed for only 3 of 45 cities, so the "
                "feature would encode data availability rather than accessibility."
            )
        },
    }

    print(f"\nAssembled: {len(output):,} rows across {output['city'].nunique()} cities")

    completeness = {}
    for feature in features:
        nulls = int(output[feature].isna().sum())
        completeness[feature] = {
            "nulls": nulls,
            "complete_fraction": round(1 - nulls / max(len(output), 1), 6),
        }
    manifest["feature_completeness"] = completeness

    incomplete = {f: c["nulls"] for f, c in completeness.items() if c["nulls"]}
    if incomplete:
        print("\nFeatures with missing values (left as NaN):")
        for feature, count in incomplete.items():
            print(f"  {feature:24s} {count:,} of {len(output):,}")
    else:
        print("\nAll features are complete for every cell.")

    if args.with_target:
        subset, target, edges = build_target(output)
        subset = subset.copy()
        subset["growth_tercile"] = target
        subset["suitability_class"] = [CLASS_NAMES[int(t)] for t in target]
        output = subset
        manifest["target"] = {
            "definition": "GHSL built_fraction(T1) - built_fraction(T0), tercile-binned",
            "tercile_edges": [float(e) for e in edges],
            "tercile_scope": (
                f"computed over the {args.city} subset only, so the edges differ from "
                f"the whole-grid terciles the model was trained against"
                if args.city else "computed over the whole 45-city grid, as in training"
            ),
            "class_names": CLASS_NAMES,
            "class_counts": {
                CLASS_NAMES[int(k)]: int(v)
                for k, v in zip(*np.unique(target, return_counts=True))
            },
        }
        print(f"\nTarget added. Class balance: {manifest['target']['class_counts']}")

    args.out.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.city.lower()}" if args.city else ""
    csv_path = args.out / f"model2_urban_expansion_features{suffix}.csv"
    manifest_path = args.out / f"model2_urban_expansion_manifest{suffix}.json"

    output.to_csv(csv_path, index=False)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nFeatures  -> {csv_path} ({csv_path.stat().st_size / 1_048_576:.1f} MB)")
    print(f"Manifest  -> {manifest_path}")

    # Confirm the export is usable by the trained model before declaring success.
    model = registry.urban_expansion_model()
    sample = output.head(100)
    probabilities = model.predict_proba(sample[features].astype(float))
    assert probabilities.shape == (len(sample), 3)
    print(f"\nVerified: the trained model scores the exported table (checked {len(sample)} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
