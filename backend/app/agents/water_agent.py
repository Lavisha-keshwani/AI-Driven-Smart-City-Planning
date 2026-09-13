"""
Water / Environment Agent — wraps and interprets Model 1.

Runs Model 1 for the grid cell, then explains what the classification and the
observed Global Surface Water record mean for water availability and environmental
condition. It does not produce a water prediction of its own; the probability and
classification in its evidence come from the model and pass through untouched.
"""

from __future__ import annotations

import logging

from app.agents import base
from app.agents.schemas import AgentResult
from app.agents.state import CityState
from app.core.errors import SmartCityError
from app.services.models import surface_water

logger = logging.getLogger(__name__)

DOMAIN = "water"
AGENT = "Water / Environment Agent"

TASK = (
    "Model 1 (Surface Water Monitoring) is an XGBoost classifier validated on a "
    "city-based holdout: it decides whether a 1 km grid cell is a surface-water body, "
    "from terrain, rainfall climatology, spectral indices and land cover. Its recall "
    "at the tuned threshold is moderate, so a negative classification means the model "
    "found no evidence of a water body, not that none exists.\n\n"
    "The observed Global Surface Water statistics in the evidence are satellite "
    "measurements, not predictions. Treat them as ground truth and keep them distinct "
    "from the model's probability.\n\n"
    "Explain what this cell's water situation means for water-resource availability, "
    "environmental condition, and any implication for nearby development."
)


def _evidence(result: dict) -> dict:
    return {
        "grid_cell": {
            "grid_id": result["grid_id"],
            "city": result["city"],
            "state": result["state"],
        },
        "model_prediction": {
            "model": result["model"],
            "algorithm": result["algorithm"],
            "water_body_probability": result["water_body_probability"],
            "classification": result["classification"],
            "decision_threshold": result["decision_threshold"],
        },
        "measured_observations": result["observed"],
        "derived_water_body_status": result["water_body_status"],
        "top_contributing_features": (result.get("feature_attribution") or [])[:5],
        "incomplete_features": result.get("incomplete_features"),
    }


def _fallback(result: dict) -> AgentResult:
    """Deterministic summary, used when the LLM is unavailable."""
    status = result["water_body_status"]
    probability = result["water_body_probability"]
    occurrence = status.get("occurrence_pct")

    findings = [
        f"Model 1 assigns a water-body probability of {probability:.0%}, classifying the "
        f"cell as {result['classification'].replace('_', ' ')} at its tuned threshold of "
        f"{result['decision_threshold']:.2f}.",
    ]
    if occurrence is not None:
        findings.append(
            f"Global Surface Water observations (measured) show water present "
            f"{occurrence:.1f}% of the time, a {status['status']} regime with "
            f"{status['inter_annual_reliability']} inter-annual reliability."
        )

    risks, recommendations = [], []
    if result["is_water_body"]:
        risks.append(
            "The cell contains surface water, so construction setbacks and drainage "
            "obligations apply, and encroachment would reduce local storage capacity."
        )
        recommendations.append("Protect the water body extent and confirm statutory setbacks.")
    elif status.get("status") in {"seasonal", "ephemeral"}:
        risks.append(
            "Water appears here only part of the year, so it is not a dependable "
            "year-round source."
        )
        recommendations.append(
            "Plan for storage or an alternative dry-season supply rather than relying "
            "on this surface water."
        )
    else:
        risks.append(
            "No surface water is observed in this cell, so demand falls on piped supply "
            "or groundwater."
        )
        recommendations.append("Prioritise rainwater harvesting and demand-side efficiency.")

    return AgentResult(
        domain=DOMAIN,
        summary=(
            f"Cell {result['grid_id']} in {result['city']} is classified as "
            f"{result['classification'].replace('_', ' ')} with probability "
            f"{probability:.0%}. Observed surface-water regime: {status['status']}."
        ),
        findings=findings,
        risks=risks,
        recommendations=recommendations,
        uncertainty=(
            "Generated without LLM interpretation. Model 1's recall is moderate, so a "
            "non-water classification is absence of evidence rather than evidence of "
            "absence, and its spectral inputs are sensitive to image season and date."
        ),
        interpretation_confidence="medium",
    )


def run(state: CityState) -> dict:
    """LangGraph node: Model 1 inference, then LLM interpretation."""
    location = state["location"]
    grid_id = location["grid_id"]
    explain = bool(state.get("options", {}).get("include_attribution", True))

    try:
        result = surface_water.predict(grid_id, explain_prediction=explain)
    except SmartCityError as exc:
        logger.warning("%s: Model 1 unavailable for %s — %s", AGENT, grid_id, exc.message)
        return {
            "water_result": {},
            "water_analysis": base.failure_analysis(
                domain=DOMAIN, agent=AGENT,
                model_name=surface_water.MODEL_NAME, exc=exc,
            ).model_dump(),
            "errors": [base.error_entry(DOMAIN, exc)],
            "trace": [f"{AGENT}: failed ({exc.error_code})"],
        }

    analysis = base.interpret(
        domain=DOMAIN,
        agent=AGENT,
        model_name=result["model"],
        task=TASK,
        evidence=_evidence(result),
        fallback=_fallback(result),
    )
    return {
        "water_result": result,
        "water_analysis": analysis.model_dump(),
        "trace": [f"{AGENT}: {result['classification']} (p={result['water_body_probability']:.3f})"],
    }
