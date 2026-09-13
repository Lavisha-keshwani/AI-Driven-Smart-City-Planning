"""
Coordinator Agent — synthesis and trade-off reasoning.

Receives every domain agent's output and produces one explainable recommendation.
Its defining constraint: it never alters an underlying prediction. It reconciles
them.

The design deliberately splits detection from narration:

  1. `detect_conflicts` finds tensions between domains with deterministic rules, so
     a genuine conflict is never missed because the LLM overlooked it.
  2. `_baseline_recommendation` derives the headline decision from those same rules,
     so the decision is reproducible and testable.
  3. The LLM then explains the synthesis in language a planner can act on.

If the LLM produces a decision that contradicts the deterministic baseline in the
unsafe direction — a more permissive verdict than the evidence supports — the
baseline wins and the override is recorded. Ecological constraints stay visible: a
favourable urban score never suppresses a flood or water finding.
"""

from __future__ import annotations

import logging

from app.agents import base, llm
from app.agents.schemas import CoordinatorReport, CoordinatorResult, TradeOff
from app.agents.state import CityState

logger = logging.getLogger(__name__)

AGENT = "Coordinator Agent"

# Verdicts ordered from most to least permissive. Used to stop the LLM relaxing a
# conclusion the deterministic rules reached.
_PERMISSIVENESS = {
    "proceed": 0,
    "proceed_with_conditions": 1,
    "proceed_with_strong_mitigation": 2,
    "discourage": 3,
    "insufficient_evidence": 4,
}

TASK = (
    "You are the Coordinator in a multi-agent urban-planning decision-support system. "
    "Domain agents have each analysed the same location: water/environment, urban "
    "expansion, flood/resilience, and optionally a building sustainability assessment.\n\n"
    "Your task is to synthesise them into one recommendation a planner can act on:\n"
    "  1. Reconcile the domains, naming every real conflict between them.\n"
    "  2. For each conflict, say how development should proceed given the tension.\n"
    "  3. State the conditions that would make development acceptable here.\n"
    "  4. List priority actions in order.\n"
    "  5. Name the evidence gaps that limit your conclusion.\n\n"
    "Hard constraints:\n"
    "  - You must not alter any model prediction. Reconcile them; never re-estimate one.\n"
    "  - A high urban-suitability score is a statement about historical growth pressure, "
    "not an environmental endorsement. It must never be allowed to suppress a flood or "
    "water finding. Water resilience, flood exposure and ecological constraints stay "
    "visible in your conclusion even when development pressure is favourable.\n"
    "  - A deterministic baseline verdict is supplied. You may make the recommendation "
    "MORE cautious than the baseline if the evidence warrants, never less.\n"
    "  - Where a domain is unavailable, treat it as an evidence gap, not as a pass."
)


def _domain_signals(state: CityState) -> dict:
    """Extract the comparable signal from each domain, in code."""
    water = state.get("water_result") or {}
    urban = state.get("urban_result") or {}
    flood = state.get("flood_result") or {}
    building = state.get("building_result") or {}

    signals: dict = {
        "water": {
            "available": bool(water),
            "is_water_body": water.get("is_water_body"),
            "water_body_probability": water.get("water_body_probability"),
            "status": (water.get("water_body_status") or {}).get("status"),
            "inter_annual_reliability":
                (water.get("water_body_status") or {}).get("inter_annual_reliability"),
        },
        "urban": {
            "available": bool(urban),
            "suitability_class": urban.get("suitability_class"),
            "suitability_score": urban.get("suitability_score"),
            "confidence": urban.get("confidence"),
            "constraints": [c["constraint"] for c in urban.get("constraints", [])],
        },
        "flood": {
            "available": bool(flood),
            "flood_probability": flood.get("flood_probability"),
            "risk_level": flood.get("risk_level"),
            "drivers": [d["driver"] for d in flood.get("risk_drivers", [])],
        },
        "building": {
            "available": bool(building),
            "recommendation_count": len(building.get("recommendations", [])),
            "high_priority_count": (building.get("priority_counts") or {}).get("HIGH"),
        },
    }
    return signals


def _agent_digest(state: CityState, *, max_items: int = 4) -> dict:
    """Condense each agent's analysis to its conclusions.

    Keeps the reasoning the Coordinator needs to reconcile the domains, while
    leaving out evidence blocks it already has in `signals`.
    """
    digest: dict = {}
    for domain in ("water", "urban", "flood", "building"):
        analysis = state.get(f"{domain}_analysis")
        if not analysis:
            continue
        result = analysis.get("result", {})
        digest[domain] = {
            "summary": result.get("summary"),
            "findings": (result.get("findings") or [])[:max_items],
            "risks": (result.get("risks") or [])[:max_items],
            "recommendations": (result.get("recommendations") or [])[:max_items],
            "uncertainty": result.get("uncertainty"),
            "interpretation_source": analysis.get("source"),
        }
    return digest


def detect_conflicts(signals: dict) -> list[dict]:
    """Find tensions between domains using deterministic rules.

    These are the cases the specification calls out, generalised: development
    pressure set against physical and ecological constraint.
    """
    conflicts: list[dict] = []
    urban_class = signals["urban"].get("suitability_class")
    flood_level = signals["flood"].get("risk_level")
    flood_probability = signals["flood"].get("flood_probability")
    is_water_body = signals["water"].get("is_water_body")
    water_status = signals["water"].get("status")

    # Development pressure against flood exposure.
    if urban_class in {"GREEN", "YELLOW"} and flood_level in {"HIGH", "MODERATE"}:
        severity = (
            "high" if urban_class == "GREEN" and flood_level == "HIGH"
            else "moderate"
        )
        conflicts.append({
            "type": "growth_pressure_vs_flood_exposure",
            "severity": severity,
            "between": ["urban", "flood"],
            "description": (
                f"The area shows {urban_class} expansion suitability while flood risk is "
                f"{flood_level} (probability "
                f"{flood_probability:.0%})." if flood_probability is not None else
                f"The area shows {urban_class} expansion suitability while flood risk is "
                f"{flood_level}."
            ),
            "implication": (
                "Growth pressure and flood exposure coincide, which is how flood-exposed "
                "development happens. Expansion should not proceed unrestricted."
            ),
        })

    # Development pressure on a surface-water body.
    if urban_class in {"GREEN", "YELLOW"} and is_water_body:
        conflicts.append({
            "type": "growth_pressure_vs_water_body",
            "severity": "high",
            "between": ["urban", "water"],
            "description": (
                f"The cell is classified as a surface-water body ({water_status} regime) "
                f"yet carries {urban_class} expansion suitability."
            ),
            "implication": (
                "Building here would encroach on surface water, removing storage capacity "
                "and worsening flood risk downstream. Statutory setbacks apply."
            ),
        })

    # Water dependability against development.
    if (
        urban_class in {"GREEN", "YELLOW"}
        and signals["water"].get("inter_annual_reliability") in {"low", "none"}
        and not is_water_body
    ):
        conflicts.append({
            "type": "growth_pressure_vs_water_availability",
            "severity": "moderate",
            "between": ["urban", "water"],
            "description": (
                "The area is favourable for expansion but has no dependable local surface "
                "water."
            ),
            "implication": (
                "New demand would fall on piped supply or groundwater. Water-supply "
                "capacity should be confirmed before growth is committed."
            ),
        })

    # Low development suitability with otherwise benign conditions: still discourage.
    if urban_class == "RED" and flood_level == "LOW":
        conflicts.append({
            "type": "low_suitability_despite_low_hazard",
            "severity": "low",
            "between": ["urban", "flood"],
            "description": (
                "Flood risk is low, but the area sits in the lowest observed-growth class."
            ),
            "implication": (
                "Absence of hazard is not a reason to expand. Low growth propensity "
                "usually reflects poor access or servicing economics."
            ),
        })

    # Flood hazard on a water body — compounding physical constraint.
    if is_water_body and flood_level in {"HIGH", "MODERATE"}:
        conflicts.append({
            "type": "water_body_with_flood_exposure",
            "severity": "high",
            "between": ["water", "flood"],
            "description": (
                f"The cell holds surface water and carries {flood_level} flood risk."
            ),
            "implication": (
                "These reinforce each other: the water body is both an asset to protect "
                "and an indicator of inundation exposure."
            ),
        })

    return conflicts


def _baseline_recommendation(signals: dict, conflicts: list[dict]) -> tuple[str, list[str]]:
    """Derive the headline verdict deterministically.

    Returns `(verdict, reasons)`. This is the reproducible decision the LLM explains
    and may tighten but not loosen.
    """
    reasons: list[str] = []

    available = [d for d in ("water", "urban", "flood") if signals[d]["available"]]
    if len(available) < 2:
        return "insufficient_evidence", [
            f"Only {len(available)} of the three domain models produced a result "
            f"({', '.join(available) or 'none'}), which is not enough to reconcile."
        ]

    urban_class = signals["urban"].get("suitability_class")
    flood_level = signals["flood"].get("risk_level")
    is_water_body = signals["water"].get("is_water_body")

    # An ecological hard stop: never recommend building on a surface-water body.
    if is_water_body:
        reasons.append(
            "The cell is classified as a surface-water body, so development would "
            "encroach on surface water regardless of growth potential."
        )
        return "discourage", reasons

    # Low growth propensity: discourage regardless of other favourable factors.
    if urban_class == "RED":
        reasons.append(
            "Urban expansion suitability is RED, the lowest observed-growth class, so "
            "expansion is discouraged whatever the other indicators show."
        )
        if flood_level == "HIGH":
            reasons.append("Flood risk is also HIGH, reinforcing the conclusion.")
        return "discourage", reasons

    if flood_level == "HIGH":
        reasons.append(
            f"Flood risk is HIGH (probability "
            f"{signals['flood']['flood_probability']:.0%}), so unrestricted development "
            f"is not acceptable here."
        )
        if urban_class == "GREEN":
            reasons.append(
                "Expansion suitability is GREEN, which is precisely the combination that "
                "produces flood-exposed development if left unmanaged."
            )
            return "proceed_with_strong_mitigation", reasons
        reasons.append("Expansion suitability is only conditional, compounding the hazard.")
        return "discourage", reasons

    if flood_level == "MODERATE":
        reasons.append(
            f"Flood risk is MODERATE (probability "
            f"{signals['flood']['flood_probability']:.0%}), requiring resilience measures."
        )
        return "proceed_with_conditions", reasons

    # Flood risk LOW from here on.
    if urban_class == "GREEN":
        if any(c["severity"] in {"high", "moderate"} for c in conflicts):
            reasons.append(
                "Expansion suitability is GREEN with low flood risk, but unresolved "
                "cross-domain conflicts remain."
            )
            return "proceed_with_conditions", reasons
        reasons.append(
            "Expansion suitability is GREEN and flood risk is LOW, the most favourable "
            "combination in this framework."
        )
        reasons.append(
            "Flood recall is moderate, so LOW is absence of evidence rather than proof "
            "of safety; standard drainage design still applies."
        )
        return "proceed", reasons

    reasons.append(
        "Expansion suitability is conditional (YELLOW) with low modelled flood risk, so "
        "development is acceptable once servicing and site constraints are resolved."
    )
    return "proceed_with_conditions", reasons


def _fallback_result(
    signals: dict, conflicts: list[dict], verdict: str, reasons: list[str], state: CityState
) -> CoordinatorResult:
    """Deterministic synthesis, used when the LLM is unavailable."""
    location = state.get("location", {})
    gaps = [
        f"The {domain} model produced no result for this location."
        for domain in ("water", "urban", "flood")
        if not signals[domain]["available"]
    ]
    if not signals["building"]["available"]:
        gaps.append(
            "No building parameters were supplied, so no site-level sustainability "
            "assessment was produced."
        )

    conditions: list[str] = []
    if signals["flood"].get("risk_level") in {"HIGH", "MODERATE"}:
        conditions.append(
            "Flood-resilience measures: raised plinth, flood-resistant ground-floor "
            "construction, backflow prevention and on-site detention."
        )
    if signals["water"].get("is_water_body"):
        conditions.append(
            "Confirm statutory setbacks from the surface-water body and protect its extent."
        )
    if signals["water"].get("inter_annual_reliability") in {"low", "none"}:
        conditions.append(
            "Confirm water-supply capacity, since local surface water is not dependable."
        )
    for constraint in signals["urban"].get("constraints", []):
        conditions.append(f"Resolve the site constraint: {constraint.replace('_', ' ')}.")

    return CoordinatorResult(
        overall_recommendation=verdict,  # type: ignore[arg-type]
        headline=(
            f"{verdict.replace('_', ' ').capitalize()} for "
            f"{location.get('city', 'this location')} cell {location.get('grid_id', '')}."
        ),
        rationale=" ".join(reasons),
        trade_offs=[
            TradeOff(
                between=c["between"],
                tension=c["description"],
                resolution=c["implication"],
            )
            for c in conflicts
        ],
        conditions=conditions,
        priority_actions=[
            c["implication"] for c in conflicts
            if c["severity"] == "high"
        ] or conditions[:3],
        evidence_gaps=gaps + [
            "Synthesis generated deterministically without LLM interpretation."
        ],
    )


def run(state: CityState) -> dict:
    """LangGraph node: reconcile all domains into one explainable recommendation."""
    signals = _domain_signals(state)
    conflicts = detect_conflicts(signals)
    verdict, reasons = _baseline_recommendation(signals, conflicts)

    # The prompt carries the decision-relevant digest, not the full model payloads.
    # `signals` already holds every number the synthesis turns on, and each agent's
    # own reading is condensed to its conclusions. The untouched model outputs stay
    # in the API response; sending them here would only inflate the prompt.
    evidence = {
        "location": {
            k: state.get("location", {}).get(k) for k in ("grid_id", "city", "state")
        },
        "domain_signals": signals,
        "detected_conflicts": conflicts,
        "deterministic_baseline": {
            "verdict": verdict,
            "reasons": reasons,
            "note": (
                "Derived by deterministic rules. You may be more cautious than this "
                "verdict, never less."
            ),
        },
        "domain_agent_conclusions": _agent_digest(state),
        "errors": state.get("errors", []),
    }

    prompt = (
        f"{TASK}\n\n"
        f"EVIDENCE (authoritative — use these values exactly, do not recompute):\n"
        f"{base.render_evidence(evidence)}\n\n"
        f"Produce the synthesis."
    )
    result, meta = llm.structured_call(prompt, CoordinatorResult, context=AGENT)

    note = meta.get("note")
    if result is None:
        result = _fallback_result(signals, conflicts, verdict, reasons, state)
    else:
        # Guard the safety direction: the LLM may tighten, never loosen.
        if _PERMISSIVENESS.get(result.overall_recommendation, 0) < _PERMISSIVENESS[verdict]:
            logger.warning(
                "Coordinator: LLM verdict '%s' is more permissive than the deterministic "
                "baseline '%s'; keeping the baseline.",
                result.overall_recommendation, verdict,
            )
            note = (
                f"The LLM proposed '{result.overall_recommendation}', which is more "
                f"permissive than the deterministic baseline '{verdict}'. The baseline was "
                f"kept. " + (note or "")
            ).strip()
            result.overall_recommendation = verdict  # type: ignore[assignment]

        # Ensure every deterministically detected conflict is represented.
        represented = {tuple(sorted(t.between)) for t in result.trade_offs}
        for conflict in conflicts:
            if tuple(sorted(conflict["between"])) not in represented:
                result.trade_offs.append(
                    TradeOff(
                        between=conflict["between"],
                        tension=conflict["description"],
                        resolution=conflict["implication"],
                    )
                )

    report = CoordinatorReport(
        result=result,
        signals=signals,
        detected_conflicts=conflicts,
        source=meta["source"],
        llm_model=meta.get("llm_model"),
        note=note,
    )
    logger.info(
        "%s: verdict=%s conflicts=%d source=%s",
        AGENT, result.overall_recommendation, len(conflicts), meta["source"],
    )
    return {
        "coordinator_result": report.model_dump(),
        "trace": [
            f"{AGENT}: {result.overall_recommendation} ({len(conflicts)} conflicts detected)"
        ],
    }
