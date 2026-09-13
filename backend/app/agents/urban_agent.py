"""
Urban Planning Agent — wraps and interprets Model 2.

Explains why a cell was scored GREEN, YELLOW or RED and what that means for
development decisions. It never invents a suitability judgement: the score, the
class and the probabilities all come from Model 2 and pass through unchanged.

The agent is briefed on what the label actually measures — propensity for growth,
learned from historical expansion — so its explanation does not silently upgrade a
statistical pattern into an environmental endorsement.
"""

from __future__ import annotations

import logging

from app.agents import base
from app.agents.schemas import AgentResult
from app.agents.state import CityState
from app.core.errors import SmartCityError
from app.services.models import urban_expansion

logger = logging.getLogger(__name__)

DOMAIN = "urban"
AGENT = "Urban Planning Agent"

TASK = (
    "Model 2 (Urban Expansion Suitability) is a LightGBM 3-class classifier trained "
    "by forward validation: its inputs describe a 1 km cell's state in 2000, and its "
    "label is which tercile of built-up growth that cell actually fell into by 2020. "
    "GREEN is the highest-growth tercile, YELLOW the middle, RED the lowest.\n\n"
    "This matters for how you phrase the interpretation. The model measures PROPENSITY "
    "FOR EXPANSION learned from where growth historically occurred. It is not a "
    "judgement that expansion there is environmentally desirable, and a GREEN label is "
    "not an approval. Terciles are relative to all 45 cities in the training pool, so "
    "the class is a national-relative ranking.\n\n"
    "Explain what the classification means for development decisions at this location, "
    "why the cell scored as it did given the evidence, and what the listed site "
    "constraints imply. Be explicit that flood and water evidence must be weighed "
    "against this score before any decision is reached."
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
            "suitability_score": result["suitability_score"],
            "suitability_class": result["suitability_class"],
            "class_meaning": result["class_meaning"],
            "confidence": result["confidence"],
            "class_probabilities": result["class_probabilities"],
            "score_definition": result["score_definition"],
            "classification_rule": result["classification_rule"],
        },
        "measured_observations": result["observed"],
        "site_constraints": result["constraints"],
        "top_contributing_features": (result.get("feature_attribution") or [])[:5],
        "incomplete_features": result.get("incomplete_features"),
    }


def _fallback(result: dict) -> AgentResult:
    label = result["suitability_class"]
    score = result["suitability_score"]
    observed = result["observed"]
    constraints = result["constraints"]

    findings = [
        f"Model 2 classifies the cell as {label} with a suitability score of {score:.2f} "
        f"and confidence {result['confidence']:.0%}.",
        f"The class reflects observed built-up growth terciles between "
        f"{observed['t0_year']} and {observed['t1_year']}, not environmental desirability.",
    ]
    growth = observed.get("built_growth_t0_t1")
    if growth is not None:
        findings.append(
            f"Measured built-up fraction moved from {observed['built_fraction_t0']:.3f} to "
            f"{observed['built_fraction_t1']:.3f} over that period, a change of {growth:+.3f}."
        )

    risks = [c["reason"] for c in constraints]
    risks.append(
        "A favourable growth score says nothing about flood exposure or water "
        "availability; those must be checked separately."
    )

    if label == "GREEN":
        recommendations = [
            "Treat this as a candidate growth direction, subject to the flood and water "
            "findings, and plan trunk infrastructure ahead of demand."
        ]
    elif label == "YELLOW":
        recommendations = [
            "Treat expansion here as conditional: confirm servicing capacity and resolve "
            "the listed site constraints first."
        ]
    else:
        recommendations = [
            "Direct growth elsewhere. This cell sits in the lowest observed-growth class, "
            "so development would run against the established pattern and likely cost more "
            "to service."
        ]

    return AgentResult(
        domain=DOMAIN,
        summary=(
            f"Cell {result['grid_id']} in {result['city']} scores {score:.2f} and is "
            f"classified {label}: {result['class_meaning']}."
        ),
        findings=findings,
        risks=risks,
        recommendations=recommendations,
        uncertainty=(
            "Generated without LLM interpretation. The class is a national-relative "
            "tercile, road-network access was excluded from the features because "
            "OpenStreetMap covered only 3 of 45 cities, and growth observed over "
            "2000-2020 need not continue under changed policy."
        ),
        interpretation_confidence="medium",
    )


def run(state: CityState) -> dict:
    """LangGraph node: Model 2 inference, then LLM interpretation."""
    grid_id = state["location"]["grid_id"]
    explain = bool(state.get("options", {}).get("include_attribution", True))

    try:
        result = urban_expansion.predict(grid_id, explain_prediction=explain)
    except SmartCityError as exc:
        logger.warning("%s: Model 2 unavailable for %s — %s", AGENT, grid_id, exc.message)
        return {
            "urban_result": {},
            "urban_analysis": base.failure_analysis(
                domain=DOMAIN, agent=AGENT,
                model_name=urban_expansion.MODEL_NAME, exc=exc,
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
        "urban_result": result,
        "urban_analysis": analysis.model_dump(),
        "trace": [
            f"{AGENT}: {result['suitability_class']} (score={result['suitability_score']:.3f})"
        ],
    }
