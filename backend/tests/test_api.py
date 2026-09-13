"""
HTTP API tests.

Every endpoint the specification lists is exercised here, together with the failure
paths: invalid coordinates, unknown grid cells, bad uploads, and unavailable
dependencies. The LLM is disabled by the autouse fixture, so these tests run offline.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from tests.conftest import requires_hmpd, requires_models


# ── System ───────────────────────────────────────────────────────────────────

class TestSystem:
    def test_root_indexes_the_api(self, client):
        body = client.get("/").json()
        assert body["service"] == "SmartCityAI API"
        assert "do not replace" in body["principle"]
        for group in ("water", "urban_expansion", "flood_risk", "microplastics",
                      "building_planner", "agents"):
            assert group in body["endpoints"]

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"healthy", "degraded"}
        assert "/" in body["models_loaded"]
        assert body["llm"]["provider"] == "groq"
        assert "api_key" not in str(body["llm"]).lower().replace("api_key_configured", "")

    def test_models_status_reports_each_model(self, client):
        body = client.get("/api/models/status").json()
        assert set(body["models"]) == {
            "model1_surface_water", "model2_urban_expansion",
            "model3_flood_risk", "model4_microplastic",
        }
        for entry in body["models"].values():
            assert "loaded" in entry and "artifact_present" in entry
        assert "shap_available" in body["explainability"]

    def test_request_id_is_returned(self, client):
        response = client.get("/health", headers={"X-Request-ID": "test-trace-1"})
        assert response.headers["X-Request-ID"] == "test-trace-1"

    def test_unknown_route_404s(self, client):
        assert client.get("/api/does-not-exist").status_code == 404


# ── Grid discovery ───────────────────────────────────────────────────────────

@requires_models
class TestGridEndpoints:
    def test_list_cities(self, client):
        body = client.get("/api/grid/cities").json()
        assert body["count"] == len(body["cities"])
        assert body["count"] > 0
        assert {"city", "state", "grid_cells", "lat", "lon"} <= set(body["cities"][0])

    def test_list_city_cells(self, client, sample_city):
        body = client.get(f"/api/grid/cities/{sample_city}/cells").json()
        assert body["count"] == len(body["grid_ids"]) > 0

    def test_unknown_city_returns_404_with_the_valid_list(self, client):
        response = client.get("/api/grid/cities/Atlantis/cells")
        assert response.status_code == 404
        body = response.json()
        assert body["error"] == "grid_not_found"
        assert body["detail"]["available_cities"]

    def test_get_cell_includes_geometry(self, client, grid_cell):
        body = client.get(f"/api/grid/cell/{grid_cell['grid_id']}").json()
        assert body["geometry"]["type"] == "Polygon"
        assert body["crs"] == "EPSG:4326"

    def test_nearest(self, client, grid_cell):
        body = client.get(
            "/api/grid/nearest", params={"lat": grid_cell["lat"], "lon": grid_cell["lon"]}
        ).json()
        assert body["grid_id"] == grid_cell["grid_id"]

    def test_nearest_outside_coverage_returns_404(self, client):
        response = client.get("/api/grid/nearest", params={"lat": 0, "lon": -160})
        assert response.status_code == 404
        assert response.json()["error"] == "grid_not_found"

    @pytest.mark.parametrize("lat,lon", [(95, 0), (0, 200)])
    def test_nearest_rejects_out_of_range_coordinates(self, client, lat, lon):
        response = client.get("/api/grid/nearest", params={"lat": lat, "lon": lon})
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_input"

    def test_city_geojson(self, client, sample_city):
        body = client.get(
            f"/api/grid/cities/{sample_city}/geojson", params={"limit": 3}
        ).json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) == 3


# ── Model endpoints ──────────────────────────────────────────────────────────

@requires_models
class TestModelEndpoints:
    @pytest.mark.parametrize(
        "path,probability_field",
        [("/api/water", "water_body_probability"),
         ("/api/flood-risk", "flood_probability")],
    )
    def test_post_by_grid_id(self, client, grid_cell, path, probability_field):
        response = client.post(path, json={"grid_id": grid_cell["grid_id"]})
        assert response.status_code == 200
        body = response.json()
        assert body["grid_id"] == grid_cell["grid_id"]
        assert 0.0 <= body[probability_field] <= 1.0

    def test_post_urban_expansion(self, client, grid_cell):
        body = client.post(
            "/api/urban-expansion", json={"grid_id": grid_cell["grid_id"]}
        ).json()
        assert 0.0 <= body["suitability_score"] <= 1.0
        assert body["suitability_class"] in {"GREEN", "YELLOW", "RED"}

    @pytest.mark.parametrize(
        "path", ["/api/water", "/api/urban-expansion", "/api/flood-risk"]
    )
    def test_post_by_coordinates(self, client, grid_cell, path):
        body = client.post(
            path, json={"lat": grid_cell["lat"], "lon": grid_cell["lon"]}
        ).json()
        assert body["grid_id"] == grid_cell["grid_id"]

    @pytest.mark.parametrize(
        "path", ["/api/water", "/api/urban-expansion", "/api/flood-risk"]
    )
    def test_missing_location_is_rejected(self, client, path):
        response = client.post(path, json={})
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_input"

    @pytest.mark.parametrize(
        "path", ["/api/water", "/api/urban-expansion", "/api/flood-risk"]
    )
    def test_unknown_grid_id_returns_404(self, client, path):
        response = client.post(path, json={"grid_id": "Atlantis_00000000"})
        assert response.status_code == 404
        assert response.json()["error"] == "grid_not_found"

    @pytest.mark.parametrize(
        "prefix", ["/api/water", "/api/urban-expansion", "/api/flood-risk"]
    )
    def test_city_layer_and_geojson(self, client, sample_city, prefix):
        layer = client.get(f"{prefix}/city/{sample_city}", params={"limit": 5}).json()
        assert layer["count"] == 5

        geojson = client.get(
            f"{prefix}/city/{sample_city}/geojson", params={"limit": 5}
        ).json()
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 5
        assert geojson["features"][0]["geometry"]["type"] == "Polygon"

    @pytest.mark.parametrize(
        "prefix", ["/api/water", "/api/urban-expansion", "/api/flood-risk"]
    )
    def test_metrics_endpoints(self, client, prefix):
        body = client.get(f"{prefix}/metrics").json()
        assert body["model"]
        assert body["limitations"]

    def test_urban_thresholds_are_documented(self, client):
        body = client.get("/api/urban-expansion/thresholds").json()
        assert body["score_definition"]
        assert body["configurable_via"]
        assert set(body["class_meaning"]) == {"GREEN", "YELLOW", "RED"}

    def test_flood_thresholds_are_documented(self, client):
        body = client.get("/api/flood-risk/thresholds").json()
        assert body["risk_bands"]["high_at_or_above"] > body["risk_bands"]["moderate_at_or_above"]
        assert body["rationale"]
        assert body["threshold_basis"]

    def test_water_monitoring(self, client, sample_city):
        body = client.get(f"/api/water/monitoring/{sample_city}").json()
        assert body["city"] == sample_city
        assert "measured" in body["basis"].lower()

    def test_geojson_limit_is_bounded(self, client, sample_city):
        response = client.get(
            f"/api/water/city/{sample_city}/geojson", params={"limit": 99999}
        )
        assert response.status_code == 422


# ── Microplastics ────────────────────────────────────────────────────────────

@requires_hmpd
class TestMicroplasticsEndpoint:
    def _files(self, image_dir, particle_id):
        return {
            f"{channel.lower()}_image": (
                f"{particle_id}_{channel}.bmp",
                (image_dir / f"{particle_id}_{channel}.bmp").read_bytes(),
                "image/bmp",
            )
            for channel in ("R", "A", "P")
        }

    def test_analyze_positive_and_negative(self, client, hmpd_particles, hmpd_image_dir):
        for expected, particles in (
            ("microplastic_candidate", hmpd_particles["positive"]),
            ("no_microplastic_detected", hmpd_particles["negative"]),
        ):
            response = client.post(
                "/api/microplastics/analyze",
                files=self._files(hmpd_image_dir, particles[0]),
            )
            assert response.status_code == 200
            body = response.json()
            assert body["classification"] == expected
            assert body["disclaimer"]
            assert body["input"]["mode"] == "polarimetric_triplet"

    def test_generic_content_type_is_accepted(self, client, hmpd_particles, hmpd_image_dir):
        """curl sends .bmp as application/octet-stream; that must not be refused."""
        particle = hmpd_particles["positive"][0]
        files = {
            f"{channel.lower()}_image": (
                f"{particle}_{channel}.bmp",
                (hmpd_image_dir / f"{particle}_{channel}.bmp").read_bytes(),
                "application/octet-stream",
            )
            for channel in ("R", "A", "P")
        }
        assert client.post("/api/microplastics/analyze", files=files).status_code == 200

    def test_missing_channel_is_rejected(self, client, hmpd_particles, hmpd_image_dir):
        files = self._files(hmpd_image_dir, hmpd_particles["positive"][0])
        files.pop("p_image")
        response = client.post("/api/microplastics/analyze", files=files)
        assert response.status_code == 422

    def test_text_upload_is_rejected(self, client):
        files = {
            f"{c}_image": (f"{c}.txt", b"not an image", "text/plain") for c in "rap"
        }
        response = client.post("/api/microplastics/analyze", files=files)
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_input"

    def test_grayscale_composite_is_rejected_with_guidance(self, client):
        buffer = io.BytesIO()
        Image.new("L", (64, 64)).save(buffer, "PNG")
        response = client.post(
            "/api/microplastics/analyze-composite",
            files={"image": ("grey.png", buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 400
        body = response.json()
        assert "chance" in body["message"].lower()
        assert "remedy" in body["detail"]

    def test_rgb_composite_is_accepted_with_a_channel_order_warning(self, client):
        buffer = io.BytesIO()
        Image.new("RGB", (96, 96), (120, 90, 60)).save(buffer, "PNG")
        response = client.post(
            "/api/microplastics/analyze-composite",
            files={"image": ("stack.png", buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["input"]["mode"] == "composite_3_channel"
        assert any("channel order" in w.lower() for w in body["warnings"])

    def test_undecodable_image_is_rejected(self, client):
        response = client.post(
            "/api/microplastics/analyze-composite",
            files={"image": ("x.png", b"\x89PNG\r\n\x1a\nbroken", "image/png")},
        )
        assert response.status_code == 400

    def test_oversize_upload_is_rejected(self, client, monkeypatch):
        from app.core import config

        monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024)
        response = client.post(
            "/api/microplastics/analyze-composite",
            files={"image": ("big.png", b"x" * 5000, "image/png")},
        )
        assert response.status_code == 400
        assert "limit" in response.json()["message"].lower()

    def test_metrics_carry_the_disclaimer(self, client):
        body = client.get("/api/microplastics/metrics").json()
        assert "screening only" in body["disclaimer"].lower()
        assert body["cross_validation"]["mean_accuracy"]


# ── Building planner ─────────────────────────────────────────────────────────

@requires_models
class TestBuildingPlannerEndpoint:
    def _payload(self, grid_cell, **overrides):
        return {
            "lat": grid_cell["lat"], "lon": grid_cell["lon"],
            "building_type": "residential", "plot_size_sqm": 250,
            "floors": 2, "occupants": 4, **overrides,
        }

    def test_plan(self, client, grid_cell, monkeypatch):
        from app.services.building_planner import nasa_power

        monkeypatch.setattr(
            nasa_power, "get_climatology",
            lambda lat, lon: {
                "solar_kwh_m2_day": 5.2, "temperature_c": 29.0, "temperature_max_c": 36.0,
                "humidity_pct": 72.0, "rainfall_annual_mm": 1100.0,
                "wettest_month": "JUL", "monsoon_concentration": 0.75,
            },
        )
        response = client.post(
            "/api/building-planner", json=self._payload(grid_cell), params={"interpret": False}
        )
        assert response.status_code == 200
        body = response.json()

        assert body["recommendations"]
        assert body["priority_counts"]
        assert "advisory" in body["disclaimer"].lower()
        assert body["guidelines_applied"]["sources"]
        for rec in body["recommendations"]:
            assert {"recommendation", "priority", "reason", "triggering_data"} <= set(rec)

    @pytest.mark.parametrize(
        "overrides",
        [{"plot_size_sqm": -5}, {"floors": 0}, {"occupants": 0},
         {"building_type": "castle"}, {"plot_size_sqm": 100, "roof_area_sqm": 200}],
        ids=["negative_plot", "zero_floors", "zero_occupants", "bad_type", "roof_over_plot"],
    )
    def test_invalid_inputs_are_rejected(self, client, grid_cell, overrides):
        response = client.post(
            "/api/building-planner", json=self._payload(grid_cell, **overrides)
        )
        assert response.status_code == 422

    def test_site_endpoint(self, client, grid_cell):
        body = client.get(
            "/api/building-planner/site",
            params={"lat": grid_cell["lat"], "lon": grid_cell["lon"]},
        ).json()
        assert body["location"]["grid_id"] == grid_cell["grid_id"]
        assert "model_predictions" in body and "derived" in body

    def test_guidelines_endpoint_declares_regulatory_status(self, client):
        body = client.get("/api/building-planner/guidelines").json()
        assert "eco_niwas_samhita" in body["sources"]
        assert "not verified" in body["regulatory_status"].lower()

    def test_location_outside_coverage_returns_404(self, client):
        response = client.post(
            "/api/building-planner",
            json={"lat": 0.0, "lon": -160.0, "plot_size_sqm": 200, "floors": 1,
                  "occupants": 2},
        )
        assert response.status_code == 404

    def test_nasa_power_endpoint_requires_paired_dates(self, client):
        response = client.post(
            "/api/building-planner/nasa-power",
            json={"latitude": 13.0, "longitude": 80.0, "start_date": "2024-01-01"},
        )
        assert response.status_code == 422


# ── Agents ───────────────────────────────────────────────────────────────────

@requires_models
class TestAgentEndpoints:
    def test_list_agents_declares_role_boundaries(self, client):
        body = client.get("/api/agents").json()
        domains = {a["domain"] for a in body["agents"]}
        assert domains == {"water", "urban", "flood", "building", "coordinator"}
        for agent in body["agents"]:
            assert agent["wraps"]
            assert agent["may_not"], "each agent must declare what it may not do"
        assert "do not replace" in body["principle"]

    def test_agent_graph_topology(self, client):
        body = client.get("/api/agents/graph").json()
        names = {n["name"] for n in body["topology"]["nodes"]}
        assert {"validate_input", "water_agent", "urban_agent", "flood_agent",
                "building_gate", "building_agent", "coordinator"} == names

    @pytest.mark.parametrize("domain", ["water", "urban", "flood"])
    def test_single_agent(self, client, grid_cell, domain):
        body = client.post(
            f"/api/agents/{domain}", json={"grid_id": grid_cell["grid_id"]}
        ).json()
        assert body["model_output"]
        assert body["analysis"]["result"]["summary"]
        assert body["analysis"]["domain"] == domain

    def test_unknown_agent_domain_is_rejected(self, client, grid_cell):
        response = client.post(
            "/api/agents/weather", json={"grid_id": grid_cell["grid_id"]}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["available"] == ["flood", "urban", "water"]

    def test_pipeline_analyze(self, client, grid_cell):
        response = client.post(
            "/api/agents/analyze",
            json={"grid_id": grid_cell["grid_id"], "include_attribution": False},
        )
        assert response.status_code == 200
        body = response.json()

        for key in ("water_result", "urban_result", "flood_result"):
            assert body[key]
        for key in ("water_analysis", "urban_analysis", "flood_analysis"):
            assert body[key]["result"]["summary"]
        assert body["coordinator_result"]["result"]["overall_recommendation"]
        assert body["trace"]

    def test_coordinator_endpoint(self, client, grid_cell):
        body = client.post(
            "/api/coordinator",
            json={"grid_id": grid_cell["grid_id"], "include_attribution": False},
        ).json()

        assert body["recommendation"]["overall_recommendation"]
        assert body["recommendation"]["headline"]
        assert body["domain_signals"]
        assert set(body["domains"]) == {"water", "urban", "flood", "building"}
        assert "do not replace" in body["principle"]

    def test_coordinator_never_alters_model_output(self, client, grid_cell):
        """The number in the domain payload must equal the model's own prediction."""
        direct = client.post(
            "/api/flood-risk",
            json={"grid_id": grid_cell["grid_id"], "include_attribution": False},
        ).json()
        body = client.post(
            "/api/coordinator",
            json={"grid_id": grid_cell["grid_id"], "include_attribution": False},
        ).json()

        assert (
            body["domains"]["flood"]["model_output"]["flood_probability"]
            == direct["flood_probability"]
        )
        assert (
            body["domain_signals"]["flood"]["flood_probability"]
            == direct["flood_probability"]
        )

    def test_pipeline_rejects_a_missing_location(self, client):
        response = client.post("/api/agents/analyze", json={})
        assert response.status_code == 422

    def test_pipeline_rejects_an_unknown_grid_id(self, client):
        response = client.post("/api/agents/analyze", json={"grid_id": "Atlantis_1"})
        assert response.status_code == 404
