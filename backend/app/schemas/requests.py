"""Request schemas. Validation happens here so routers stay thin."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BuildingType = Literal["residential", "office", "commercial"]


class GridQuery(BaseModel):
    """Address a single grid cell, by id or by coordinates."""

    model_config = ConfigDict(extra="forbid")

    grid_id: str | None = Field(default=None, description="1 km analysis grid cell id.")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    include_attribution: bool = Field(
        default=True, description="Include SHAP feature attributions for the prediction."
    )

    @model_validator(mode="after")
    def _require_location(self):
        if not self.grid_id and (self.lat is None or self.lon is None):
            raise ValueError("Supply either grid_id, or both lat and lon.")
        return self


class CityQuery(BaseModel):
    """Address every cell in a city."""

    model_config = ConfigDict(extra="forbid")

    city: str = Field(min_length=1, description="City name, matched case-insensitively.")
    limit: int | None = Field(
        default=None, ge=1, le=20000,
        description="Cap the number of cells returned. Omit for the whole city.",
    )


class BuildingParams(BaseModel):
    """Sustainable Building Planner inputs."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90, description="Site latitude.")
    lon: float = Field(ge=-180, le=180, description="Site longitude.")
    building_type: BuildingType = "residential"
    plot_size_sqm: float = Field(gt=0, le=1_000_000, description="Plot area in square metres.")
    floors: int = Field(ge=1, le=100)
    occupants: int = Field(ge=1, le=100_000)
    budget_inr: float | None = Field(default=None, ge=0)
    roof_area_sqm: float | None = Field(
        default=None, gt=0,
        description="Actual roof catchment area, if known. Otherwise derived from plot size.",
    )
    requirements: list[str] = Field(
        default_factory=list, max_length=30,
        description="Free-text requirements from the user, echoed back for context.",
    )

    @model_validator(mode="after")
    def _roof_within_plot(self):
        if self.roof_area_sqm and self.roof_area_sqm > self.plot_size_sqm:
            raise ValueError("roof_area_sqm cannot exceed plot_size_sqm.")
        return self


class PipelineRequest(BaseModel):
    """Run the full multi-agent pipeline for a location."""

    model_config = ConfigDict(extra="forbid")

    grid_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    building_params: BuildingParams | None = Field(
        default=None,
        description="Supply to activate the Building Sustainability Agent.",
    )
    include_attribution: bool = True

    @model_validator(mode="after")
    def _require_location(self):
        if not self.grid_id and (self.lat is None or self.lon is None):
            raise ValueError("Supply either grid_id, or both lat and lon.")
        return self


class NasaPowerRequest(BaseModel):
    """Direct NASA POWER query."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    start_date: str | None = Field(
        default=None, description="YYYY-MM-DD. Omit with end_date for climatology."
    )
    end_date: str | None = Field(default=None, description="YYYY-MM-DD.")

    @model_validator(mode="after")
    def _dates_paired(self):
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError(
                "Supply both start_date and end_date for a daily series, or neither "
                "for long-term climatology."
            )
        return self
