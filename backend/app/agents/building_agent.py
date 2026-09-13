"""
Building Sustainability Agent — interprets the Sustainable Building Planner.

Runs the deterministic rules engine, then explains its output to a citizen. The
rules decide what is recommended and compute every figure; the agent explains and
prioritises. It is explicitly forbidden from overriding a rule, and the rules it was
given — including the ones that did not fire, and why — are all in its evidence, so
it can explain an absence rather than filling it with invention.

This node runs after the three domain agents so the planner can consume their
model outputs, and is skipped when the caller supplies no building parameters.
"""

from __future__ import annotations

import logging

from app.agents import base
from app.agents.schemas import AgentResult
from app.agents.state import CityState
from app.core import building_guidelines as bg
from app.core.errors import SmartCityError
from app.services.building_planner.recommendation_engine import generate_recommendations
from app.services.building_planner.site_analyzer import analyze_site

logger = logging.getLogger(__name__)

DOMAIN = "building"
AGENT = "Building Sustainability Agent"

TASK = (
    "A deterministic rules engine has assessed a building site and produced "
    "sustainability recommendations. Every recommendation, priority and number in the "
    "evidence was computed by that engine from cited guideline parameters and the site's "
    "model predictions and measured climate.\n\n"
    "Your job is to explain those recommendations to the person who will build here, in "
    "plain language, and to say which to do first and why. You may not add a "
    "recommendation the engine did not produce, change a priority, or alter a number. "
    "Where a rule was skipped, the reason is in the evidence — explain that honestly "
    "rather than proposing the measure anyway.\n\n"
    "Do not give structural engineering instructions and do not state or imply that any "
    "design complies with a building code. Guideline references are design references "
    "only; compliance has not been verified."
)


def should_run(state: CityState) -> bool:
    """The building agent only runs when the caller asked for a building assessment."""
    return bool(state.get("building_params"))


def _format_figures(calculations: dict, *, limit: int = 6) -> str:
    """Render a rule's calculations as a compact, readable clause."""
    parts = []
    for key, value in calculations.items():
        if key in {"formula", "basis", "note"} or isinstance(value, (dict, list)):
            continue
        parts.append(f"{key}={value}")
        if len(parts) >= limit:
            break
    return ", ".join(parts) or "none"


def _evidence(site: dict, planner: dict, params: dict) -> dict:
    """Assemble the planner's own output as evidence, without the bulky internals."""
    return {
        "building_parameters": params,
        "site_location": site["location"],
        "site_derived_conditions": site["derived"],
        "measured_climate": {
            k: v for k, v in (site["measured"].get("climate") or {}).items()
            if not k.startswith("monthly_") and k not in {"units", "requested"}
        },
        "model_predictions_used": {
            "flood_risk": (
                {
                    "flood_probability": site["model_predictions"]["flood_risk"]["flood_probability"],
                    "risk_level": site["model_predictions"]["flood_risk"]["risk_level"],
                }
                if site["model_predictions"].get("flood_risk") else None
            ),
            "surface_water": (
                {
                    "classification": site["model_predictions"]["surface_water"]["classification"],
                    "water_body_probability":
                        site["model_predictions"]["surface_water"]["water_body_probability"],
                }
                if site["model_predictions"].get("surface_water") else None
            ),
            "urban_expansion": (
                {
                    "suitability_class":
                        site["model_predictions"]["urban_expansion"]["suitability_class"],
                    "suitability_score":
                        site["model_predictions"]["urban_expansion"]["suitability_score"],
                }
                if site["model_predictions"].get("urban_expansion") else None
            ),
        },
        # Flattened to strings on purpose. When these were nested objects, the model
        # mirrored that shape back into the list[str] schema fields and the structured
        # call was rejected. Strings also keep the prompt compact.
        "rule_based_recommendations": [
            f"[{r['priority']}] ({r['category']}) {r['recommendation']}. "
            f"Reason: {r['reason']} "
            f"Key figures: {_format_figures(r['calculations'])}"
            for r in planner["recommendations"]
        ],
        "rules_that_did_not_fire": planner["skipped_rules"],
        "priority_counts": planner["priority_counts"],
        "unavailable_evidence": site["unavailable"],
        "disclaimer": bg.DISCLAIMER,
    }


def _fallback(planner: dict, params: dict) -> AgentResult:
    recommendations = planner["recommendations"]
    high = [r for r in recommendations if r["priority"] == "HIGH"]

    return AgentResult(
        domain=DOMAIN,
        summary=(
            f"The planner produced {len(recommendations)} recommendations for this "
            f"{params['building_type']} building on a {params['plot_size_sqm']:.0f} m2 plot, "
            f"{len(high)} of them high priority."
        ),
        findings=[f"{r['priority']}: {r['recommendation']} — {r['reason']}" for r in recommendations],
        risks=[
            f"{s['rule']} was not applied: {s['reason']}" for s in planner["skipped_rules"]
        ] or ["All applicable rules were evaluated."],
        recommendations=[r["recommendation"] for r in high] or
                        [r["recommendation"] for r in recommendations[:3]],
        uncertainty=(
            "Generated without LLM interpretation. All figures are planning-stage "
            "estimates from cited guideline parameters and are not verified for code "
            "compliance."
        ),
        interpretation_confidence="medium",
    )


def run(state: CityState) -> dict:
    """LangGraph node: run the planner rules, then have the LLM explain them."""
    params = state.get("building_params")
    if not params:
        return {"trace": [f"{AGENT}: skipped (no building parameters supplied)"]}

    location = state["location"]
    lat = params.get("lat", location.get("lat"))
    lon = params.get("lon", location.get("lon"))

    try:
        site = analyze_site(lat, lon)
        planner = generate_recommendations(site, params)
    except SmartCityError as exc:
        logger.warning("%s: planner failed — %s", AGENT, exc.message)
        return {
            "building_result": {},
            "building_analysis": base.failure_analysis(
                domain=DOMAIN, agent=AGENT, model_name="Sustainable Building Planner", exc=exc,
            ).model_dump(),
            "errors": [base.error_entry(DOMAIN, exc)],
            "trace": [f"{AGENT}: failed ({exc.error_code})"],
        }

    building_result = {
        "site": site,
        "recommendations": planner["recommendations"],
        "skipped_rules": planner["skipped_rules"],
        "priority_counts": planner["priority_counts"],
        "guidelines_applied": planner["guidelines_applied"],
        "disclaimer": planner["disclaimer"],
    }

    analysis = base.interpret(
        domain=DOMAIN,
        agent=AGENT,
        model_name="Sustainable Building Planner (deterministic rules)",
        task=TASK,
        evidence=_evidence(site, planner, params),
        fallback=_fallback(planner, params),
    )
    return {
        "building_result": building_result,
        "building_analysis": analysis.model_dump(),
        "trace": [
            f"{AGENT}: {len(planner['recommendations'])} recommendations "
            f"({planner['priority_counts']['HIGH']} high priority)"
        ],
    }
