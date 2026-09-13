"""
Flood / Resilience Agent — wraps and interprets Model 3.

Explains a flood probability in resilience terms: what it means for drainage, for
development restriction, and for the confidence a planner can place in it. The
probability, the band and the drivers all come from Model 3 and the measured layers;
the agent adds interpretation only.
"""

from __future__ import annotations

import logging

from app.agents import base
from app.agents.schemas import AgentResult
from app.agents.state import CityState
from app.core.errors import SmartCityError
from app.services.models import flood_risk

logger = logging.getLogger(__name__)

DOMAIN = "flood"
AGENT = "Flood / Resilience Agent"

TASK = (
    "Model 3 (Urban Flood Risk) is a Random Forest predicting flood susceptibility for "
    "a 1 km cell, trained on Global Flood Database observed-inundation labels with "
    "terrain, surface-water, built-up time-series and rainfall predictors. Validation "
    "used a city-based holdout, because adjacent 1 km cells share flood events and a "
    "random split would leak spatially and overstate skill.\n\n"
    "Two limits to respect in your interpretation. First, recall at the tuned threshold "
    "is moderate (about 0.46 on unseen cities), so a LOW result is absence of evidence, "
    "not evidence of safety — say so. Second, labels cover 2000-2018, so drainage built "
    "after that period is not reflected, and pluvial flooding from drainage overload is "
    "only implicitly represented.\n\n"
    "Explain the resilience implications: what this probability means for drainage "
    "design, what development restrictions or mitigations follow, and how much weight "
    "the result should carry."
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
            "flood_probability": result["flood_probability"],
            "risk_level": result["risk_level"],
            "risk_meaning": result["risk_meaning"],
            "decision_threshold": result["decision_threshold"],
            "risk_bands": result["risk_bands"],
        },
        "measured_observations": result["observed"],
        "physical_risk_drivers": result["risk_drivers"],
        "top_contributing_features": (result.get("feature_attribution") or [])[:5],
        "incomplete_features": result.get("incomplete_features"),
    }


def _fallback(result: dict) -> AgentResult:
    probability = result["flood_probability"]
    level = result["risk_level"]
    observed = result["observed"]
    drivers = result["risk_drivers"]

    findings = [
        f"Model 3 predicts a flood probability of {probability:.0%}, placing the cell in "
        f"the {level} band.",
    ]
    findings.extend(f"Measured driver: {d['reason']}" for d in drivers)
    events = observed.get("historical_flood_events")
    if events is not None:
        findings.append(
            f"The Global Flood Database records {events:.0f} observed inundation "
            f"event(s) for this cell over {observed.get('flood_record_period', 'the record period')}."
        )

    if level == "HIGH":
        risks = [
            "High susceptibility: unmitigated development here carries a material risk of "
            "flood damage to property and disruption of access."
        ]
        recommendations = [
            "Restrict new development, or require raised plinths, flood-resistant ground "
            "floors and on-site detention.",
            "Verify design flood levels against municipal records before approving layouts.",
        ]
    elif level == "MODERATE":
        risks = [
            "Moderate susceptibility, close to the model's decision boundary, so the "
            "result is less certain than a clear HIGH or LOW."
        ]
        recommendations = [
            "Permit development with resilience measures: raised plinth, backflow "
            "prevention and drainage sized for intense events.",
        ]
    else:
        risks = [
            "Modelled susceptibility is low, but the model's moderate recall means this "
            "is absence of evidence rather than proof of safety."
        ]
        recommendations = [
            "Standard drainage design is expected to suffice; still confirm against local "
            "flood history before relying on this result.",
        ]

    return AgentResult(
        domain=DOMAIN,
        summary=(
            f"Cell {result['grid_id']} in {result['city']} has a modelled flood "
            f"probability of {probability:.0%} ({level}). {result['risk_meaning']}"
        ),
        findings=findings,
        risks=risks,
        recommendations=recommendations,
        uncertainty=(
            "Generated without LLM interpretation. Flood labels come from satellite "
            "observation between 2000 and 2018, whose detection quality varies with cloud "
            "cover and revisit timing; drainage built since is not represented; and "
            "per-city performance varies substantially."
        ),
        interpretation_confidence="medium",
    )


def run(state: CityState) -> dict:
    """LangGraph node: Model 3 inference, then LLM interpretation."""
    grid_id = state["location"]["grid_id"]
    explain = bool(state.get("options", {}).get("include_attribution", True))

    try:
        result = flood_risk.predict(grid_id, explain_prediction=explain)
    except SmartCityError as exc:
        logger.warning("%s: Model 3 unavailable for %s — %s", AGENT, grid_id, exc.message)
        return {
            "flood_result": {},
            "flood_analysis": base.failure_analysis(
                domain=DOMAIN, agent=AGENT, model_name=flood_risk.MODEL_NAME, exc=exc,
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
        "flood_result": result,
        "flood_analysis": analysis.model_dump(),
        "trace": [f"{AGENT}: {result['risk_level']} (p={result['flood_probability']:.3f})"],
    }
