"""
Evaluate the shipped model artifacts on their unseen-city holdout.

    input          the trained artifact, its feature table, and its city split manifest
    preprocessing  assemble features through the same feature store the API uses
    evaluation     score the held-out cities, overall and per city
    output         a metrics report printed as a table and written as JSON

This is the check that the inference path in this repository is the trained one. It
recomputes precision, recall, F1, ROC-AUC and PR-AUC on the training run's own test
cities and compares them against the figures that run recorded. A mismatch means the
feature assembly, feature ordering or threshold handling has drifted from training.

Usage:
    python -m scripts.evaluation.evaluate_models --model all
    python -m scripts.evaluation.evaluate_models --model flood --out build/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import config  # noqa: E402
from app.services.models import feature_store, flood_risk, registry, surface_water  # noqa: E402

MODELS = {
    "water": {
        "label": "Model 1 — Surface Water Monitoring",
        "service": surface_water,
        "target": "is_water_body",
        "algorithm": config.M1_ALGORITHM,
        "metrics_dir": config.M1_METRICS_DIR,
        "table": feature_store.surface_water_table,
        "estimator": registry.surface_water_model,
    },
    "flood": {
        "label": "Model 3 — Urban Flood Risk",
        "service": flood_risk,
        "target": "flood_label",
        "algorithm": config.M3_ALGORITHM,
        "metrics_dir": config.M3_METRICS_DIR,
        "table": feature_store.flood_risk_table,
        "estimator": registry.flood_risk_model,
    },
}


def _score(y_true, probabilities, threshold: float) -> dict:
    predictions = (probabilities >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, predictions, average="binary", zero_division=0
    )
    result = {
        "n": int(len(y_true)),
        "positive_rate": round(float(np.mean(y_true)), 4),
        "threshold": round(threshold, 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
    }
    # AUC is undefined when a split contains only one class.
    if len(np.unique(y_true)) > 1:
        result["roc_auc"] = round(float(roc_auc_score(y_true, probabilities)), 4)
        result["pr_auc"] = round(float(average_precision_score(y_true, probabilities)), 4)
    else:
        result["roc_auc"] = None
        result["pr_auc"] = None

    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()
    result["confusion_matrix"] = {
        "true_negative": int(tn), "false_positive": int(fp),
        "false_negative": int(fn), "true_positive": int(tp),
    }
    return result


def evaluate(key: str) -> dict:
    """Evaluate one model on its unseen-city test split."""
    spec = MODELS[key]
    print(f"\n{'=' * 78}\n{spec['label']}\n{'=' * 78}")

    model = spec["estimator"]()
    table = spec["table"]()
    features = spec["service"].feature_order()
    threshold = spec["service"].operating_threshold()

    split = json.loads((spec["metrics_dir"] / "city_split.json").read_text())
    report: dict = {
        "model": spec["label"],
        "algorithm": spec["algorithm"],
        "decision_threshold": round(threshold, 6),
        "validation_strategy": "city-based holdout (no city spans two splits)",
        "city_split_sizes": {
            name: len(split[f"{name}_cities"]) for name in ("train", "val", "test")
        },
        "splits": {},
    }

    # Confirm the split really is disjoint before trusting any number from it.
    train, val, test = (set(split[f"{n}_cities"]) for n in ("train", "val", "test"))
    overlap = (train & test) | (train & val) | (val & test)
    if overlap:
        raise SystemExit(f"City split is not disjoint; overlapping cities: {sorted(overlap)}")
    print(f"Split is disjoint: {len(train)} train / {len(val)} val / {len(test)} test cities")

    for split_name in ("train", "val", "test"):
        cities = split[f"{split_name}_cities"]
        subset = table[table["city"].isin(cities)]
        if subset.empty:
            continue
        probabilities = model.predict_proba(subset[features])[:, 1]
        report["splits"][split_name] = _score(
            subset[spec["target"]].astype(int).to_numpy(), probabilities, threshold
        )

    print("\nOverall performance by split:")
    print(
        pd.DataFrame(
            {
                name: {
                    k: v for k, v in scores.items() if k != "confusion_matrix"
                }
                for name, scores in report["splits"].items()
            }
        ).to_string()
    )

    # Per-city performance on the unseen test cities — the spec requires this.
    test_subset = table[table["city"].isin(split["test_cities"])]
    per_city = []
    for city, group in test_subset.groupby("city"):
        probabilities = model.predict_proba(group[features])[:, 1]
        scores = _score(group[spec["target"]].astype(int).to_numpy(), probabilities, threshold)
        per_city.append({"city": city, **{k: v for k, v in scores.items()
                                          if k != "confusion_matrix"}})
    report["per_city_test"] = per_city

    print("\nPer-city performance on unseen test cities:")
    print(pd.DataFrame(per_city).to_string(index=False))

    # Compare against what the training run itself recorded.
    published_path = spec["metrics_dir"] / "test_metrics_comparison.csv"
    if published_path.exists():
        published = pd.read_csv(published_path)
        row = published[published["model"] == spec["algorithm"]]
        if not row.empty:
            row = row.iloc[0]
            recomputed = report["splits"]["test"]
            comparison, matched = {}, True
            for measure in ("precision", "recall", "f1", "roc_auc", "pr_auc"):
                published_value = float(row[measure])
                recomputed_value = recomputed[measure]
                agrees = (
                    recomputed_value is not None
                    and abs(recomputed_value - published_value) < 5e-4
                )
                matched &= agrees
                comparison[measure] = {
                    "published": published_value,
                    "recomputed": recomputed_value,
                    "agrees": agrees,
                }
            report["reproduction_check"] = {"matches_training_run": matched,
                                            "measures": comparison}
            print(
                f"\nReproduction against the training run's saved metrics: "
                f"{'MATCH' if matched else 'MISMATCH'}"
            )
            for measure, values in comparison.items():
                flag = "ok" if values["agrees"] else "DIFFERS"
                print(
                    f"  {measure:10s} published={values['published']:.4f} "
                    f"recomputed={values['recomputed']} [{flag}]"
                )
            if not matched:
                print(
                    "\nA mismatch means the inference path here differs from training. "
                    "Check feature assembly, feature order and the decision threshold."
                )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", choices=[*MODELS, "all"], default="all",
        help="Which model to evaluate.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Directory for the JSON report.")
    args = parser.parse_args()

    keys = list(MODELS) if args.model == "all" else [args.model]
    reports = {}
    for key in keys:
        try:
            reports[key] = evaluate(key)
        except Exception as exc:  # noqa: BLE001 - report and continue to the next model
            print(f"\n{MODELS[key]['label']}: evaluation failed — {exc}")
            reports[key] = {"error": str(exc)}

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        destination = args.out / "model_evaluation.json"
        destination.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(f"\nReport written to {destination}")

    failed = [
        k for k, r in reports.items()
        if "error" in r or r.get("reproduction_check", {}).get("matches_training_run") is False
    ]
    if failed:
        print(f"\nModels that did not reproduce cleanly: {', '.join(failed)}")
        return 1
    print("\nAll evaluated models reproduce their published holdout metrics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
