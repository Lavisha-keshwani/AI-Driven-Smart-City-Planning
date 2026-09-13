"""Sustainable Building Planner endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.agents import building_agent
from app.agents.state import initial_state
from app.core import building_guidelines as bg
from app.core.grid import nearest_cell
from app.schemas.requests import BuildingParams, NasaPowerRequest
from app.schemas.responses import BuildingPlannerResponse
from app.services.building_planner import nasa_power
from app.services.building_planner.recommendation_engine import generate_recommendations
from app.services.building_planner.site_analyzer import analyze_site

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/building-planner", tags=["building-planner"])


@router.post("", response_model=BuildingPlannerResponse)
def plan_building(params: BuildingParams, interpret: bool = Query(default=True)):
    """Assess a building site and generate sustainability recommendations.

    The recommendations are produced entirely by the deterministic rules engine from
    the site's model predictions, NASA POWER climatology and cited guideline
    parameters. With `interpret=true` the Building Sustainability Agent adds a
    plain-language reading of that output; it cannot change any recommendation.
    """
    payload = params.model_dump()
    site = analyze_site(params.lat, params.lon)
    planner = generate_recommendations(site, payload)

    interpretation = None
    if interpret:
        cell = nearest_cell(params.lat, params.lon)
        state = initial_state(cell, building_params=payload)
        node = building_agent.run(state)
        analysis = node.get("building_analysis")
        if analysis:
            interpretation = analysis

    return BuildingPlannerResponse(
        site=site,
        recommendations=planner["recommendations"],
        skipped_rules=planner["skipped_rules"],
        priority_counts=planner["priority_counts"],
        guidelines_applied=planner["guidelines_applied"],
        disclaimer=planner["disclaimer"],
        interpretation=interpretation,
    )


@router.get("/site")
def assess_site(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    """Site conditions only, without building parameters or recommendations."""
    return analyze_site(lat, lon)


@router.get("/guidelines")
def guidelines():
    """Every guideline parameter the planner applies, with its provenance.

    Entries marked `origin: "guideline"` cite a published reference; entries marked
    `origin: "project_assumption"` are this project's modelling assumptions and carry
    no regulatory weight. Compliance is not verified.
    """
    return bg.export()


@router.post("/nasa-power")
def query_nasa_power(request: NasaPowerRequest):
    """Query NASA POWER directly.

    With `start_date` and `end_date`, returns the daily series. Without them, returns
    the long-term monthly climatology the planner uses.
    """
    if request.start_date and request.end_date:
        return nasa_power.get_nasa_power_data(
            request.latitude, request.longitude, request.start_date, request.end_date
        )
    return nasa_power.get_climatology(request.latitude, request.longitude)
