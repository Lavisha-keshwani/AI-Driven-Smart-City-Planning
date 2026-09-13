"""
LangGraph shared state.

`CityState` is the single object that flows through the graph. Nodes read what they
need and return only the keys they own, which is what lets the three domain agents
run concurrently without a reducer: no two of them ever write the same key.

The raw/analysis split is deliberate and is the project's core architectural
boundary:

    *_result    what the ML model or rules engine produced — the ground truth
    *_analysis  the agent's interpretation of that result

An agent writes only to its `*_analysis` key. The `*_result` values are written by
model-inference code and are never mutated afterwards, so the Coordinator and the
API both see exactly the numbers the models produced.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class CityState(TypedDict, total=False):
    """State passed between graph nodes."""

    # ── Input ────────────────────────────────────────────────────────────────
    location: dict            # {grid_id, lat, lon, city, state, ...}
    building_params: dict | None
    options: dict             # {include_attribution: bool, ...}

    # ── Model and rules output (written by inference nodes, never by agents) ──
    water_result: dict
    urban_result: dict
    flood_result: dict
    building_result: dict

    # ── Agent interpretations (one key per agent, so writes never collide) ────
    water_analysis: dict
    urban_analysis: dict
    flood_analysis: dict
    building_analysis: dict

    # ── Coordinator synthesis ────────────────────────────────────────────────
    coordinator_result: dict

    # ── Diagnostics. Appended to concurrently, so it needs a merge reducer. ───
    errors: Annotated[list[dict], operator.add]
    trace: Annotated[list[str], operator.add]


def initial_state(
    location: dict,
    *,
    building_params: dict | None = None,
    options: dict | None = None,
) -> CityState:
    """Build a fresh state for one pipeline run."""
    return {
        "location": location,
        "building_params": building_params,
        "options": options or {},
        "errors": [],
        "trace": [],
    }
