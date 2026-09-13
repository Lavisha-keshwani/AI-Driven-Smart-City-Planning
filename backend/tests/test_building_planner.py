"""
Sustainable Building Planner tests.

The rules engine is deterministic, so it is tested the way deterministic code should
be: with fixed inputs and asserted arithmetic. The NASA POWER client is tested against
a mocked transport, so the suite neither depends on nor hammers the live API — except
for one explicitly marked integration test.
"""

from __future__ import annotations

import httpx
import pytest

from app.core import building_guidelines as bg
from app.core.errors import InvalidInputError, UpstreamServiceError
from app.services.building_planner import nasa_power
from app.services.building_planner.recommendation_engine import generate_recommendations
from tests.conftest import requires_models


# ── Guideline registry ───────────────────────────────────────────────────────

class TestGuidelines:
    def test_every_parameter_declares_provenance(self):
        """A reviewer must be able to trace each number to a source or an assumption."""
        for group_name, group in bg.ALL_GROUPS.items():
            for key, rule in group.items():
                assert rule["origin"] in {"guideline", "project_assumption"}, (
                    f"{group_name}.{key} has no provenance"
                )
                assert rule["source"] in bg.SOURCES, f"{group_name}.{key} cites no source"
                assert rule["note"], f"{group_name}.{key} has no explanation"
                assert rule["unit"], f"{group_name}.{key} has no unit"

    def test_regulatory_claims_are_disclaimed(self):
        export = bg.export()
        assert "not verified" in export["regulatory_status"].lower()
        disclaimer = export["disclaimer"].lower()
        assert "advisory" in disclaimer
        assert "not a certified structural engineering design" in disclaimer
        assert "does not verify compliance" in disclaimer

    def test_eco_niwas_samhita_is_cited_with_its_publisher(self):
        source = bg.SOURCES["eco_niwas_samhita"]
        assert "Bureau of Energy Efficiency" in source["publisher"]
        assert source["scope"]

    def test_citation_includes_origin_and_source(self):
        citation = bg.citation("thermal", "openable_area_share_of_floor")
        assert citation["origin"] == "guideline"
        assert "Eco-Niwas Samhita" in citation["source_title"]
        assert citation["value"] == 0.125


# ── NASA POWER client, against a mocked transport ───────────────────────────

def _climatology_payload(**overrides):
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    parameter = {
        "ALLSKY_SFC_SW_DWN": {**{m: 5.0 for m in months}, "ANN": 5.0},
        "T2M": {**{m: 28.0 for m in months}, "ANN": 28.0},
        "T2M_MAX": {**{m: 35.0 for m in months}, "ANN": 35.0},
        "T2M_MIN": {**{m: 20.0 for m in months}, "ANN": 20.0},
        # 2 mm/day every month -> 2 * 365.25 = 730.5 mm/year
        "PRECTOTCORR": {**{m: 2.0 for m in months}, "ANN": 2.0},
        "RH2M": {**{m: 70.0 for m in months}, "ANN": 70.0},
        "WS2M": {**{m: 3.0 for m in months}, "ANN": 3.0},
    }
    parameter.update(overrides)
    return {"properties": {"parameter": parameter}}


@pytest.fixture(autouse=True)
def clear_nasa_cache():
    nasa_power._fetch_climatology.cache_clear()
    nasa_power._fetch_daily.cache_clear()
    yield
    nasa_power._fetch_climatology.cache_clear()
    nasa_power._fetch_daily.cache_clear()


def _mock_transport(monkeypatch, handler):
    """Route every httpx.Client request through `handler`."""
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            return handler(url, params or {})

    monkeypatch.setattr(nasa_power.httpx, "Client", FakeClient)


class TestNasaPower:
    def test_climatology_parses_and_derives_annual_rainfall(self, monkeypatch):
        _mock_transport(
            monkeypatch,
            lambda url, params: httpx.Response(200, json=_climatology_payload()),
        )
        data = nasa_power.get_climatology(13.08, 80.27)

        assert data["solar_kwh_m2_day"] == 5.0
        assert data["temperature_c"] == 28.0
        assert data["humidity_pct"] == 70.0
        # Weighted by real month lengths, not a flat 30 or 365 factor.
        assert data["rainfall_annual_mm"] == pytest.approx(730.5, abs=0.5)
        assert len(data["monthly_rainfall_mm"]) == 12

    def test_monsoon_concentration_reflects_seasonality(self, monkeypatch):
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        monsoon = {m: (10.0 if m in ("JUN", "JUL", "AUG", "SEP") else 0.0) for m in months}
        _mock_transport(
            monkeypatch,
            lambda url, params: httpx.Response(
                200, json=_climatology_payload(PRECTOTCORR={**monsoon, "ANN": 3.3})
            ),
        )
        data = nasa_power.get_climatology(13.08, 80.27)
        assert data["monsoon_concentration"] == pytest.approx(1.0, abs=0.01)
        assert data["wettest_month"] in ("JUN", "JUL", "AUG", "SEP")

    def test_missing_sentinel_values_are_dropped_not_treated_as_zero(self, monkeypatch):
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        rainfall = {m: (-999.0 if m == "JAN" else 2.0) for m in months}
        _mock_transport(
            monkeypatch,
            lambda url, params: httpx.Response(
                200, json=_climatology_payload(PRECTOTCORR={**rainfall, "ANN": 2.0})
            ),
        )
        data = nasa_power.get_climatology(13.08, 80.27)

        assert "JAN" not in data["monthly_rainfall_mm"]
        assert len(data["monthly_rainfall_mm"]) == 11

    @pytest.mark.parametrize(
        "status,expected",
        [(429, "rate-limiting"), (500, "HTTP 500"), (503, "HTTP 503")],
    )
    def test_http_errors_surface_as_upstream_errors(self, monkeypatch, status, expected):
        _mock_transport(monkeypatch, lambda url, params: httpx.Response(status, text="err"))
        with pytest.raises(UpstreamServiceError) as exc:
            nasa_power.get_climatology(13.08, 80.27)
        assert expected in exc.value.message

    def test_timeout_surfaces_as_an_upstream_error(self, monkeypatch):
        def handler(url, params):
            raise httpx.TimeoutException("timed out")

        _mock_transport(monkeypatch, handler)
        with pytest.raises(UpstreamServiceError) as exc:
            nasa_power.get_climatology(13.08, 80.27)
        assert "did not respond in time" in exc.value.message

    def test_connection_failure_surfaces_as_an_upstream_error(self, monkeypatch):
        def handler(url, params):
            raise httpx.ConnectError("no route to host")

        _mock_transport(monkeypatch, handler)
        with pytest.raises(UpstreamServiceError):
            nasa_power.get_climatology(13.08, 80.27)

    def test_never_substitutes_fallback_climate_values(self, monkeypatch):
        """An outage must raise, not quietly return a regional average."""
        _mock_transport(monkeypatch, lambda url, params: httpx.Response(500))
        with pytest.raises(UpstreamServiceError):
            nasa_power.get_climatology(13.08, 80.27)

    def test_empty_parameter_block_is_rejected(self, monkeypatch):
        _mock_transport(
            monkeypatch,
            lambda url, params: httpx.Response(200, json={"properties": {"parameter": {}}}),
        )
        with pytest.raises(UpstreamServiceError):
            nasa_power.get_climatology(13.08, 80.27)

    @pytest.mark.parametrize("lat,lon", [(95, 0), (0, 200)])
    def test_invalid_coordinates_are_rejected_before_any_request(self, lat, lon):
        with pytest.raises(InvalidInputError):
            nasa_power.get_climatology(lat, lon)

    def test_daily_series_summarises_the_period(self, monkeypatch):
        days = {f"2024060{i}": 1.0 for i in range(1, 6)}
        payload = {"properties": {"parameter": {p: dict(days) for p in nasa_power.PARAMETERS}}}
        _mock_transport(monkeypatch, lambda url, params: httpx.Response(200, json=payload))

        data = nasa_power.get_nasa_power_data(13.08, 80.27, "2024-06-01", "2024-06-05")
        assert data["summary"]["PRECTOTCORR_total_mm"] == pytest.approx(5.0)
        assert data["summary"]["T2M_mean"] == pytest.approx(1.0)
        assert data["coverage"]["days_requested"] == 5
        assert data["coverage"]["complete"] is True

    def test_reversed_date_range_is_rejected(self):
        with pytest.raises(InvalidInputError):
            nasa_power.get_nasa_power_data(13.08, 80.27, "2024-06-10", "2024-06-01")

    def test_future_end_date_is_rejected(self):
        with pytest.raises(InvalidInputError):
            nasa_power.get_nasa_power_data(13.08, 80.27, "2024-06-01", "2099-01-01")

    def test_malformed_date_is_rejected(self):
        with pytest.raises(InvalidInputError):
            nasa_power.get_nasa_power_data(13.08, 80.27, "01-06-2024", "05-06-2024")

    def test_responses_are_cached(self, monkeypatch):
        calls = []

        def handler(url, params):
            calls.append(params)
            return httpx.Response(200, json=_climatology_payload())

        _mock_transport(monkeypatch, handler)
        nasa_power.get_climatology(13.08, 80.27)
        nasa_power.get_climatology(13.09, 80.28)  # snaps to the same cache grid point
        assert len(calls) == 1, "nearby lookups should reuse the cached response"


# ── Recommendation rules ────────────────────────────────────────────────────

def _site(*, rainfall=1200.0, solar=5.2, temperature=29.0, humidity=70.0,
          temp_max=35.0, flood=None, water_body=False, built=0.3,
          occurrence=0.0, urban_class="YELLOW"):
    """A synthetic site assessment with fully specified conditions.

    This is a test double for the *shape* the site analyzer produces, so rule logic can
    be exercised at chosen boundary values. It never stands in for a model prediction
    in production code.
    """
    flood_block = None
    if flood is not None:
        level = "HIGH" if flood >= 0.6 else "MODERATE" if flood >= 0.3 else "LOW"
        flood_block = {
            "flood_probability": flood,
            "risk_level": level,
            "observed": {"elevation_m": 12.0, "slope_deg": 1.0,
                         "depression_index_m": 0.5, "built_fraction_2020": built},
            "risk_drivers": [],
        }
    return {
        "location": {"grid_id": "T_1", "city": "Testville", "state": "TS"},
        "model_predictions": {
            "surface_water": {
                "is_water_body": water_body,
                "water_body_status": {"status": "none", "inter_annual_reliability": "high"},
            },
            "urban_expansion": {
                "suitability_class": urban_class, "suitability_score": 0.5,
                "constraints": [], "score_definition": "d", "classification_rule": "r",
            },
            "flood_risk": flood_block,
        },
        "measured": {
            "climate": {
                "solar_kwh_m2_day": solar, "temperature_c": temperature,
                "temperature_max_c": temp_max, "humidity_pct": humidity,
                "rainfall_annual_mm": rainfall,
            }
        },
        "derived": {
            "water_proximity": {
                "classification": "within_water_body_cell" if water_body else "dry",
                "reason": "test", "occurrence_pct": occurrence, "water_body_status": "none",
            },
            "green_cover": {
                "classification": "moderately_built", "reason": "test",
                "built_fraction": built, "non_built_fraction": 1 - built,
            },
            "solar_potential": {
                "classification": "good", "irradiance_kwh_m2_day": solar, "reason": "t",
            },
            "rainfall_regime": {
                "annual_mm": rainfall, "wettest_month": "JUL",
                "monsoon_concentration": 0.8, "reason": "t",
            },
        },
        "unavailable": {},
        "data_completeness": {},
    }


def _params(**overrides):
    base = {
        "building_type": "residential", "plot_size_sqm": 200.0, "floors": 2,
        "occupants": 4, "budget_inr": None, "roof_area_sqm": None, "requirements": [],
        "lat": 13.0, "lon": 80.0,
    }
    return {**base, **overrides}


class TestRecommendationRules:
    def _by_category(self, output, category):
        return [r for r in output["recommendations"] if r["category"] == category]

    def test_every_recommendation_has_the_required_fields(self):
        output = generate_recommendations(_site(flood=0.5), _params())
        assert output["recommendations"]
        for rec in output["recommendations"]:
            assert rec["recommendation"]
            assert rec["priority"] in {"HIGH", "MEDIUM", "LOW"}
            assert rec["reason"]
            assert rec["triggering_data"]
            assert "calculations" in rec
            assert "guideline_basis" in rec

    def test_recommendations_are_priority_ordered(self):
        output = generate_recommendations(_site(flood=0.7), _params())
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        ranks = [order[r["priority"]] for r in output["recommendations"]]
        assert ranks == sorted(ranks)

    def test_rainwater_yield_matches_the_documented_formula(self):
        """yield_L = roof_area * (rainfall_mm / 1000) * runoff * 1000."""
        output = generate_recommendations(
            _site(rainfall=1000.0), _params(plot_size_sqm=200.0, roof_area_sqm=100.0)
        )
        calc = self._by_category(output, "water")[0]["calculations"]
        runoff = bg.value("rainwater", "roof_runoff_coefficient")
        assert calc["annual_yield_litres"] == pytest.approx(100 * 1.0 * runoff * 1000, rel=1e-3)

    def test_rainwater_skipped_below_the_viability_threshold(self):
        output = generate_recommendations(_site(rainfall=200.0), _params())
        assert not [
            r for r in output["recommendations"]
            if "rainwater" in r["recommendation"].lower()
        ]
        skipped = [s for s in output["skipped_rules"] if "Rainwater" in s["rule"]]
        assert skipped and "below" in skipped[0]["reason"]

    def test_rainwater_skipped_when_rainfall_is_unavailable(self):
        site = _site()
        site["derived"].pop("rainfall_regime")
        output = generate_recommendations(site, _params())
        skipped = [s for s in output["skipped_rules"] if "Rainwater" in s["rule"]]
        assert skipped and "NASA POWER" in skipped[0]["reason"]

    def test_solar_capacity_is_the_lesser_of_roof_and_demand(self):
        output = generate_recommendations(
            _site(solar=5.5), _params(plot_size_sqm=2000.0, occupants=2)
        )
        calc = self._by_category(output, "energy")[0]["calculations"]
        assert calc["recommended_capacity_kw"] == min(
            calc["roof_limited_capacity_kw"], calc["demand_matched_capacity_kw"]
        )
        assert calc["limiting_factor"] == "estimated demand"

    def test_solar_generation_matches_the_documented_formula(self):
        output = generate_recommendations(_site(solar=5.0), _params())
        calc = self._by_category(output, "energy")[0]["calculations"]
        expected = calc["recommended_capacity_kw"] * 5.0 * calc["performance_ratio"]
        assert calc["estimated_daily_generation_kwh"] == pytest.approx(expected, rel=1e-2)

    def test_solar_skipped_below_viable_irradiance(self):
        output = generate_recommendations(_site(solar=2.0), _params())
        assert not self._by_category(output, "energy")
        assert any("solar" in s["rule"].lower() for s in output["skipped_rules"])

    def test_flood_resilience_fires_only_above_low_risk(self):
        high = generate_recommendations(_site(flood=0.8), _params())
        assert self._by_category(high, "flood_resilience")

        low = generate_recommendations(_site(flood=0.1), _params())
        assert not self._by_category(low, "flood_resilience")
        skipped = [s for s in low["skipped_rules"] if "Flood" in s["rule"]]
        assert skipped and "rather than proof of safety" in skipped[0]["reason"]

    def test_plinth_height_scales_with_the_risk_band(self):
        moderate = generate_recommendations(_site(flood=0.45), _params())
        high = generate_recommendations(_site(flood=0.85), _params())

        moderate_h = self._by_category(moderate, "flood_resilience")[0]
        high_h = self._by_category(high, "flood_resilience")[0]
        assert (
            high_h["calculations"]["recommended_plinth_raise_m"]
            > moderate_h["calculations"]["recommended_plinth_raise_m"]
        )
        assert high_h["priority"] == "HIGH"

    def test_missing_flood_model_does_not_imply_safety(self):
        output = generate_recommendations(_site(flood=None), _params())
        skipped = [s for s in output["skipped_rules"] if "Flood" in s["rule"]]
        assert skipped
        assert "not a finding that the site is safe" in skipped[0]["reason"]

    def test_permeable_share_rises_with_flood_risk(self):
        low = generate_recommendations(_site(flood=0.1), _params())
        high = generate_recommendations(_site(flood=0.8), _params())

        low_share = self._by_category(low, "green_cover")[0][
            "calculations"]["permeable_share_of_open_area"]
        high_share = self._by_category(high, "green_cover")[0][
            "calculations"]["permeable_share_of_open_area"]
        assert high_share > low_share

    def test_water_conservation_arithmetic(self):
        output = generate_recommendations(_site(), _params(occupants=4))
        calc = [
            r for r in self._by_category(output, "water")
            if "low-flow" in r["recommendation"].lower()
        ][0]["calculations"]

        lpcd = bg.value("water", "domestic_demand_lpcd")
        assert calc["baseline_demand_litres_per_day"] == 4 * lpcd
        assert calc["residual_demand_litres_per_day"] == pytest.approx(
            calc["baseline_demand_litres_per_day"]
            - calc["fixture_saving_litres_per_day"]
            - calc["greywater_reuse_litres_per_day"],
            abs=1,
        )

    def test_office_uses_the_office_demand_benchmark(self):
        output = generate_recommendations(
            _site(), _params(building_type="office", occupants=50)
        )
        calc = [
            r for r in self._by_category(output, "water")
            if "low-flow" in r["recommendation"].lower()
        ][0]["calculations"]
        assert calc["demand_lpcd"] == bg.value("water", "office_demand_lpcd")

    def test_water_body_setback_fires_only_near_water(self):
        near = generate_recommendations(_site(water_body=True, occurrence=40.0), _params())
        assert [
            r for r in near["recommendations"] if "setback" in r["recommendation"].lower()
        ]
        dry = generate_recommendations(_site(water_body=False), _params())
        assert not [
            r for r in dry["recommendations"] if "setback" in r["recommendation"].lower()
        ]

    def test_passive_cooling_adapts_to_humidity(self):
        humid = generate_recommendations(_site(humidity=80.0), _params())
        dry = generate_recommendations(_site(humidity=35.0), _params())

        humid_text = self._by_category(humid, "thermal_comfort")[0]["recommendation"].lower()
        dry_text = self._by_category(dry, "thermal_comfort")[0]["recommendation"].lower()
        assert "cross-ventilation" in humid_text
        assert "evaporative" in dry_text

    def test_passive_cooling_skipped_in_a_cool_climate(self):
        output = generate_recommendations(
            _site(temperature=18.0, temp_max=24.0), _params()
        )
        assert not self._by_category(output, "thermal_comfort")

    def test_red_suitability_produces_a_high_priority_caution(self):
        output = generate_recommendations(_site(urban_class="RED"), _params())
        planning = self._by_category(output, "site_planning")
        assert any(r["priority"] == "HIGH" for r in planning)

    def test_output_carries_the_disclaimer_and_the_applied_ruleset(self):
        output = generate_recommendations(_site(), _params())
        assert "advisory" in output["disclaimer"].lower()
        assert output["guidelines_applied"]["sources"]
        assert output["priority_counts"]


# ── Site analyzer, against the real models ──────────────────────────────────

@requires_models
class TestSiteAnalyzer:
    def test_site_separates_predictions_measurements_and_derivations(
        self, grid_cell, monkeypatch
    ):
        monkeypatch.setattr(
            nasa_power, "get_climatology",
            lambda lat, lon: {
                "solar_kwh_m2_day": 5.0, "temperature_c": 28.0, "temperature_max_c": 35.0,
                "humidity_pct": 70.0, "rainfall_annual_mm": 900.0, "wettest_month": "JUL",
                "monsoon_concentration": 0.7,
            },
        )
        from app.services.building_planner.site_analyzer import analyze_site

        site = analyze_site(grid_cell["lat"], grid_cell["lon"])

        assert set(site["model_predictions"]) == {
            "surface_water", "urban_expansion", "flood_risk"
        }
        assert site["measured"]["climate"]["solar_kwh_m2_day"] == 5.0
        assert site["derived"]["water_proximity"]["classification"]
        assert site["location"]["grid_id"] == grid_cell["grid_id"]
        assert all(site["data_completeness"].values())

    def test_nasa_outage_is_recorded_not_hidden(self, grid_cell, monkeypatch):
        def boom(lat, lon):
            raise UpstreamServiceError("NASA POWER unavailable", detail={})

        monkeypatch.setattr(nasa_power, "get_climatology", boom)
        from app.services.building_planner.site_analyzer import analyze_site

        site = analyze_site(grid_cell["lat"], grid_cell["lon"])

        assert site["data_completeness"]["nasa_power"] is False
        assert "nasa_power" in site["unavailable"]
        assert "solar_potential" not in site["derived"]
        # The model evidence must still be present.
        assert site["model_predictions"]["flood_risk"]
