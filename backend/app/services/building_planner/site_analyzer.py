"""
Site analyzer — assembles everything known about a building site.

Combines three distinct kinds of evidence and keeps them labelled as such:

  model_predictions   Model 1 / 2 / 3 output for the grid cell containing the site
  measured            NASA POWER climatology, and the observed geospatial layers
  derived             deterministic classifications computed in code from the above

When a model or NASA POWER is unavailable, the corresponding block records the
failure and the planner continues with what it has, flagging what is missing. It
never fills the gap with a regional average.
"""

from __future__ import annotations

import logging

from app.core import building_guidelines as bg
from app.core.errors import SmartCityError
from app.core.grid import nearest_cell
from app.services.building_planner import nasa_power
from app.services.models import flood_risk, surface_water, urban_expansion

logger = logging.getLogger(__name__)


def _solar_band(irradiance: float) -> str:
    if irradiance >= bg.value("solar", "excellent_irradiance"):
        return "excellent"
    if irradiance >= bg.value("solar", "good_irradiance"):
        return "good"
    if irradiance >= bg.value("solar", "min_viable_irradiance"):
        return "moderate"
    return "low"


def _water_proximity(water: dict | None) -> dict:
    """Classify the site's relationship to surface water, from measured GSW data."""
    if not water:
        return {"classification": "unknown", "reason": "Surface-water model unavailable."}

    status = water.get("water_body_status", {})
    occurrence = status.get("occurrence_pct")
    if occurrence is None:
        return {"classification": "unknown", "reason": "No surface-water observation for this cell."}

    if water.get("is_water_body"):
        classification = "within_water_body_cell"
        reason = (
            f"The 1 km cell containing this site is classified as a surface-water body "
            f"(water present {occurrence:.0f}% of the time). Construction setbacks from "
            f"the water body apply."
        )
    elif occurrence > 5:
        classification = "adjacent_to_water"
        reason = (
            f"Surface water is present in this cell {occurrence:.0f}% of the time, so the "
            f"site is close to a channel or seasonal water body."
        )
    elif occurrence > 0:
        classification = "occasional_water"
        reason = f"Surface water is detected here only occasionally ({occurrence:.1f}% of the time)."
    else:
        classification = "dry"
        reason = "No surface water is detected in this cell."

    return {
        "classification": classification,
        "reason": reason,
        "water_body_status": status.get("status"),
        "occurrence_pct": occurrence,
    }


def _green_cover(urban: dict | None, flood: dict | None) -> dict:
    """Green-cover context from the observed built-up and terrain layers."""
    observed = (urban or {}).get("observed", {})
    built = observed.get("built_fraction_t1")
    if built is None:
        built = (flood or {}).get("observed", {}).get("built_fraction_2020")

    if built is None:
        return {"classification": "unknown", "reason": "No built-up observation for this cell."}

    non_built = round(1.0 - float(built), 4)
    if built >= 0.6:
        classification = "densely_built"
        reason = (
            f"{built * 100:.0f}% of the surrounding cell is built up, leaving little "
            f"permeable or vegetated ground. On-plot green cover carries more weight here."
        )
    elif built >= 0.3:
        classification = "moderately_built"
        reason = f"{built * 100:.0f}% of the cell is built up, with some open ground remaining."
    else:
        classification = "largely_open"
        reason = (
            f"Only {built * 100:.0f}% of the cell is built up, so the site sits in a "
            f"largely open or peri-urban setting."
        )

    return {
        "classification": classification,
        "reason": reason,
        "built_fraction": round(float(built), 4),
        "non_built_fraction": non_built,
    }


def _attempt(label: str, fn, errors: dict):
    """Run one evidence source, recording a structured failure instead of raising."""
    try:
        return fn()
    except SmartCityError as exc:
        logger.warning("Site analysis: %s unavailable — %s", label, exc.message)
        errors[label] = {"error": exc.error_code, "message": exc.message, "detail": exc.detail}
        return None


def analyze_site(lat: float, lon: float, *, include_attribution: bool = False) -> dict:
    """Assemble the full site picture for a location.

    The site is snapped to the nearest cell of the 1 km analysis grid, and that
    cell's id is reported along with the snapping distance so the caller knows the
    spatial resolution the assessment actually has.
    """
    errors: dict = {}
    cell = nearest_cell(lat, lon)
    grid_id = cell["grid_id"]

    water = _attempt(
        "surface_water_model",
        lambda: surface_water.predict(grid_id, explain_prediction=include_attribution),
        errors,
    )
    urban = _attempt(
        "urban_expansion_model",
        lambda: urban_expansion.predict(grid_id, explain_prediction=include_attribution),
        errors,
    )
    flood = _attempt(
        "flood_risk_model",
        lambda: flood_risk.predict(grid_id, explain_prediction=include_attribution),
        errors,
    )
    climate = _attempt("nasa_power", lambda: nasa_power.get_climatology(lat, lon), errors)

    derived = {
        "water_proximity": _water_proximity(water),
        "green_cover": _green_cover(urban, flood),
    }
    if climate:
        derived["solar_potential"] = {
            "classification": _solar_band(climate["solar_kwh_m2_day"]),
            "irradiance_kwh_m2_day": climate["solar_kwh_m2_day"],
            "reason": (
                f"Long-term mean irradiance of {climate['solar_kwh_m2_day']} kWh/m2/day "
                f"at this location."
            ),
        }
        derived["rainfall_regime"] = {
            "annual_mm": climate["rainfall_annual_mm"],
            "wettest_month": climate.get("wettest_month"),
            "monsoon_concentration": climate.get("monsoon_concentration"),
            "reason": (
                f"{climate['rainfall_annual_mm']:.0f} mm falls annually, with "
                f"{(climate.get('monsoon_concentration') or 0) * 100:.0f}% arriving in the "
                f"June-September monsoon."
            ),
        }

    site = {
        "location": {
            "requested_lat": lat,
            "requested_lon": lon,
            "grid_id": grid_id,
            "grid_lat": cell["lat"],
            "grid_lon": cell["lon"],
            "city": cell["city"],
            "state": cell["state"],
            "snap_distance_km": cell.get("distance_km"),
        },
        "model_predictions": {
            "surface_water": water,
            "urban_expansion": urban,
            "flood_risk": flood,
        },
        "measured": {"climate": climate},
        "derived": derived,
        "unavailable": errors,
        "data_completeness": {
            "surface_water_model": water is not None,
            "urban_expansion_model": urban is not None,
            "flood_risk_model": flood is not None,
            "nasa_power": climate is not None,
        },
    }
    logger.info(
        "Site analysis for (%.4f, %.4f) -> %s: %d/4 evidence sources available",
        lat, lon, grid_id, sum(site["data_completeness"].values()),
    )
    return site
