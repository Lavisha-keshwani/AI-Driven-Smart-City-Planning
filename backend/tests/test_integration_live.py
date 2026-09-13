"""
Live integration tests against the real external services.

These are the only tests that reach the network, and they are OPT-IN: they run when
SMARTCITY_LIVE_TESTS=1, and skip otherwise. The rest of the suite stays offline and
deterministic, so `pytest` never depends on a Groq quota or NASA POWER availability.

Run them with:

    SMARTCITY_LIVE_TESTS=1 pytest tests/test_integration_live.py -v
"""

from __future__ import annotations

import os

import pytest

from app.agents import llm
from app.agents.schemas import AgentResult, CoordinatorResult
from app.core import config
from app.services.building_planner import nasa_power
from tests.conftest import requires_models

live_only = pytest.mark.skipif(
    os.environ.get("SMARTCITY_LIVE_TESTS") != "1",
    reason="Live external-service tests are opt-in; set SMARTCITY_LIVE_TESTS=1 to run.",
)

pytestmark = live_only


@pytest.fixture
def live_llm(monkeypatch):
    """Re-enable the LLM, which conftest disables for every other test."""
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    if not config.GROQ_API_KEY:
        pytest.skip("GROQ_API_KEY is not configured.")


# ── NASA POWER ───────────────────────────────────────────────────────────────

class TestNasaPowerLive:
    def test_climatology_returns_plausible_values(self):
        """Chennai: tropical coastal, monsoon-dominated."""
        nasa_power._fetch_climatology.cache_clear()
        data = nasa_power.get_climatology(13.0827, 80.2707)

        assert 3.0 < data["solar_kwh_m2_day"] < 8.0, "irradiance outside a physical range"
        assert 15.0 < data["temperature_c"] < 40.0
        assert 200.0 < data["rainfall_annual_mm"] < 6000.0
        assert 0.0 <= data["humidity_pct"] <= 100.0
        assert len(data["monthly_rainfall_mm"]) == 12
        assert data["source"] == "NASA POWER"

    def test_daily_series_covers_the_requested_period(self):
        nasa_power._fetch_daily.cache_clear()
        data = nasa_power.get_nasa_power_data(13.0827, 80.2707, "2024-06-01", "2024-06-30")

        assert data["coverage"]["days_requested"] == 30
        assert data["coverage"]["days_available"] > 25
        assert data["summary"]["T2M_mean"] is not None
        assert data["summary"]["PRECTOTCORR_total_mm"] is not None

    def test_monsoon_signal_is_detected_for_a_monsoon_city(self):
        nasa_power._fetch_climatology.cache_clear()
        data = nasa_power.get_climatology(19.0760, 72.8777)  # Mumbai
        assert data["monsoon_concentration"] > 0.6, (
            "Mumbai's rainfall should be strongly monsoon-concentrated"
        )
        assert data["wettest_month"] in ("JUN", "JUL", "AUG", "SEP")

    def test_no_api_key_is_required(self):
        """The chosen NASA POWER endpoints are open; nothing authenticates."""
        nasa_power._fetch_climatology.cache_clear()
        data = nasa_power.get_climatology(28.6139, 77.2090)  # Delhi
        assert data["solar_kwh_m2_day"] > 0


# ── Groq ─────────────────────────────────────────────────────────────────────

class TestGroqLive:
    def test_structured_agent_result(self, live_llm):
        result, meta = llm.structured_call(
            "Model 3 (Random Forest, city-holdout validated) predicts a flood "
            "probability of 0.82 for a grid cell, risk band HIGH. Measured: elevation "
            "6 m, slope 0.3 degrees, surface water present 18% of the time. Interpret "
            "this for the flood domain.",
            AgentResult,
            context="live-test",
        )
        assert result is not None, f"Groq call failed: {meta.get('note')}"
        assert meta["source"] == "llm"
        assert meta["llm_model"] == config.GROQ_MODEL
        assert result.summary
        assert result.interpretation_confidence in {"high", "medium", "low"}
        # The schema must have coerced list fields to plain strings.
        for item in result.findings + result.risks + result.recommendations:
            assert isinstance(item, str)

    def test_structured_coordinator_result(self, live_llm):
        result, meta = llm.structured_call(
            "Domain signals: urban suitability GREEN (score 0.97); flood risk HIGH "
            "(probability 0.67); water: not a water body. Deterministic baseline verdict: "
            "proceed_with_strong_mitigation. Produce the synthesis.",
            CoordinatorResult,
            context="live-test",
        )
        assert result is not None, f"Groq call failed: {meta.get('note')}"
        assert result.overall_recommendation in {
            "proceed", "proceed_with_conditions", "proceed_with_strong_mitigation",
            "discourage", "insufficient_evidence",
        }
        assert result.headline and result.rationale

    def test_llm_does_not_invent_a_number_it_was_not_given(self, live_llm):
        """The guardrails must hold: an absent figure is reported as unavailable."""
        result, meta = llm.structured_call(
            "Model 1 classified a grid cell as a water body. The surface-water "
            "occurrence percentage is UNAVAILABLE for this cell and was not measured. "
            "Interpret what is known, and state clearly what cannot be concluded.",
            AgentResult,
            context="live-test-guardrail",
        )
        assert result is not None, f"Groq call failed: {meta.get('note')}"
        blob = " ".join(
            [result.summary, result.uncertainty, *result.findings, *result.risks]
        ).lower()
        assert any(
            phrase in blob
            for phrase in ("unavailable", "not available", "not measured", "missing",
                           "cannot", "unknown")
        ), "The agent should acknowledge the missing occurrence value"


# ── The whole pipeline, live ─────────────────────────────────────────────────

@requires_models
def test_full_pipeline_with_live_llm(live_llm, grid_cell):
    """The complete workflow with real Groq interpretation.

    Free-tier Groq enforces a tokens-per-minute cap, so an LLM call may legitimately
    be rate-limited. That is treated as a pass for the degradation path — the test
    asserts the pipeline completes and labels its interpretation source either way,
    which is the contract that matters.
    """
    from app.agents.graph import run_pipeline

    result = run_pipeline(grid_id=grid_cell["grid_id"], include_attribution=False)

    assert result["coordinator_result"]["result"]["overall_recommendation"]
    assert result["errors"] == []

    sources = {
        domain: result[f"{domain}_analysis"]["source"]
        for domain in ("water", "urban", "flood")
    }
    sources["coordinator"] = result["coordinator_result"]["source"]

    for stage, source in sources.items():
        assert source in {"llm", "deterministic_fallback"}, stage
        if source == "deterministic_fallback":
            note = (
                result["coordinator_result"].get("note")
                if stage == "coordinator"
                else result[f"{stage}_analysis"].get("note")
            )
            assert note, f"{stage} fell back without recording why"

    assert any(source == "llm" for source in sources.values()), (
        f"No stage reached the LLM at all; sources were {sources}"
    )
