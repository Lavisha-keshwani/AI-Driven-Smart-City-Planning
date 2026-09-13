"""
Response schemas.

Model-prediction payloads are typed but permissive (`extra="allow"`), because the
authoritative shape of a prediction is defined by the model service that produces
it; pinning every field here would mean two places to change whenever a model gains
a diagnostic. The fields declared are the ones the frontend relies on and the ones
whose meaning the API guarantees.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.schemas import CoordinatorReport, DomainAnalysis


class ErrorResponse(BaseModel):
    """The envelope every failure uses."""

    error: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")
    detail: dict = Field(default_factory=dict)


class FeatureAttribution(BaseModel):
    feature: str
    importance: float
    direction: Literal["positive", "negative", "neutral"]
    shap_value: float


class WaterPrediction(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    grid_id: str
    city: str
    lat: float | None = None
    lon: float | None = None
    water_body_probability: float
    is_water_body: bool
    classification: str
    decision_threshold: float
    observed: dict = Field(default_factory=dict)
    water_body_status: dict = Field(default_factory=dict)
    feature_attribution: list[FeatureAttribution] | None = None


class UrbanPrediction(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    grid_id: str
    city: str
    lat: float | None = None
    lon: float | None = None
    suitability_score: float = Field(ge=0, le=1)
    suitability_class: str
    class_meaning: str
    confidence: float
    class_probabilities: dict[str, float]
    constraints: list[dict] = Field(default_factory=list)
    observed: dict = Field(default_factory=dict)
    feature_attribution: list[FeatureAttribution] | None = None


class FloodPrediction(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    grid_id: str
    city: str
    lat: float | None = None
    lon: float | None = None
    flood_probability: float = Field(ge=0, le=1)
    risk_level: str
    risk_meaning: str
    decision_threshold: float
    risk_drivers: list[dict] = Field(default_factory=list)
    observed: dict = Field(default_factory=dict)
    feature_attribution: list[FeatureAttribution] | None = None


class CityLayer(BaseModel):
    """A batch of per-cell predictions for one city."""

    city: str
    count: int
    cells: list[dict]


class GeoJsonResponse(BaseModel):
    """A GeoJSON FeatureCollection of grid cells."""

    model_config = ConfigDict(extra="allow")

    type: Literal["FeatureCollection"]
    crs: dict
    features: list[dict]


class MicroplasticResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    task: str
    detections: list[dict]
    count: int
    confidence: float
    classification: str
    microplastic_detected: bool
    class_probabilities: dict[str, float]
    input: dict
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str


class BuildingPlannerResponse(BaseModel):
    """Site assessment plus deterministic recommendations, and the agent's reading."""

    model_config = ConfigDict(extra="allow")

    site: dict
    recommendations: list[dict]
    skipped_rules: list[dict]
    priority_counts: dict[str, int]
    guidelines_applied: dict
    disclaimer: str
    interpretation: DomainAnalysis | None = Field(
        default=None,
        description="Building Sustainability Agent narrative. Null when the LLM is off.",
    )


class PipelineResponse(BaseModel):
    """Full multi-agent pipeline output.

    The `*_result` blocks hold untouched model output; the `*_analysis` blocks hold
    agent interpretation of it. That separation is the API's core guarantee.
    """

    model_config = ConfigDict(extra="allow")

    location: dict
    water_result: dict | None = None
    urban_result: dict | None = None
    flood_result: dict | None = None
    building_result: dict | None = None

    water_analysis: DomainAnalysis | None = None
    urban_analysis: DomainAnalysis | None = None
    flood_analysis: DomainAnalysis | None = None
    building_analysis: DomainAnalysis | None = None

    coordinator_result: CoordinatorReport | None = None

    trace: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    service: str
    version: str
    models_loaded: str
    datasets_present: str
    llm: dict


class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    models: dict
    datasets: dict
    all_models_loaded: bool
    all_datasets_present: bool
    llm: dict
    grid: dict
    nasa_power_cache: dict
    explainability: dict


class MetricsResponse(BaseModel):
    """Validation evidence for one model."""

    model_config = ConfigDict(extra="allow")

    model: str
    task: str | None = None
    metrics_source: str | None = None
    limitations: list[str] = Field(default_factory=list)


class CitiesResponse(BaseModel):
    count: int
    cities: list[dict]


class GridCellsResponse(BaseModel):
    city: str
    count: int
    grid_ids: list[str]


class AgentInfoResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    topology: dict
    agents: list[dict]
    llm: dict
    principle: str


class Acknowledged(BaseModel):
    """Generic acknowledgement payload."""

    ok: bool = True
    detail: Any = None
