"""
Model inference tests.

These check the contract each model service guarantees, and — most importantly —
that the inference path reproduces the metrics the training run recorded on its
unseen-city holdout. That reproduction test is what proves the feature assembly,
feature ordering and threshold handling in this codebase match training, rather
than merely running without error.
"""

from __future__ import annotations

import json

import pytest

from app.core import config
from app.core.errors import GridNotFoundError, InferenceError, InvalidInputError
from app.services.models import (
    explain,
    feature_store,
    flood_risk,
    microplastic,
    registry,
    surface_water,
    urban_expansion,
)
from tests.conftest import requires_hmpd, requires_models

pytestmark = requires_models


# ── Model 1 — Surface Water ──────────────────────────────────────────────────

class TestSurfaceWater:
    def test_predict_contract(self, grid_cell):
        result = surface_water.predict(grid_cell["grid_id"])

        assert result["grid_id"] == grid_cell["grid_id"]
        assert 0.0 <= result["water_body_probability"] <= 1.0
        assert isinstance(result["is_water_body"], bool)
        assert result["classification"] in {"water_body", "non_water_body"}
        # The classification must follow the threshold, not drift from it.
        assert result["is_water_body"] == (
            result["water_body_probability"] >= result["decision_threshold"]
        )

    def test_observed_values_are_separate_from_prediction(self, grid_cell):
        """Measured GSW statistics must not be conflated with model output."""
        result = surface_water.predict(grid_cell["grid_id"])
        assert "observed" in result
        assert "water_body_probability" not in result["observed"]
        assert "measured" in result["water_body_status"]["basis"].lower() or \
               "observations" in result["water_body_status"]["basis"].lower()

    def test_feature_order_comes_from_the_fitted_model(self):
        order = surface_water.feature_order()
        model = registry.surface_water_model()
        assert order == list(model.feature_names_in_)

    def test_unknown_grid_id_raises(self):
        with pytest.raises(GridNotFoundError):
            surface_water.predict("NotACity_00000000")

    def test_batch_matches_single_cell(self, sample_city):
        batch = surface_water.predict_city(sample_city, limit=5)
        assert len(batch) == 5
        single = surface_water.predict(batch[0]["grid_id"])
        assert batch[0]["water_body_probability"] == single["water_body_probability"]

    def test_metrics_report_real_validation_evidence(self):
        metrics = surface_water.metrics()
        assert metrics["selected_model_metrics"] is not None
        split = metrics["city_split"]
        # City-based holdout: the splits must not share any city.
        assert not set(split["train_cities"]) & set(split["test_cities"])
        assert not set(split["train_cities"]) & set(split["val_cities"])
        assert not set(split["val_cities"]) & set(split["test_cities"])
        assert metrics["limitations"]

    def test_metrics_do_not_claim_the_unreproducible_regression_scores(self):
        """The 0.995 / 0.985 R2 figures belong to a different model lineage."""
        blob = json.dumps(surface_water.metrics())
        assert "0.995" not in blob
        assert "r2" not in blob.lower()


# ── Model 2 — Urban Expansion ───────────────────────────────────────────────

class TestUrbanExpansion:
    def test_predict_contract(self, grid_cell):
        result = urban_expansion.predict(grid_cell["grid_id"])

        assert 0.0 <= result["suitability_score"] <= 1.0
        assert result["suitability_class"] in {"GREEN", "YELLOW", "RED"}
        assert result["class_meaning"]
        probabilities = result["class_probabilities"]
        assert set(probabilities) == {"GREEN", "YELLOW", "RED"}
        assert sum(probabilities.values()) == pytest.approx(1.0, abs=1e-3)

    def test_score_is_the_expected_class_value(self, grid_cell):
        """score must equal P(YELLOW)*0.5 + P(GREEN)*1.0, as documented."""
        result = urban_expansion.predict(grid_cell["grid_id"])
        p = result["class_probabilities"]
        expected = p["YELLOW"] * 0.5 + p["GREEN"] * 1.0
        assert result["suitability_score"] == pytest.approx(expected, abs=1e-3)

    def test_class_is_argmax_by_default(self, grid_cell):
        result = urban_expansion.predict(grid_cell["grid_id"])
        p = result["class_probabilities"]
        assert result["suitability_class"] == max(p, key=p.get)

    def test_forward_validation_epochs_are_exposed(self, grid_cell):
        """The T0/T1 design must be visible, not implicit."""
        observed = urban_expansion.predict(grid_cell["grid_id"])["observed"]
        assert observed["t0_year"] < observed["t1_year"]
        assert observed["t0_year"] == config.M2_T0_YEAR

    def test_feature_order_comes_from_the_booster(self):
        order = urban_expansion.feature_order()
        model = registry.urban_expansion_model()
        assert order == list(model.booster_.feature_name())
        assert len(order) == model.n_features_in_

    def test_constraints_are_measured_not_asserted(self, sample_city):
        """Every constraint must carry the measurement that triggered it."""
        for cell in urban_expansion.predict_city(sample_city, limit=40):
            detail = urban_expansion.predict(cell["grid_id"], explain_prediction=False)
            for constraint in detail["constraints"]:
                assert constraint["measured"], constraint
                assert constraint["severity"] in {"low", "moderate", "high"}
            if detail["constraints"]:
                return

    def test_metrics_document_the_road_density_exclusion(self):
        blob = json.dumps(urban_expansion.metrics()).lower()
        assert "openstreetmap" in blob or "road" in blob


# ── Model 3 — Flood Risk ────────────────────────────────────────────────────

class TestFloodRisk:
    def test_predict_contract(self, grid_cell):
        result = flood_risk.predict(grid_cell["grid_id"])
        assert 0.0 <= result["flood_probability"] <= 1.0
        assert result["risk_level"] in {"LOW", "MODERATE", "HIGH"}
        assert result["flood_predicted"] == (
            result["flood_probability"] >= result["decision_threshold"]
        )

    @pytest.mark.parametrize(
        "probability,expected",
        [(0.0, "LOW"), (0.29, "LOW"), (0.30, "MODERATE"), (0.59, "MODERATE"),
         (0.60, "HIGH"), (1.0, "HIGH")],
    )
    def test_risk_bands_are_monotone_at_their_edges(self, probability, expected):
        assert flood_risk.risk_level(probability) == expected

    def test_risk_drivers_carry_measurements(self, sample_city):
        for cell in flood_risk.predict_city(sample_city, limit=40):
            detail = flood_risk.predict(cell["grid_id"], explain_prediction=False)
            for driver in detail["risk_drivers"]:
                assert driver["measured"], driver
                assert driver["reason"]
            if detail["risk_drivers"]:
                return

    def test_metrics_use_city_based_holdout(self):
        metrics = flood_risk.metrics()
        assert "city-based holdout" in metrics["validation_strategy"].lower()
        assert "leak" in metrics["validation_strategy"].lower()
        split = metrics["city_split"]
        assert not set(split["train_cities"]) & set(split["test_cities"])

    def test_metrics_include_all_required_evaluation_measures(self):
        selected = flood_risk.metrics()["selected_model_metrics"]
        for measure in ("precision", "recall", "f1", "roc_auc", "pr_auc"):
            assert selected[measure] is not None, measure

    def test_metrics_include_city_wise_performance(self):
        per_city = flood_risk.metrics()["city_wise_performance"]
        assert per_city and len(per_city) > 1

    def test_low_risk_is_documented_as_absence_of_evidence(self):
        blob = " ".join(flood_risk.metrics()["limitations"]).lower()
        assert "absence of evidence" in blob


# ── Metric reproduction: the proof the wiring matches training ───────────────

@pytest.mark.parametrize(
    "service,dataset,metrics_dir,target,algorithm",
    [
        pytest.param(
            surface_water, config.M1_DATASET, config.M1_METRICS_DIR,
            "is_water_body", config.M1_ALGORITHM, id="model1_surface_water",
        ),
        pytest.param(
            flood_risk, config.M3_DATASET, config.M3_METRICS_DIR,
            "flood_label", config.M3_ALGORITHM, id="model3_flood_risk",
        ),
    ],
)
def test_inference_path_reproduces_published_holdout_metrics(
    service, dataset, metrics_dir, target, algorithm
):
    """Score the training run's unseen-city test set through this codebase.

    If feature assembly, feature order or the threshold differed from training in any
    way, these numbers would drift. Matching to four decimal places is the evidence
    that the deployed inference path is the trained one.
    """
    import pandas as pd
    from sklearn.metrics import (
        average_precision_score,
        precision_recall_fscore_support,
        roc_auc_score,
    )

    split = json.loads((metrics_dir / "city_split.json").read_text())
    published = pd.read_csv(metrics_dir / "test_metrics_comparison.csv")
    published = published[published["model"] == algorithm].iloc[0]

    if service is surface_water:
        table = feature_store.surface_water_table()
        model = registry.surface_water_model()
    else:
        table = feature_store.flood_risk_table()
        model = registry.flood_risk_model()

    test = table[table["city"].isin(split["test_cities"])]
    assert len(test) > 0, "The holdout cities produced no rows"

    y_true = test[target].astype(int)
    probabilities = model.predict_proba(test[service.feature_order()])[:, 1]
    predictions = (probabilities >= service.operating_threshold()).astype(int)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, predictions, average="binary", zero_division=0
    )
    assert precision == pytest.approx(published["precision"], abs=5e-4)
    assert recall == pytest.approx(published["recall"], abs=5e-4)
    assert f1 == pytest.approx(published["f1"], abs=5e-4)
    assert roc_auc_score(y_true, probabilities) == pytest.approx(
        published["roc_auc"], abs=5e-4
    )
    assert average_precision_score(y_true, probabilities) == pytest.approx(
        published["pr_auc"], abs=5e-4
    )


def test_urban_expansion_agrees_with_forward_validation_target():
    """Model 2's predictions must track the tercile-binned GHSL growth target.

    This is the check that the rebuilt feature table — including the city_code and
    state_code encoding, which the training run did not document — matches what the
    model was fitted on. Agreement near the published 0.835 test accuracy confirms it;
    a broken encoding would collapse agreement towards chance (0.33).
    """
    import numpy as np

    table = feature_store.urban_expansion_table()
    model = registry.urban_expansion_model()

    candidates = table.dropna(subset=["built_t0", "built_t1"])
    predictions = model.predict(candidates[urban_expansion.feature_order()].astype(float))

    growth = candidates["built_t1"] - candidates["built_t0"]
    edges = growth.quantile([1 / 3, 2 / 3]).to_numpy()
    target = np.digitize(growth, edges)

    agreement = float((predictions == target).mean())
    assert agreement > 0.75, (
        f"Only {agreement:.1%} agreement with the forward-validation target. The "
        f"rebuilt Model 2 feature table likely does not match training."
    )


# ── Explainability ──────────────────────────────────────────────────────────

class TestExplainability:
    @pytest.mark.parametrize(
        "service", [surface_water, urban_expansion, flood_risk],
        ids=["model1", "model2", "model3"],
    )
    def test_attribution_shape(self, service, grid_cell):
        result = service.predict(grid_cell["grid_id"], explain_prediction=True)
        attribution = result["feature_attribution"]

        if not explain.shap_available():
            assert attribution is None
            pytest.skip("shap is not installed")

        assert attribution, "SHAP is available but produced no attribution"
        importances = [a["importance"] for a in attribution]
        assert importances == sorted(importances, reverse=True), "must be rank-ordered"
        for item in attribution:
            assert 0.0 <= item["importance"] <= 1.0
            assert item["direction"] in {"positive", "negative", "neutral"}

    def test_one_hot_columns_fold_back_to_the_source_feature(self, grid_cell):
        """A caller must see `state`, not `state_Kerala`."""
        if not explain.shap_available():
            pytest.skip("shap is not installed")
        result = surface_water.predict(grid_cell["grid_id"], explain_prediction=True)
        features = {a["feature"] for a in result["feature_attribution"]}
        raw = set(surface_water.feature_order())
        assert features <= raw, f"Unmapped transformed names leaked: {features - raw}"

    def test_attribution_is_omitted_when_not_requested(self, grid_cell):
        result = surface_water.predict(grid_cell["grid_id"], explain_prediction=False)
        assert "feature_attribution" not in result


# ── Microplastic screening ──────────────────────────────────────────────────

@requires_hmpd
class TestMicroplastic:
    def _channels(self, image_dir, particle_id):
        return tuple(
            (image_dir / f"{particle_id}_{ch}.bmp").read_bytes() for ch in ("R", "A", "P")
        )

    def test_classifies_labelled_particles_correctly(self, hmpd_particles, hmpd_image_dir):
        """Check against HMPD's own labels, not a self-consistent assertion."""
        checked = 0
        for expected, particles in (
            ("microplastic_candidate", hmpd_particles["positive"]),
            ("no_microplastic_detected", hmpd_particles["negative"]),
        ):
            for particle_id in particles:
                result = microplastic.analyze_polarimetric(
                    *self._channels(hmpd_image_dir, particle_id)
                )
                assert result["classification"] == expected, particle_id
                assert 0.5 <= result["confidence"] <= 1.0
                checked += 1
        assert checked >= 4, "Too few complete particles to make the test meaningful"

    def test_detection_count_matches_classification(self, hmpd_particles, hmpd_image_dir):
        result = microplastic.analyze_polarimetric(
            *self._channels(hmpd_image_dir, hmpd_particles["positive"][0])
        )
        assert result["count"] == len(result["detections"]) == 1
        assert result["detections"][0]["region"] == "whole_image"

    def test_every_response_carries_the_scope_disclaimer(
        self, hmpd_particles, hmpd_image_dir
    ):
        result = microplastic.analyze_polarimetric(
            *self._channels(hmpd_image_dir, hmpd_particles["negative"][0])
        )
        disclaimer = result["disclaimer"].lower()
        assert "screening only" in disclaimer
        assert "composition" in disclaimer
        assert "concentration" in disclaimer

    def test_single_channel_upload_is_rejected(self):
        """Replicating one channel scores at chance, so it must not be accepted."""
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("L", (64, 64)).save(buffer, "PNG")
        with pytest.raises(InvalidInputError) as exc:
            microplastic.analyze_composite(buffer.getvalue(), filename="x.png")
        assert "chance" in exc.value.message.lower()

    @pytest.mark.parametrize(
        "payload,filename",
        [(b"", "x.png"), (b"not an image", "x.png"), (b"x" * 100, "x.exe")],
        ids=["empty", "undecodable", "bad_extension"],
    )
    def test_invalid_uploads_are_rejected(self, payload, filename):
        with pytest.raises(InvalidInputError):
            microplastic.analyze_composite(payload, filename=filename)

    def test_oversize_upload_is_rejected(self, monkeypatch):
        monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
        with pytest.raises(InvalidInputError) as exc:
            microplastic.analyze_composite(b"x" * 100, filename="x.png")
        assert "limit" in exc.value.message.lower()

    def test_metrics_report_cross_validation_not_invented_numbers(self):
        metrics = microplastic.metrics()
        cv = metrics["cross_validation"]
        assert 0.0 < cv["mean_accuracy"] <= 1.0
        assert cv["mean_f1"] is not None
        assert metrics["per_fold"], "Per-fold results should come from cv_results.csv"


# ── Missing-artifact behaviour ───────────────────────────────────────────────

def test_missing_model_raises_a_clear_error_naming_the_config_key(monkeypatch, grid_cell):
    """A missing artifact must produce actionable guidance, never a fake prediction."""
    from app.core.errors import ModelUnavailableError

    monkeypatch.setattr(registry, "_model3", lambda: None)
    with pytest.raises(ModelUnavailableError) as exc:
        registry.flood_risk_model()

    assert exc.value.status_code == 503
    assert exc.value.detail["config_key"] == "FLOOD_MODEL_PATH"
    assert "FLOOD_MODEL_PATH" in exc.value.detail["remedy"]


def test_missing_threshold_refuses_to_classify(monkeypatch):
    """Without a tuned threshold, no classification may be issued."""
    monkeypatch.setattr(registry, "model3_thresholds", lambda: {})
    with pytest.raises(InferenceError):
        flood_risk.operating_threshold()
