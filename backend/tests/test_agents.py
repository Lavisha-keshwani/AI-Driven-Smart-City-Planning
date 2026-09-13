"""
Agent layer tests.

The important assertions here are about role boundaries rather than prose quality:

  * an agent's evidence must carry the model's numbers unchanged
  * the deterministic conflict detector must find each specified trade-off case
  * the Coordinator's baseline verdict must be reproducible
  * the LLM must not be able to loosen a conclusion the rules reached
  * an unavailable model must degrade into a stated gap, never a substituted value

No test needs Groq: `conftest.no_llm` disables it, and `stub_llm` injects canned
structured responses where LLM handling itself is under test.
"""

from __future__ import annotations

import pytest

from app.agents import coordinator_agent, flood_agent, graph, urban_agent, water_agent
from app.agents.schemas import AgentResult, CoordinatorResult
from app.agents.state import initial_state
from app.core.errors import InvalidInputError, ModelUnavailableError
from app.services.models import registry
from tests.conftest import requires_models


# ── Conflict detection: the specification's trade-off cases ──────────────────

def _signals(*, urban=None, flood=None, water_body=False, reliability="high",
            water_available=True, urban_available=True, flood_available=True):
    return {
        "water": {
            "available": water_available,
            "is_water_body": water_body,
            "water_body_probability": 0.9 if water_body else 0.1,
            "status": "permanent" if water_body else "none",
            "inter_annual_reliability": reliability,
        },
        "urban": {
            "available": urban_available,
            "suitability_class": urban,
            "suitability_score": {"GREEN": 0.9, "YELLOW": 0.5, "RED": 0.1}.get(urban),
            "confidence": 0.8,
            "constraints": [],
        },
        "flood": {
            "available": flood_available,
            "flood_probability": {"HIGH": 0.8, "MODERATE": 0.45, "LOW": 0.1}.get(flood),
            "risk_level": flood,
            "drivers": [],
        },
        "building": {"available": False, "recommendation_count": 0,
                     "high_priority_count": None},
    }


class TestConflictDetection:
    def test_case_a_high_suitability_with_high_flood_risk(self):
        """Spec Case A: GREEN + HIGH flood must discourage unrestricted expansion."""
        signals = _signals(urban="GREEN", flood="HIGH")
        conflicts = coordinator_agent.detect_conflicts(signals)

        match = [c for c in conflicts if c["type"] == "growth_pressure_vs_flood_exposure"]
        assert match, "The GREEN + HIGH flood conflict must be detected"
        assert match[0]["severity"] == "high"
        assert set(match[0]["between"]) == {"urban", "flood"}

        verdict, reasons = coordinator_agent._baseline_recommendation(signals, conflicts)
        assert verdict == "proceed_with_strong_mitigation"
        assert any("HIGH" in r for r in reasons)

    def test_case_b_high_suitability_low_flood_good_water(self):
        """Spec Case B: the favourable case."""
        signals = _signals(urban="GREEN", flood="LOW", reliability="high")
        conflicts = coordinator_agent.detect_conflicts(signals)
        verdict, _ = coordinator_agent._baseline_recommendation(signals, conflicts)
        assert verdict == "proceed"

    def test_case_c_medium_suitability_high_flood(self):
        """Spec Case C: conditional suitability plus high hazard."""
        signals = _signals(urban="YELLOW", flood="HIGH")
        conflicts = coordinator_agent.detect_conflicts(signals)
        assert any(c["type"] == "growth_pressure_vs_flood_exposure" for c in conflicts)
        verdict, _ = coordinator_agent._baseline_recommendation(signals, conflicts)
        assert verdict == "discourage"

    @pytest.mark.parametrize("flood", ["LOW", "MODERATE", "HIGH"])
    def test_case_d_low_suitability_discourages_regardless(self, flood):
        """Spec Case D: RED discourages expansion whatever else is favourable."""
        signals = _signals(urban="RED", flood=flood)
        conflicts = coordinator_agent.detect_conflicts(signals)
        verdict, _ = coordinator_agent._baseline_recommendation(signals, conflicts)
        assert verdict == "discourage"

    def test_water_body_is_an_ecological_hard_stop(self):
        """A favourable growth score must never approve building on surface water."""
        signals = _signals(urban="GREEN", flood="LOW", water_body=True)
        conflicts = coordinator_agent.detect_conflicts(signals)
        verdict, reasons = coordinator_agent._baseline_recommendation(signals, conflicts)

        assert verdict == "discourage"
        assert any("surface-water body" in r for r in reasons)
        assert any(c["type"] == "growth_pressure_vs_water_body" for c in conflicts)

    def test_unreliable_water_supply_is_flagged(self):
        signals = _signals(urban="GREEN", flood="LOW", reliability="low")
        conflicts = coordinator_agent.detect_conflicts(signals)
        assert any(c["type"] == "growth_pressure_vs_water_availability" for c in conflicts)

    def test_insufficient_evidence_when_models_are_missing(self):
        signals = _signals(urban="GREEN", flood=None, flood_available=False,
                           water_available=False)
        verdict, reasons = coordinator_agent._baseline_recommendation(signals, [])
        assert verdict == "insufficient_evidence"
        assert "not enough" in " ".join(reasons)

    def test_moderate_flood_requires_conditions(self):
        signals = _signals(urban="GREEN", flood="MODERATE")
        conflicts = coordinator_agent.detect_conflicts(signals)
        verdict, _ = coordinator_agent._baseline_recommendation(signals, conflicts)
        assert verdict == "proceed_with_conditions"


# ── The safety guard on LLM synthesis ───────────────────────────────────────

class TestCoordinatorSafetyGuard:
    def _state_with(self, urban_class, flood_level, water_body=False):
        return {
            "location": {"grid_id": "X_1", "city": "Testville", "state": "TS"},
            "water_result": {
                "is_water_body": water_body, "water_body_probability": 0.2,
                "water_body_status": {"status": "none", "inter_annual_reliability": "high"},
            },
            "urban_result": {
                "suitability_class": urban_class, "suitability_score": 0.9,
                "confidence": 0.8, "constraints": [],
            },
            "flood_result": {
                "flood_probability": 0.8 if flood_level == "HIGH" else 0.1,
                "risk_level": flood_level, "risk_drivers": [],
            },
            "errors": [],
        }

    def test_llm_cannot_loosen_the_deterministic_verdict(self, stub_llm):
        """An LLM answering 'proceed' against a 'discourage' baseline must be overruled."""
        stub_llm(CoordinatorResult(
            overall_recommendation="proceed",
            headline="Looks fine to me.",
            rationale="Unjustifiably permissive synthesis.",
        ))
        output = coordinator_agent.run(self._state_with("RED", "HIGH"))
        report = output["coordinator_result"]

        assert report["result"]["overall_recommendation"] == "discourage"
        assert "more permissive" in report["note"]

    def test_llm_may_tighten_the_verdict(self, stub_llm):
        """Extra caution is allowed; the LLM's stricter verdict survives."""
        stub_llm(CoordinatorResult(
            overall_recommendation="discourage",
            headline="Too risky.",
            rationale="Additional caution warranted.",
        ))
        output = coordinator_agent.run(self._state_with("GREEN", "LOW"))
        report = output["coordinator_result"]

        assert report["result"]["overall_recommendation"] == "discourage"
        assert report["note"] is None

    def test_detected_conflicts_are_always_represented(self, stub_llm):
        """A conflict the rules found cannot be dropped by the LLM omitting it."""
        stub_llm(CoordinatorResult(
            overall_recommendation="discourage",
            headline="No.",
            rationale="The LLM listed no trade-offs at all.",
            trade_offs=[],
        ))
        output = coordinator_agent.run(self._state_with("GREEN", "HIGH"))
        report = output["coordinator_result"]

        assert report["detected_conflicts"]
        assert len(report["result"]["trade_offs"]) == len(report["detected_conflicts"])

    def test_deterministic_fallback_when_llm_is_unavailable(self):
        """With the LLM off, a full synthesis is still produced, and labelled as such."""
        output = coordinator_agent.run(self._state_with("GREEN", "HIGH"))
        report = output["coordinator_result"]

        assert report["source"] == "deterministic_fallback"
        assert report["result"]["overall_recommendation"] == "proceed_with_strong_mitigation"
        assert report["result"]["rationale"]
        assert report["result"]["trade_offs"]


# ── Domain agents ───────────────────────────────────────────────────────────

@requires_models
class TestDomainAgents:
    @pytest.mark.parametrize(
        "agent,result_key",
        [(water_agent, "water_result"), (urban_agent, "urban_result"),
         (flood_agent, "flood_result")],
        ids=["water", "urban", "flood"],
    )
    def test_agent_records_model_output_and_an_analysis(self, agent, result_key, grid_cell):
        state = initial_state(grid_cell)
        output = agent.run(state)

        assert output[result_key], "the model output must be recorded"
        analysis = output[f"{agent.DOMAIN}_analysis"]
        assert analysis["domain"] == agent.DOMAIN
        assert analysis["result"]["summary"]
        assert analysis["source"] == "deterministic_fallback"  # LLM is off in tests

    def test_evidence_carries_the_model_numbers_unchanged(self, grid_cell):
        """The agent must not transform the probability it was given."""
        state = initial_state(grid_cell)
        output = flood_agent.run(state)

        model_probability = output["flood_result"]["flood_probability"]
        evidence = output["flood_analysis"]["evidence"]
        assert evidence["model_prediction"]["flood_probability"] == model_probability

    def test_agent_result_schema_has_no_field_for_a_prediction(self):
        """Structurally, an agent cannot return a competing numeric prediction."""
        fields = set(AgentResult.model_fields)
        for forbidden in ("flood_probability", "suitability_score", "probability", "score"):
            assert forbidden not in fields

    def test_unavailable_model_becomes_a_stated_gap(self, monkeypatch, grid_cell):
        """A missing model must yield no result and an explicit gap, not a value."""
        from app.services.models import flood_risk

        def boom(*args, **kwargs):
            raise ModelUnavailableError("Model 3 artifact missing.",
                                        detail={"config_key": "FLOOD_MODEL_PATH"})

        monkeypatch.setattr(flood_risk, "predict", boom)
        output = flood_agent.run(initial_state(grid_cell))

        assert output["flood_result"] == {}
        assert output["errors"][0]["error"] == "model_unavailable"
        analysis = output["flood_analysis"]
        assert analysis["result"]["findings"] == []
        assert "No substitute value" in analysis["result"]["summary"]


# ── Graph structure and execution ───────────────────────────────────────────

class TestGraph:
    def test_topology_declares_the_parallel_domain_group(self):
        topology = graph.graph_topology()
        parallel = [
            n for n in topology["nodes"] if n.get("parallel_group") == "domain"
        ]
        assert {n["name"] for n in parallel} == {
            "water_agent", "urban_agent", "flood_agent"
        }
        assert "concurrently" in topology["parallelism"]

    def test_topology_states_the_architectural_principle(self):
        principle = graph.graph_topology()["principle"].lower()
        assert "interpret" in principle
        assert "do not replace" in principle

    def test_building_agent_is_gated_on_building_params(self):
        from app.agents import building_agent

        assert building_agent.should_run({"building_params": {"plot_size_sqm": 100}})
        assert not building_agent.should_run({"building_params": None})
        assert not building_agent.should_run({})

    def test_pipeline_requires_a_location(self):
        with pytest.raises(InvalidInputError):
            graph.run_pipeline()

    @requires_models
    def test_pipeline_runs_all_stages(self, grid_cell):
        result = graph.run_pipeline(grid_id=grid_cell["grid_id"])

        assert result["location"]["grid_id"] == grid_cell["grid_id"]
        for key in ("water_result", "urban_result", "flood_result"):
            assert result[key], f"{key} must be populated"
        for key in ("water_analysis", "urban_analysis", "flood_analysis"):
            assert result[key]["result"]["summary"]
        assert result["coordinator_result"]["result"]["overall_recommendation"]
        assert result["errors"] == []
        # The trace must record every stage, proving the graph ran in full.
        assert len(result["trace"]) >= 6

    @requires_models
    def test_pipeline_resolves_coordinates_to_a_cell(self, grid_cell):
        result = graph.run_pipeline(lat=grid_cell["lat"], lon=grid_cell["lon"])
        assert result["location"]["grid_id"] == grid_cell["grid_id"]
        assert result["location"]["resolved_from"] == "coordinates"
        assert "distance_km" in result["location"]

    @requires_models
    def test_pipeline_skips_building_agent_without_params(self, grid_cell):
        result = graph.run_pipeline(grid_id=grid_cell["grid_id"])
        assert not result.get("building_analysis")

    @requires_models
    def test_domain_agents_run_concurrently(self, grid_cell, monkeypatch):
        """Prove the fan-out is real: total wall time must beat the serial sum."""
        import threading
        import time

        observed: list[tuple[str, float, float, str]] = []
        delay = 0.6

        def instrument(module, name):
            original = module.run

            def wrapped(state):
                start = time.perf_counter()
                time.sleep(delay)
                result = original(state)
                observed.append(
                    (name, start, time.perf_counter(), threading.current_thread().name)
                )
                return result

            monkeypatch.setattr(module, "run", wrapped)

        for module, name in (
            (water_agent, "water"), (urban_agent, "urban"), (flood_agent, "flood")
        ):
            instrument(module, name)

        graph.get_graph.cache_clear()
        try:
            started = time.perf_counter()
            graph.run_pipeline(grid_id=grid_cell["grid_id"])
            elapsed = time.perf_counter() - started
        finally:
            graph.get_graph.cache_clear()

        assert len(observed) == 3
        serial_total = sum(end - start for _, start, end, _ in observed)
        assert elapsed < serial_total, (
            f"Pipeline took {elapsed:.2f}s against {serial_total:.2f}s of agent work, "
            f"so the domain agents did not overlap."
        )
        latest_start = max(start for _, start, _, _ in observed)
        earliest_end = min(end for _, _, end, _ in observed)
        assert latest_start < earliest_end, "agent execution windows did not overlap"
        assert len({thread for *_, thread in observed}) > 1, "all agents ran on one thread"


# ── Guardrails in the prompt layer ──────────────────────────────────────────

def test_guardrails_forbid_inventing_and_overriding_predictions():
    from app.agents.llm import GUARDRAILS

    text = GUARDRAILS.lower()
    assert "never" in text
    assert "invent" in text
    assert "override" in text
    assert "measured data" in text
    assert "model predictions" in text
    assert "uncertainty" in text


def test_llm_status_never_exposes_the_key(monkeypatch):
    from app.agents import llm
    from app.core import config

    monkeypatch.setattr(config, "GROQ_API_KEY", "secret-key-value")
    status = llm.llm_status()

    assert status["api_key_configured"] is True
    assert "secret-key-value" not in str(status)


def test_structured_call_degrades_when_the_llm_is_disabled():
    from app.agents import llm

    result, meta = llm.structured_call("prompt", AgentResult, context="test")
    assert result is None
    assert meta["source"] == "deterministic_fallback"
    assert meta["note"]


def test_structured_call_reports_a_missing_key(monkeypatch):
    from app.agents import llm
    from app.core import config

    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    result, meta = llm.structured_call("prompt", AgentResult, context="test")

    assert result is None
    assert "GROQ_API_KEY" in meta["note"]
