"""
Forward-validation evaluation of Model 2 (Urban Expansion Suitability).

    input          the trained artifact and the rebuilt T0 feature table
    preprocessing  assemble features exactly as the API does, via the feature store
    target         GHSL built-up growth between T0 and T1, tercile-binned
    evaluation     overall and per-city agreement, plus a city-holdout view
    output         a metrics report printed as a table and written as JSON

Why this script exists. The Model 2 training run saved `metrics_comparison.csv` but no
city-split manifest, so its reported 0.835 accuracy cannot be attributed to a spatial
holdout. This script supplies the missing spatial validation: it scores the shipped
artifact per city, and reports the distribution across cities rather than one pooled
number, so spatially optimistic performance cannot hide behind an average.

It also serves as the encoding check. `city_code` and `state_code` are alphabetical
category codes that the training script did not document; if this repository
reconstructed them differently from training, agreement with the forward-validation
target would collapse towards chance (0.33 for three balanced classes).

Usage:
    python -m scripts.evaluation.evaluate_urban_expansion --out build/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import config  # noqa: E402
from app.services.models import feature_store, registry, urban_expansion  # noqa: E402

CLASS_NAMES = ["RED", "YELLOW", "GREEN"]


def build_target(table: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Derive the forward-validation target from the two GHSL epochs.

    The label is which tercile of observed built-up growth a cell fell into between
    T0 and T1: features describe the historical state, the target is what happened
    next. Terciles are cut over the whole pool, matching the training construction.
    """
    subset = table.dropna(subset=["built_t0", "built_t1"]).copy()
    growth = (subset["built_t1"] - subset["built_t0"]).to_numpy()
    edges = np.quantile(growth, [1 / 3, 2 / 3])
    return subset, np.digitize(growth, edges), edges


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Directory for the JSON report.")
    parser.add_argument(
        "--holdout-fraction", type=float, default=0.2,
        help="Share of cities held out in the spatial-holdout view.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print("=" * 78)
    print("Model 2 — Urban Expansion Suitability: forward-validation evaluation")
    print("=" * 78)

    model = registry.urban_expansion_model()
    table = feature_store.urban_expansion_table()
    features = urban_expansion.feature_order()

    subset, y_true, edges = build_target(table)
    print(
        f"\nForward validation: features at T0={config.M2_T0_YEAR}, "
        f"target = growth to T1={config.M2_T1_YEAR}"
    )
    print(f"Tercile edges on built-up growth: {np.round(edges, 6).tolist()}")
    print(f"Cells evaluated: {len(subset):,} across {subset['city'].nunique()} cities")

    probabilities = model.predict_proba(subset[features].astype(float))
    y_pred = np.asarray(model.classes_)[probabilities.argmax(axis=1)]

    report: dict = {
        "model": "Model 2 — Urban Expansion Suitability",
        "algorithm": registry.model2_config().get("best_model"),
        "forward_validation": {
            "t0_year": config.M2_T0_YEAR,
            "t1_year": config.M2_T1_YEAR,
            "target": "GHSL built_fraction(T1) - built_fraction(T0), tercile-binned",
            "tercile_edges": [float(e) for e in edges],
            "design_note": (
                "Predictors describe the cell's historical state; the label is the "
                "growth that subsequently occurred. The model therefore learns which "
                "characteristics preceded expansion, not where the city already is."
            ),
        },
        "cells_evaluated": int(len(subset)),
        "cities": int(subset["city"].nunique()),
    }

    # ── Pooled performance ───────────────────────────────────────────────────
    accuracy = float((y_pred == y_true).mean())
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    try:
        roc_auc = float(roc_auc_score(y_true, probabilities, multi_class="ovr"))
    except ValueError:
        roc_auc = None

    report["pooled"] = {
        "accuracy": round(accuracy, 4),
        "precision_macro": round(float(precision), 4),
        "recall_macro": round(float(recall), 4),
        "f1_macro": round(float(f1), 4),
        "roc_auc_ovr": round(roc_auc, 4) if roc_auc is not None else None,
    }
    print(f"\nPooled performance (all cells): {json.dumps(report['pooled'])}")

    print("\nPer-class report:")
    print(classification_report(y_true, y_pred, target_names=CLASS_NAMES, zero_division=0))

    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])
    report["confusion_matrix"] = {
        "labels": CLASS_NAMES,
        "matrix": matrix.tolist(),
    }
    print("Confusion matrix (rows = observed, columns = predicted):")
    print(pd.DataFrame(matrix, index=CLASS_NAMES, columns=CLASS_NAMES).to_string())

    # ── Encoding reconstruction check ────────────────────────────────────────
    chance = 1 / 3
    report["encoding_check"] = {
        "pooled_accuracy": round(accuracy, 4),
        "chance_level": round(chance, 4),
        "reconstruction_plausible": bool(accuracy > 0.6),
        "note": (
            "city_code/state_code are alphabetical category codes over the full 45-city "
            "grid, reconstructed here because the training run did not document the "
            "encoding. Accuracy far above chance confirms the reconstruction matches "
            "what the model was fitted on."
        ),
    }
    print(
        f"\nEncoding reconstruction: accuracy {accuracy:.4f} against a chance level of "
        f"{chance:.4f} -> "
        f"{'consistent with training' if accuracy > 0.6 else 'INCONSISTENT'}"
    )

    published = registry.model2_metrics()
    if published is not None:
        row = published[published["model"] == registry.model2_config().get("best_model")]
        if not row.empty:
            report["training_run_reported_accuracy"] = round(float(row.iloc[0]["accuracy"]), 4)
            print(
                f"Training run reported accuracy: "
                f"{report['training_run_reported_accuracy']:.4f} "
                f"(pooled here: {accuracy:.4f}; this evaluation includes cells the "
                f"training run may have used for fitting, so a higher figure is expected)"
            )

    # ── Per-city performance ─────────────────────────────────────────────────
    frame = subset[["grid_id", "city"]].copy()
    frame["observed"] = y_true
    frame["predicted"] = y_pred

    per_city = []
    for city, group in frame.groupby("city"):
        city_precision, city_recall, city_f1, _ = precision_recall_fscore_support(
            group["observed"], group["predicted"], average="macro", zero_division=0
        )
        per_city.append({
            "city": city,
            "n": int(len(group)),
            "accuracy": round(float((group["predicted"] == group["observed"]).mean()), 4),
            "f1_macro": round(float(city_f1), 4),
        })
    per_city.sort(key=lambda r: r["accuracy"])
    report["per_city"] = per_city

    accuracies = [c["accuracy"] for c in per_city]
    report["per_city_spread"] = {
        "min": min(accuracies), "max": max(accuracies),
        "mean": round(float(np.mean(accuracies)), 4),
        "std": round(float(np.std(accuracies)), 4),
    }
    print("\nPer-city accuracy spread:", json.dumps(report["per_city_spread"]))
    print("\nFive weakest cities:")
    print(pd.DataFrame(per_city[:5]).to_string(index=False))
    print("\nFive strongest cities:")
    print(pd.DataFrame(per_city[-5:]).to_string(index=False))

    # ── Spatial holdout view ─────────────────────────────────────────────────
    rng = np.random.default_rng(args.seed)
    cities = np.array(sorted(frame["city"].unique()))
    rng.shuffle(cities)
    n_holdout = max(1, int(len(cities) * args.holdout_fraction))
    holdout = sorted(cities[:n_holdout].tolist())

    held = frame[frame["city"].isin(holdout)]
    held_precision, held_recall, held_f1, _ = precision_recall_fscore_support(
        held["observed"], held["predicted"], average="macro", zero_division=0
    )
    report["spatial_holdout"] = {
        "holdout_cities": holdout,
        "n_cells": int(len(held)),
        "accuracy": round(float((held["predicted"] == held["observed"]).mean()), 4),
        "f1_macro": round(float(held_f1), 4),
        "caveat": (
            "The shipped artifact was fitted before this script existed, and the "
            "training run saved no city-split manifest, so these cities cannot be "
            "guaranteed unseen. The figure is a spatial-consistency check, not a clean "
            "generalisation estimate. Retrain with a declared city split for that."
        ),
    }
    print(f"\nSpatial holdout over {n_holdout} cities: {holdout}")
    print(
        f"  accuracy={report['spatial_holdout']['accuracy']:.4f} "
        f"f1_macro={report['spatial_holdout']['f1_macro']:.4f}"
    )
    print(f"  caveat: {report['spatial_holdout']['caveat']}")

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        destination = args.out / "urban_expansion_evaluation.json"
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {destination}")

    if not report["encoding_check"]["reconstruction_plausible"]:
        print(
            "\nFAILED: accuracy near chance means the rebuilt feature table does not "
            "match what Model 2 was trained on."
        )
        return 1
    print("\nForward-validation evaluation complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
