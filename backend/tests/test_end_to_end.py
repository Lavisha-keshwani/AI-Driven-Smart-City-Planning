"""
End-to-end workflow test.

One test walks the entire documented pipeline against a real grid cell, and asserts
the invariants that matter at each hop:

    real location on the 1 km grid
      -> environmental data retrieved (NASA POWER, mocked for determinism)
      -> Model 1 surface water
      -> Model 2 urban expansion
      -> Model 3 flood risk
      -> Sustainable Building Planner rules
      -> LangGraph domain agents
      -> Coordinator synthesis
      -> structured, React-consumable response

The grid cell is discovered from the project's own data — never invented — and is
chosen to exercise the hardest trade-off: favourable growth suitability coinciding
with elevated flood risk.
"""

from __future__ import annotations

import pytest

from app.core.grid import grid_metadata
from app.services.models import flood_risk, urban_expansion
from tests.conftest import requires_models

pytestmark = requires_models


CLIMATE = {
    "solar_kwh_m2_day": 5.2,
    "temperature_c": 29.4,
    "temperature_max_c": 36.1,
    "temperature_min_c": 21.0,
    "humidity_pct": 74.0,
    "wind_speed_m_s": 2.8,
    "rainfall_annual_mm": 1320.0,
    "monthly_rainfall_mm": {"JUL": 380.0},
    "wettest_month": "JUL",
    "monsoon_concentration": 0.72,
}


@pytest.fixture(scope="module")
def conflict_cell() -> dict:
    """A real cell where growth suitability and flood risk are in tension.

    Scans a real city's cells for the GREEN-suitability + elevated-flood combination.
    Falls back to any real cell if that pairing does not occur, so the test still
    exercises the full pipeline rather than skipping.
    """
    metadata = grid_metadata()
    city = str(metadata.iloc[0]["city"])

    urban = {c["grid_id"]: c for c in urban_expansion.predict_city(city, limit=600)}
    flood = {c["grid_id"]: c for c in flood_risk.predict_city(city, limit=600)}

    best = None
    for grid_id, urban_cell in urban.items():
        flood_cell = flood.get(grid_id)
        if not flood_cell:
            continue
        if (
            urban_cell["suitability_class"] == "GREEN"
            and flood_cell["risk_level"] in {"HIGH", "MODERATE"}
        ):
            return {"grid_id": grid_id, "city": city, "kind": "growth_flood_conflict"}
        best = best or {"grid_id": grid_id, "city": city, "kind": "no_conflict_found"}

    assert best, f"No cells returned for {city}"
    return best


def test_full_workflow_produces_a_frontend_ready_recommendation(
    client, conflict_cell, monkeypatch
):
    """Walk the whole pipeline and check every stage's contract."""
    from app.services.building_planner import nasa_power

    monkeypatch.setattr(nasa_power, "get_climatology", lambda lat, lon: dict(CLIMATE))

    grid_id = conflict_cell["grid_id"]

    # ── Stage 1: the location is real and resolvable ─────────────────────────
    cell = client.get(f"/api/grid/cell/{grid_id}").json()
    assert cell["grid_id"] == grid_id
    assert cell["geometry"]["type"] == "Polygon"
    lat, lon = cell["lat"], cell["lon"]

    # ── Stage 2-4: the three predictive models ───────────────────────────────
    water = client.post("/api/water", json={"grid_id": grid_id}).json()
    urban = client.post("/api/urban-expansion", json={"grid_id": grid_id}).json()
    flood = client.post("/api/flood-risk", json={"grid_id": grid_id}).json()

    assert 0.0 <= water["water_body_probability"] <= 1.0
    assert 0.0 <= urban["suitability_score"] <= 1.0
    assert urban["suitability_class"] in {"GREEN", "YELLOW", "RED"}
    assert 0.0 <= flood["flood_probability"] <= 1.0
    assert flood["risk_level"] in {"LOW", "MODERATE", "HIGH"}

    # ── Stage 5: the deterministic building planner ───────────────────────────
    building_payload = {
        "lat": lat, "lon": lon, "building_type": "residential",
        "plot_size_sqm": 300.0, "floors": 2, "occupants": 5,
        "budget_inr": 5_000_000.0, "requirements": ["rainwater", "solar"],
    }
    planner = client.post(
        "/api/building-planner", json=building_payload, params={"interpret": False}
    ).json()
    assert planner["recommendations"]
    assert "advisory" in planner["disclaimer"].lower()
    for rec in planner["recommendations"]:
        assert rec["triggering_data"], "every recommendation must cite what triggered it"

    # ── Stage 6-8: agents, coordinator, full pipeline ────────────────────────
    response = client.post(
        "/api/agents/analyze",
        json={"grid_id": grid_id, "building_params": building_payload},
    )
    assert response.status_code == 200
    pipeline = response.json()

    # Model outputs must pass through the pipeline byte-for-byte.
    assert pipeline["water_result"]["water_body_probability"] == water["water_body_probability"]
    assert pipeline["urban_result"]["suitability_score"] == urban["suitability_score"]
    assert pipeline["flood_result"]["flood_probability"] == flood["flood_probability"]

    # Every agent produced an interpretation.
    for domain in ("water", "urban", "flood", "building"):
        analysis = pipeline[f"{domain}_analysis"]
        assert analysis, f"{domain} agent produced no analysis"
        assert analysis["result"]["summary"], f"{domain} agent produced no summary"
        assert analysis["domain"] == domain

    # The building agent ran, because building parameters were supplied.
    assert pipeline["building_result"]["recommendations"]

    # ── Stage 9: the Coordinator's synthesis ─────────────────────────────────
    coordinator = pipeline["coordinator_result"]
    verdict = coordinator["result"]["overall_recommendation"]
    assert verdict in {
        "proceed", "proceed_with_conditions", "proceed_with_strong_mitigation",
        "discourage", "insufficient_evidence",
    }
    assert coordinator["result"]["headline"]
    assert coordinator["result"]["rationale"]

    # The signals the Coordinator reasoned over must match the models exactly.
    signals = coordinator["signals"]
    assert signals["flood"]["flood_probability"] == flood["flood_probability"]
    assert signals["urban"]["suitability_class"] == urban["suitability_class"]
    assert signals["water"]["is_water_body"] == water["is_water_body"]

    # ── Trade-off reasoning on the conflict case ─────────────────────────────
    if conflict_cell["kind"] == "growth_flood_conflict":
        conflict_types = {c["type"] for c in coordinator["detected_conflicts"]}
        assert "growth_pressure_vs_flood_exposure" in conflict_types, (
            "A GREEN-suitability cell with elevated flood risk must raise the conflict"
        )
        assert verdict != "proceed", (
            "Unrestricted development must not be recommended where growth pressure "
            "coincides with flood exposure"
        )
        assert coordinator["result"]["trade_offs"]

    # Ecological visibility: flood and water evidence must survive into the output.
    assert signals["flood"]["available"]
    assert signals["water"]["available"]

    # ── Stage 10: the response is React-consumable ───────────────────────────
    import json

    serialised = json.dumps(pipeline)          # must be JSON round-trippable
    assert json.loads(serialised) == pipeline
    assert pipeline["errors"] == [], f"pipeline reported errors: {pipeline['errors']}"
    assert len(pipeline["trace"]) >= 7, "the trace must record every stage"


def test_coordinator_endpoint_returns_the_same_verdict(client, conflict_cell, monkeypatch):
    """The coordinator-first view must agree with the full pipeline view."""
    from app.services.building_planner import nasa_power

    monkeypatch.setattr(nasa_power, "get_climatology", lambda lat, lon: dict(CLIMATE))
    grid_id = conflict_cell["grid_id"]

    pipeline = client.post(
        "/api/agents/analyze",
        json={"grid_id": grid_id, "include_attribution": False},
    ).json()
    coordinator = client.post(
        "/api/coordinator",
        json={"grid_id": grid_id, "include_attribution": False},
    ).json()

    assert (
        coordinator["recommendation"]["overall_recommendation"]
        == pipeline["coordinator_result"]["result"]["overall_recommendation"]
    )
    assert (
        coordinator["domains"]["flood"]["model_output"]["flood_probability"]
        == pipeline["flood_result"]["flood_probability"]
    )


def test_map_layers_align_on_the_shared_grid(client, conflict_cell):
    """All three model layers must be indexed by the same grid cells."""
    city = conflict_cell["city"]
    layers = {}
    for name, prefix in (
        ("water", "/api/water"),
        ("urban", "/api/urban-expansion"),
        ("flood", "/api/flood-risk"),
    ):
        body = client.get(f"{prefix}/city/{city}/geojson", params={"limit": 25}).json()
        assert body["crs"]["properties"]["name"] == "EPSG:4326"
        layers[name] = {f["id"] for f in body["features"]}

    assert layers["water"] == layers["urban"] == layers["flood"], (
        "The three layers must cover an identical set of grid cells"
    )


def test_geojson_carries_the_fields_the_map_needs(client, conflict_cell):
    """The urban layer must supply what the GREEN/YELLOW/RED map renders from."""
    body = client.get(
        f"/api/urban-expansion/city/{conflict_cell['city']}/geojson", params={"limit": 5}
    ).json()

    for feature in body["features"]:
        properties = feature["properties"]
        assert properties["suitability_class"] in {"GREEN", "YELLOW", "RED"}
        assert 0.0 <= properties["suitability_score"] <= 1.0
        assert properties["grid_id"]
        assert feature["geometry"]["coordinates"][0][0] == \
               feature["geometry"]["coordinates"][0][-1], "ring must close"
