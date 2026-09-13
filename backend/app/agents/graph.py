"""
LangGraph StateGraph for the multi-agent pipeline.

    START
      |
      v
  validate_input          resolve the location onto the 1 km grid
      |
      +-----------+-----------+
      v           v           v
    water       urban       flood      three domain agents, run CONCURRENTLY
    agent       agent       agent
      |           |           |
      +-----------+-----------+
                  |
                  v
          building_gate        conditional: run the building agent, or skip
                  |
                  v
            coordinator        reconcile everything
                  |
                  v
                 END

The fan-out is genuine concurrency, not a sequence. Three edges out of
`validate_input` put the domain agents in one superstep, and three edges into
`building_gate` make it a barrier that LangGraph will not execute until all three
have finished. This is safe without a merge reducer because each agent writes only
its own `*_result` / `*_analysis` keys; the two keys that several nodes do append
to, `errors` and `trace`, carry `operator.add` reducers in `CityState`.

The building agent is gated rather than unconditional: it needs the domain models'
output, but only runs when the caller supplied building parameters.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents import (
    building_agent,
    coordinator_agent,
    flood_agent,
    urban_agent,
    water_agent,
)
from app.agents.state import CityState, initial_state
from app.core.errors import InvalidInputError
from app.core.grid import get_cell, nearest_cell

logger = logging.getLogger(__name__)


def _validate_input(state: CityState) -> dict:
    """Entry node: resolve the request onto a real grid cell.

    Accepts either a `grid_id` or a `lat`/`lon` pair. Coordinates are snapped to the
    nearest cell, and the snap distance is recorded so the caller knows the spatial
    resolution of the answer. An unresolvable location fails here rather than
    surfacing as three separate model errors downstream.
    """
    location = state.get("location") or {}
    grid_id = location.get("grid_id")

    if grid_id:
        cell = get_cell(grid_id)
        resolved = {**cell, "resolved_from": "grid_id"}
    elif location.get("lat") is not None and location.get("lon") is not None:
        cell = nearest_cell(float(location["lat"]), float(location["lon"]))
        resolved = {
            **cell,
            "resolved_from": "coordinates",
            "requested_lat": float(location["lat"]),
            "requested_lon": float(location["lon"]),
        }
    else:
        raise InvalidInputError(
            "A location is required: supply either grid_id, or both lat and lon.",
            detail={"received_keys": sorted(location)},
        )

    logger.info(
        "Pipeline start: %s (%s, %s) resolved from %s",
        resolved["grid_id"], resolved["city"], resolved["state"], resolved["resolved_from"],
    )
    return {
        "location": resolved,
        "trace": [f"Input validation: resolved to {resolved['grid_id']} ({resolved['city']})"],
    }


def _building_gate(state: CityState) -> dict:
    """Barrier node joining the three parallel agents.

    It holds no logic of its own: LangGraph will not run it until every inbound edge
    has completed, which is what synchronises the fan-in.
    """
    return {"trace": ["Domain agents complete"]}


def _route_after_gate(state: CityState) -> str:
    """Conditional edge: run the building agent only if it was asked for."""
    return "building_agent" if building_agent.should_run(state) else "coordinator"


def build_graph():
    """Construct and compile the agent graph."""
    graph = StateGraph(CityState)

    graph.add_node("validate_input", _validate_input)
    graph.add_node("water_agent", water_agent.run)
    graph.add_node("urban_agent", urban_agent.run)
    graph.add_node("flood_agent", flood_agent.run)
    graph.add_node("building_gate", _building_gate)
    graph.add_node("building_agent", building_agent.run)
    graph.add_node("coordinator", coordinator_agent.run)

    graph.add_edge(START, "validate_input")

    # Fan out: the three domain agents form one concurrent superstep.
    graph.add_edge("validate_input", "water_agent")
    graph.add_edge("validate_input", "urban_agent")
    graph.add_edge("validate_input", "flood_agent")

    # Fan in: building_gate waits for all three before running.
    graph.add_edge("water_agent", "building_gate")
    graph.add_edge("urban_agent", "building_gate")
    graph.add_edge("flood_agent", "building_gate")

    graph.add_conditional_edges(
        "building_gate",
        _route_after_gate,
        {"building_agent": "building_agent", "coordinator": "coordinator"},
    )
    graph.add_edge("building_agent", "coordinator")
    graph.add_edge("coordinator", END)

    compiled = graph.compile()
    logger.info("Agent graph compiled: 7 nodes, 3 domain agents in parallel")
    return compiled


@lru_cache(maxsize=1)
def get_graph():
    """The compiled graph, built once per process."""
    return build_graph()


def graph_topology() -> dict:
    """A description of the graph, for the API to expose."""
    return {
        "framework": "LangGraph StateGraph",
        "state_schema": "CityState",
        "nodes": [
            {"name": "validate_input", "kind": "validation",
             "description": "Resolve the request onto the 1 km analysis grid."},
            {"name": "water_agent", "kind": "domain_agent", "model": "Model 1 — Surface Water",
             "parallel_group": "domain", "description": "Interpret surface-water classification."},
            {"name": "urban_agent", "kind": "domain_agent", "model": "Model 2 — Urban Expansion",
             "parallel_group": "domain", "description": "Interpret expansion suitability."},
            {"name": "flood_agent", "kind": "domain_agent", "model": "Model 3 — Flood Risk",
             "parallel_group": "domain", "description": "Interpret flood susceptibility."},
            {"name": "building_gate", "kind": "barrier",
             "description": "Join the parallel domain agents; route to the building agent."},
            {"name": "building_agent", "kind": "domain_agent",
             "model": "Sustainable Building Planner (rules)", "conditional": True,
             "description": "Interpret deterministic building recommendations."},
            {"name": "coordinator", "kind": "coordinator",
             "description": "Reconcile all domains, identify trade-offs, issue the verdict."},
        ],
        "parallelism": (
            "water_agent, urban_agent and flood_agent execute concurrently in one "
            "superstep; building_gate is a barrier that waits for all three."
        ),
        "conditional_edges": {
            "building_gate": "building_agent when building_params supplied, else coordinator"
        },
        "principle": (
            "LLM agents interpret predictive model outputs; they do not replace the "
            "predictive models. Each *_result key holds untouched model output; each "
            "*_analysis key holds an agent's interpretation of it."
        ),
    }


def run_pipeline(
    *,
    grid_id: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    building_params: dict | None = None,
    include_attribution: bool = True,
) -> dict:
    """Execute the full pipeline for one location.

    Supply either `grid_id` or both `lat` and `lon`.
    """
    location: dict = {}
    if grid_id:
        location["grid_id"] = grid_id
    if lat is not None and lon is not None:
        location["lat"], location["lon"] = lat, lon
    if not location:
        raise InvalidInputError(
            "A location is required: supply either grid_id, or both lat and lon."
        )

    state = initial_state(
        location,
        building_params=building_params,
        options={"include_attribution": include_attribution},
    )
    result = dict(get_graph().invoke(state))
    logger.info(
        "Pipeline complete for %s: %d trace steps, %d errors",
        result.get("location", {}).get("grid_id"),
        len(result.get("trace", [])), len(result.get("errors", [])),
    )
    return result
