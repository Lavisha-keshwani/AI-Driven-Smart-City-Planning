"""
Multi-agent pipeline endpoints.

`POST /api/agents/analyze` runs the whole LangGraph pipeline. `POST /api/coordinator`
is the same run presented coordinator-first, for callers that want the verdict and
trade-offs at the top of the payload.

Individual domain agents are also exposed so an evaluator can inspect one agent's
reasoning in isolation, without paying for the full pipeline.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.agents import (
    building_agent,
    coordinator_agent,
    flood_agent,
    llm,
    urban_agent,
    water_agent,
)
from app.agents.graph import graph_topology, run_pipeline
from app.agents.state import initial_state
from app.core.errors import InvalidInputError
from app.core.grid import get_cell, nearest_cell
from app.schemas.requests import GridQuery, PipelineRequest
from app.schemas.responses import AgentInfoResponse, PipelineResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agents"])

_DOMAIN_AGENTS = {
    "water": water_agent,
    "urban": urban_agent,
    "flood": flood_agent,
}

PRINCIPLE = (
    "LLM agents interpret predictive model outputs; they do not replace the "
    "predictive models. Every probability, score and classification is produced by a "
    "trained model or a deterministic rules engine. Agents add interpretation, and the "
    "Coordinator reconciles domains without altering any prediction."
)


def _run(request: PipelineRequest) -> dict:
    return run_pipeline(
        grid_id=request.grid_id,
        lat=request.lat,
        lon=request.lon,
        building_params=(
            request.building_params.model_dump() if request.building_params else None
        ),
        include_attribution=request.include_attribution,
    )


@router.post("/agents/analyze", response_model=PipelineResponse)
def analyze(request: PipelineRequest):
    """Run the full multi-agent pipeline for a location.

    Executes input validation, the three domain agents in parallel, the Building
    Sustainability Agent when building parameters are supplied, and the Coordinator.
    """
    return PipelineResponse(**_run(request))


@router.post("/coordinator")
def coordinate(request: PipelineRequest):
    """Run the pipeline and return the Coordinator's synthesis first.

    Same computation as `/api/agents/analyze`; the payload leads with the verdict and
    trade-offs, then carries the domain detail beneath.
    """
    state = _run(request)
    coordinator = state.get("coordinator_result") or {}
    return {
        "location": state.get("location", {}),
        "recommendation": coordinator.get("result"),
        "detected_conflicts": coordinator.get("detected_conflicts", []),
        "domain_signals": coordinator.get("signals", {}),
        "interpretation_source": coordinator.get("source"),
        "llm_model": coordinator.get("llm_model"),
        "note": coordinator.get("note"),
        "domains": {
            "water": {
                "model_output": state.get("water_result"),
                "analysis": state.get("water_analysis"),
            },
            "urban": {
                "model_output": state.get("urban_result"),
                "analysis": state.get("urban_analysis"),
            },
            "flood": {
                "model_output": state.get("flood_result"),
                "analysis": state.get("flood_analysis"),
            },
            "building": {
                "model_output": state.get("building_result"),
                "analysis": state.get("building_analysis"),
            },
        },
        "trace": state.get("trace", []),
        "errors": state.get("errors", []),
        "principle": PRINCIPLE,
    }


@router.post("/agents/{domain}")
def run_single_agent(domain: str, query: GridQuery):
    """Run one domain agent on its own.

    `domain` is water, urban or flood. The building agent needs building parameters,
    so it is reached through /api/building-planner instead.
    """
    agent = _DOMAIN_AGENTS.get(domain.lower())
    if agent is None:
        raise InvalidInputError(
            f"Unknown agent domain '{domain}'.",
            detail={
                "available": sorted(_DOMAIN_AGENTS),
                "note": (
                    "The building agent requires building parameters; use "
                    "POST /api/building-planner."
                ),
            },
        )

    cell = get_cell(query.grid_id) if query.grid_id else nearest_cell(query.lat, query.lon)
    state = initial_state(cell, options={"include_attribution": query.include_attribution})
    output = agent.run(state)

    return {
        "location": cell,
        "model_output": output.get(f"{domain.lower()}_result"),
        "analysis": output.get(f"{domain.lower()}_analysis"),
        "trace": output.get("trace", []),
        "errors": output.get("errors", []),
        "principle": PRINCIPLE,
    }


@router.get("/agents", response_model=AgentInfoResponse)
def list_agents():
    """The agents in the system, their models, and their role boundaries."""
    return AgentInfoResponse(
        topology=graph_topology(),
        agents=[
            {
                "domain": "water",
                "agent": water_agent.AGENT,
                "wraps": "Model 1 — Surface Water Monitoring",
                "responsibility": (
                    "Interpret the surface-water classification and the observed Global "
                    "Surface Water record; explain water availability and environmental "
                    "implications."
                ),
                "may_not": "Produce or alter a surface-water prediction.",
            },
            {
                "domain": "urban",
                "agent": urban_agent.AGENT,
                "wraps": "Model 2 — Urban Expansion Suitability",
                "responsibility": (
                    "Explain the suitability score and GREEN/YELLOW/RED class, and what "
                    "they mean for growth decisions."
                ),
                "may_not": "Invent a suitability judgement independent of the model.",
            },
            {
                "domain": "flood",
                "agent": flood_agent.AGENT,
                "wraps": "Model 3 — Urban Flood Risk",
                "responsibility": (
                    "Interpret the flood probability, identify resilience concerns and "
                    "explain how much weight the result carries."
                ),
                "may_not": "Produce or alter a flood probability.",
            },
            {
                "domain": "building",
                "agent": building_agent.AGENT,
                "wraps": "Sustainable Building Planner (deterministic rules)",
                "responsibility": (
                    "Explain the rule-based recommendations and NASA POWER site data to "
                    "a citizen, and prioritise them."
                ),
                "may_not": (
                    "Override a deterministic rule, change a priority, or add a "
                    "recommendation the rules did not produce."
                ),
            },
            {
                "domain": "coordinator",
                "agent": coordinator_agent.AGENT,
                "wraps": "All domain agents",
                "responsibility": (
                    "Reconcile the domains, name the trade-offs, and issue one "
                    "explainable recommendation. Conflict detection and the baseline "
                    "verdict are deterministic; the LLM explains them and may only make "
                    "the conclusion more cautious, never less."
                ),
                "may_not": "Alter any underlying model prediction.",
            },
        ],
        llm=llm.llm_status(),
        principle=PRINCIPLE,
    )
