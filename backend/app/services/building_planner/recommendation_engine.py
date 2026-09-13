"""
Sustainable Building Planner — deterministic recommendation rules.

Pure rules, arithmetic and cited guideline parameters. No ML model, and no LLM:
whether a recommendation fires, and every number in it, is decided in this file,
so the same inputs always produce the same advice and each figure can be traced.

Every recommendation carries:

    recommendation     what to do
    priority           HIGH / MEDIUM / LOW
    reason             why this site triggers it
    triggering_data    the exact values that fired the rule
    calculations       the arithmetic, with its inputs
    guideline_basis    the cited parameters used, with their provenance

A rule whose triggering evidence is missing does not fire, and says so in
`skipped`. Nothing is estimated from a substituted default.
"""

from __future__ import annotations

import logging
import math

from app.core import building_guidelines as bg

logger = logging.getLogger(__name__)

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
_PRIORITY_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}


def _daily_demand_lpcd(building_type: str) -> tuple[float, str]:
    if building_type in {"office", "commercial"}:
        return bg.value("water", "office_demand_lpcd"), "water.office_demand_lpcd"
    return bg.value("water", "domestic_demand_lpcd"), "water.domestic_demand_lpcd"


def _roof_area(plot_size_sqm: float, roof_area_sqm: float | None) -> tuple[float, str]:
    """Roof catchment area — supplied if known, otherwise derived from plot share."""
    if roof_area_sqm and roof_area_sqm > 0:
        return float(roof_area_sqm), "supplied by caller"
    share = bg.value("rainwater", "roof_share_of_plot")
    return plot_size_sqm * share, f"{share:.0%} of plot area (rainwater.roof_share_of_plot)"


# ── Individual rules ─────────────────────────────────────────────────────────

def _rainwater_harvesting(site: dict, params: dict, skipped: list) -> dict | None:
    rainfall_block = site["derived"].get("rainfall_regime")
    if not rainfall_block or rainfall_block.get("annual_mm") is None:
        skipped.append({
            "rule": "Rainwater harvesting",
            "reason": "Annual rainfall is unknown because NASA POWER data is unavailable.",
        })
        return None

    rainfall_mm = float(rainfall_block["annual_mm"])
    minimum = bg.value("rainwater", "min_viable_annual_rainfall_mm")
    plot = float(params["plot_size_sqm"])
    occupants = int(params["occupants"])

    roof_area, roof_basis = _roof_area(plot, params.get("roof_area_sqm"))
    runoff = bg.value("rainwater", "roof_runoff_coefficient")
    # Yield (litres) = catchment area (m2) x rainfall (m) x runoff coefficient x 1000 L/m3
    annual_yield_l = roof_area * (rainfall_mm / 1000.0) * runoff * 1000.0

    lpcd, lpcd_key = _daily_demand_lpcd(params["building_type"])
    annual_demand_l = occupants * lpcd * 365.0
    coverage = annual_yield_l / annual_demand_l if annual_demand_l else 0.0

    storage_days = bg.value("rainwater", "storage_days_of_demand")
    tank_l = round(occupants * lpcd * storage_days)

    if rainfall_mm < minimum:
        skipped.append({
            "rule": "Rainwater harvesting",
            "reason": (
                f"Annual rainfall of {rainfall_mm:.0f} mm is below the "
                f"{minimum:.0f} mm threshold at which roof catchment on a single plot "
                f"is generally worthwhile."
            ),
            "triggering_data": {"rainfall_annual_mm": rainfall_mm},
        })
        return None

    monsoon = rainfall_block.get("monsoon_concentration")
    if rainfall_mm >= 800 or coverage >= 0.5:
        priority = HIGH
    elif rainfall_mm >= 600:
        priority = MEDIUM
    else:
        priority = LOW

    reason = (
        f"Annual rainfall of {rainfall_mm:.0f} mm over roughly {roof_area:.0f} m2 of roof "
        f"yields about {annual_yield_l:,.0f} litres a year, covering approximately "
        f"{min(coverage, 1.0):.0%} of the {occupants}-occupant demand."
    )
    if monsoon and monsoon > 0.7:
        reason += (
            f" {monsoon:.0%} of that rain arrives in the monsoon, so storage matters "
            f"more than catchment area here."
        )

    return {
        "recommendation": "Install a rooftop rainwater harvesting system with storage and recharge",
        "category": "water",
        "priority": priority,
        "reason": reason,
        "triggering_data": {
            "rainfall_annual_mm": rainfall_mm,
            "monsoon_concentration": monsoon,
            "roof_area_sqm": round(roof_area, 1),
            "occupants": occupants,
        },
        "calculations": {
            "roof_area_sqm": round(roof_area, 1),
            "roof_area_basis": roof_basis,
            "runoff_coefficient": runoff,
            "annual_yield_litres": round(annual_yield_l),
            "annual_demand_litres": round(annual_demand_l),
            "demand_coverage_fraction": round(min(coverage, 1.0), 3),
            "recommended_storage_litres": tank_l,
            "storage_basis": f"{storage_days} days of demand at {lpcd} L/person/day",
            "formula": "yield_L = roof_area_m2 * (rainfall_mm / 1000) * runoff_coefficient * 1000",
        },
        "guideline_basis": [
            bg.citation("rainwater", "roof_runoff_coefficient"),
            bg.citation("rainwater", "storage_days_of_demand"),
            bg.citation("water", lpcd_key.split(".")[1]),
            bg.citation("rainwater", "mandatory_plot_area_sqm"),
        ],
    }


def _solar(site: dict, params: dict, skipped: list) -> dict | None:
    solar_block = site["derived"].get("solar_potential")
    if not solar_block:
        skipped.append({
            "rule": "Rooftop solar",
            "reason": "Solar irradiance is unknown because NASA POWER data is unavailable.",
        })
        return None

    irradiance = float(solar_block["irradiance_kwh_m2_day"])
    minimum = bg.value("solar", "min_viable_irradiance")
    if irradiance < minimum:
        skipped.append({
            "rule": "Rooftop solar",
            "reason": (
                f"Irradiance of {irradiance} kWh/m2/day is below the {minimum} "
                f"kWh/m2/day threshold for a viable rooftop system."
            ),
            "triggering_data": {"solar_kwh_m2_day": irradiance},
        })
        return None

    plot = float(params["plot_size_sqm"])
    roof_area, roof_basis = _roof_area(plot, params.get("roof_area_sqm"))
    usable_share = bg.value("solar", "usable_roof_share")
    area_per_kw = bg.value("solar", "area_per_kw_sqm")
    performance_ratio = bg.value("solar", "performance_ratio")

    usable_roof = roof_area * usable_share
    roof_limited_kw = math.floor((usable_roof / area_per_kw) * 10) / 10  # 0.1 kW granularity
    if roof_limited_kw < 1.0:
        skipped.append({
            "rule": "Rooftop solar",
            "reason": (
                f"Usable roof area of about {usable_roof:.0f} m2 supports less than 1 kW "
                f"at {area_per_kw} m2/kW, too small for a grid-connected system."
            ),
            "triggering_data": {"usable_roof_sqm": round(usable_roof, 1)},
        })
        return None

    # Size against demand too, so the recommendation is not simply "fill the roof".
    floors = int(params["floors"])
    headroom = bg.value("solar", "demand_headroom")
    if params["building_type"] in {"office", "commercial"}:
        floor_area = plot * bg.value("site", "max_ground_coverage") * floors
        monthly_demand_kwh = floor_area * bg.value("solar", "office_kwh_per_sqm_month")
        demand_basis = (
            f"{floor_area:.0f} m2 floor area at "
            f"{bg.value('solar', 'office_kwh_per_sqm_month')} kWh/m2/month"
        )
    else:
        occupants = int(params["occupants"])
        monthly_demand_kwh = occupants * bg.value("solar", "residential_kwh_per_person_month")
        demand_basis = (
            f"{occupants} occupants at "
            f"{bg.value('solar', 'residential_kwh_per_person_month')} kWh/person/month"
        )

    # Capacity needed so generation meets demand (plus headroom):
    #   kW = daily_demand_kWh / (irradiance * performance_ratio)
    daily_demand_kwh = monthly_demand_kwh / 30.0
    demand_matched_kw = math.ceil(
        (daily_demand_kwh * headroom) / (irradiance * performance_ratio) * 10
    ) / 10
    capacity_kw = min(roof_limited_kw, demand_matched_kw)
    binding = "roof area" if roof_limited_kw <= demand_matched_kw else "estimated demand"

    # Generation (kWh/day) = capacity (kW) x irradiance (kWh/m2/day) x performance ratio
    daily_kwh = capacity_kw * irradiance * performance_ratio
    annual_kwh = daily_kwh * 365.0
    demand_coverage = (daily_kwh / daily_demand_kwh) if daily_demand_kwh else None

    priority = (
        HIGH if irradiance >= bg.value("solar", "excellent_irradiance")
        else MEDIUM if irradiance >= bg.value("solar", "good_irradiance")
        else LOW
    )

    reason = (
        f"Irradiance here averages {irradiance} kWh/m2/day, rated "
        f"{solar_block['classification']}. A {capacity_kw:.1f} kW system generates roughly "
        f"{annual_kwh:,.0f} kWh a year"
    )
    if demand_coverage is not None:
        reason += f", about {min(demand_coverage, 1.0):.0%} of estimated consumption"
    reason += f". Size is limited by {binding}."

    return {
        "recommendation": f"Install a {capacity_kw:.1f} kW rooftop solar photovoltaic system",
        "category": "energy",
        "priority": priority,
        "reason": reason,
        "triggering_data": {
            "solar_kwh_m2_day": irradiance,
            "solar_classification": solar_block["classification"],
            "roof_area_sqm": round(roof_area, 1),
            "building_type": params["building_type"],
        },
        "calculations": {
            "roof_area_sqm": round(roof_area, 1),
            "roof_area_basis": roof_basis,
            "usable_roof_sqm": round(usable_roof, 1),
            "usable_roof_share": usable_share,
            "roof_limited_capacity_kw": roof_limited_kw,
            "demand_matched_capacity_kw": demand_matched_kw,
            "recommended_capacity_kw": capacity_kw,
            "limiting_factor": binding,
            "estimated_monthly_demand_kwh": round(monthly_demand_kwh),
            "demand_basis": demand_basis,
            "demand_headroom_factor": headroom,
            "area_per_kw_sqm": area_per_kw,
            "performance_ratio": performance_ratio,
            "estimated_daily_generation_kwh": round(daily_kwh, 1),
            "estimated_annual_generation_kwh": round(annual_kwh),
            "demand_coverage_fraction": (
                round(min(demand_coverage, 1.0), 3) if demand_coverage is not None else None
            ),
            "formula": "generation_kWh_day = capacity_kW * irradiance_kWh_m2_day * performance_ratio",
        },
        "guideline_basis": [
            bg.citation("solar", "area_per_kw_sqm"),
            bg.citation("solar", "performance_ratio"),
            bg.citation("solar", "usable_roof_share"),
            bg.citation("solar", "residential_kwh_per_person_month"),
            bg.citation("solar", "demand_headroom"),
        ],
    }


def _passive_cooling(site: dict, params: dict, skipped: list) -> dict | None:
    climate = site["measured"].get("climate")
    if not climate or climate.get("temperature_c") is None:
        skipped.append({
            "rule": "Passive cooling",
            "reason": "Temperature data is unavailable, so cooling strategy cannot be assessed.",
        })
        return None

    mean_temp = float(climate["temperature_c"])
    max_temp = climate.get("temperature_max_c")
    humidity = climate.get("humidity_pct")

    trigger = bg.value("thermal", "passive_cooling_trigger_c")
    record_high = bg.value("thermal", "record_high_trigger_c")
    humid_trigger = bg.value("thermal", "high_humidity_trigger_pct")

    if mean_temp < trigger and not (max_temp and max_temp >= record_high):
        skipped.append({
            "rule": "Passive cooling",
            "reason": (
                f"Mean temperature of {mean_temp}°C is below the {trigger}°C "
                f"trigger and the record high stays under {record_high}°C, so cooling "
                f"load is not the dominant concern at this site."
            ),
            "triggering_data": {"temperature_c": mean_temp},
        })
        return None

    measures = [
        "orient the longer facades north and south to cut east and west solar gain",
        f"apply a cool-roof finish with solar reflectance of at least "
        f"{bg.value('thermal', 'cool_roof_solar_reflectance'):.2f}",
        "shade east and west openings with overhangs, fins or deciduous planting",
    ]
    is_humid = humidity is not None and float(humidity) >= humid_trigger
    if is_humid:
        measures.append(
            "size openings for cross-ventilation on opposite walls; in this humidity "
            "air movement cools more effectively than evaporative systems"
        )
    else:
        measures.append(
            "use evaporative cooling and high thermal mass, which work well in this dry air"
        )
    if max_temp and float(max_temp) >= record_high:
        measures.append("insulate the roof and west wall, the surfaces driving peak heat gain")

    openable = bg.value("thermal", "openable_area_share_of_floor")
    floor_area = float(params["plot_size_sqm"]) * bg.value("site", "max_ground_coverage") * int(
        params["floors"]
    )

    priority = (
        HIGH if (max_temp and float(max_temp) >= record_high) or mean_temp >= 30 else MEDIUM
    )
    reason = f"Mean annual temperature is {mean_temp}°C"
    if max_temp:
        # T2M_MAX is the highest temperature on record, not a typical daily high,
        # so it is described as such rather than as a summer average.
        reason += f", with a record high of {max_temp}°C"
    reason += (
        f", and relative humidity averages {humidity}%. "
        if humidity is not None else ". "
    )
    reason += (
        "Humid conditions favour ventilation over evaporative cooling."
        if is_humid else
        "Dry air makes thermal mass and evaporative cooling effective."
    )

    return {
        "recommendation": "Design for passive cooling: " + "; ".join(measures),
        "category": "thermal_comfort",
        "priority": priority,
        "reason": reason,
        "triggering_data": {
            "temperature_c": mean_temp,
            "temperature_max_c": max_temp,
            "humidity_pct": humidity,
        },
        "calculations": {
            "estimated_floor_area_sqm": round(floor_area, 1),
            "required_openable_area_sqm": round(floor_area * openable, 1),
            "openable_area_share_of_floor": openable,
            "formula": "openable_area_m2 = floor_area_m2 * openable_area_share",
        },
        "guideline_basis": [
            bg.citation("thermal", "openable_area_share_of_floor"),
            bg.citation("thermal", "cool_roof_solar_reflectance"),
            bg.citation("thermal", "visible_light_transmittance_min"),
            bg.citation("thermal", "record_high_trigger_c"),
        ],
    }


def _flood_resilience(site: dict, params: dict, skipped: list) -> dict | None:
    flood = site["model_predictions"].get("flood_risk")
    if not flood:
        skipped.append({
            "rule": "Flood resilience",
            "reason": (
                "Flood risk could not be predicted for this site, so no flood-specific "
                "measures are proposed. This is not a finding that the site is safe."
            ),
        })
        return None

    probability = float(flood["flood_probability"])
    level = flood["risk_level"]
    observed = flood.get("observed", {})
    drivers = flood.get("risk_drivers", [])

    if level == "LOW":
        skipped.append({
            "rule": "Flood resilience (elevated-risk measures)",
            "reason": (
                f"Modelled flood probability is {probability:.0%}, in the LOW band. "
                f"Standard drainage design is expected to suffice. Note that the model's "
                f"recall is moderate, so LOW means no evidence of flood exposure rather "
                f"than proof of safety."
            ),
            "triggering_data": {"flood_probability": probability, "risk_level": level},
        })
        return None

    plinth = (
        bg.value("site", "plinth_raise_high_m") if level == "HIGH"
        else bg.value("site", "plinth_raise_moderate_m")
    )
    measures = [
        f"raise the plinth at least {plinth} m above finished ground level",
        "use water-resistant materials and finishes on the ground floor",
        "fit non-return valves on drainage connections to stop backflow",
        "keep electrical distribution boards and service equipment above plinth level",
    ]
    elevation = observed.get("elevation_m")
    if elevation is not None and float(elevation) < 20:
        measures.append(
            "confirm the local flood level with the municipal authority, since low "
            "elevation leaves little drainage head"
        )
    if any(d["driver"] == "local_depression" for d in drivers):
        measures.append(
            "provide on-site detention storage, because this cell sits lower than its "
            "surroundings and water collects here"
        )

    driver_text = "; ".join(d["reason"] for d in drivers[:3]) if drivers else ""
    reason = (
        f"Model 3 puts flood probability at {probability:.0%} ({level} band). "
        f"{driver_text}"
    ).strip()

    return {
        "recommendation": "Build in flood resilience: " + "; ".join(measures),
        "category": "flood_resilience",
        "priority": HIGH if level == "HIGH" else MEDIUM,
        "reason": reason,
        "triggering_data": {
            "flood_probability": probability,
            "risk_level": level,
            "elevation_m": elevation,
            "slope_deg": observed.get("slope_deg"),
            "depression_index_m": observed.get("depression_index_m"),
            "historical_flood_events": observed.get("historical_flood_events"),
        },
        "calculations": {
            "recommended_plinth_raise_m": plinth,
            "basis": f"{level} flood-risk band",
        },
        "guideline_basis": [
            bg.citation("site", "plinth_raise_moderate_m"),
            bg.citation("site", "plinth_raise_high_m"),
        ],
    }


def _green_and_permeable(site: dict, params: dict, skipped: list) -> dict | None:
    plot = float(params["plot_size_sqm"])
    coverage = bg.value("site", "max_ground_coverage")
    footprint = plot * coverage
    open_area = plot - footprint

    flood = site["model_predictions"].get("flood_risk")
    green = site["derived"].get("green_cover", {})

    elevated_flood = bool(flood and flood["risk_level"] in {"HIGH", "MODERATE"})
    share = (
        bg.value("site", "flood_permeable_share_of_open_area") if elevated_flood
        else bg.value("site", "min_permeable_share_of_open_area")
    )
    permeable_area = open_area * share

    reasons = []
    if elevated_flood:
        reasons.append(
            f"flood probability of {float(flood['flood_probability']):.0%} makes on-site "
            f"infiltration important"
        )
        priority = HIGH
    else:
        priority = MEDIUM
    if green.get("classification") == "densely_built":
        reasons.append(
            f"{green['built_fraction'] * 100:.0f}% of the surrounding cell is already "
            f"built up, so on-plot green cover carries more weight"
        )
        priority = HIGH
    elif green.get("classification") in {"moderately_built", "largely_open"}:
        reasons.append(green["reason"].rstrip("."))

    return {
        "recommendation": (
            f"Keep at least {permeable_area:.0f} m2 ({share:.0%} of open area) permeable "
            f"or vegetated, using rain gardens, permeable paving or bioswales"
        ),
        "category": "green_cover",
        "priority": priority,
        "reason": (
            "; ".join(reasons).capitalize() if reasons
            else "Permeable ground reduces runoff and moderates local temperature."
        ),
        "triggering_data": {
            "plot_size_sqm": plot,
            "flood_risk_level": flood["risk_level"] if flood else None,
            "surrounding_built_fraction": green.get("built_fraction"),
        },
        "calculations": {
            "assumed_ground_coverage": coverage,
            "building_footprint_sqm": round(footprint, 1),
            "open_area_sqm": round(open_area, 1),
            "permeable_share_of_open_area": share,
            "minimum_permeable_area_sqm": round(permeable_area, 1),
            "formula": "permeable_m2 = (plot_m2 - plot_m2 * ground_coverage) * permeable_share",
        },
        "guideline_basis": [
            bg.citation("site", "max_ground_coverage"),
            bg.citation("site", "min_permeable_share_of_open_area"),
            bg.citation("site", "flood_permeable_share_of_open_area"),
        ],
    }


def _water_conservation(site: dict, params: dict, skipped: list) -> dict | None:
    occupants = int(params["occupants"])
    lpcd, lpcd_key = _daily_demand_lpcd(params["building_type"])
    baseline_lpd = occupants * lpcd

    fixture_saving = bg.value("water", "low_flow_fixture_saving")
    greywater_share = bg.value("water", "greywater_reuse_share")
    fixture_lpd = baseline_lpd * fixture_saving
    greywater_lpd = baseline_lpd * greywater_share

    water = site["model_predictions"].get("surface_water")
    proximity = site["derived"].get("water_proximity", {})

    reasons = [
        f"{occupants} occupants at the {lpcd} L/person/day benchmark imply about "
        f"{baseline_lpd:,.0f} L/day of demand"
    ]
    priority = MEDIUM
    if proximity.get("classification") in {"dry", "occasional_water"}:
        reasons.append(
            "no dependable surface water sits near this site, so demand falls on "
            "piped supply or groundwater"
        )
        priority = HIGH
    if water and water.get("water_body_status", {}).get("inter_annual_reliability") == "low":
        reasons.append(
            "nearby surface water returns inconsistently between years, so it cannot be "
            "relied on as a dry-season source"
        )
        priority = HIGH

    return {
        "recommendation": (
            "Fit low-flow fixtures (tap aerators, dual-flush cisterns, efficient "
            "showerheads) and plumb a dual system so treated greywater serves flushing "
            "and landscape irrigation"
        ),
        "category": "water",
        "priority": priority,
        "reason": "; ".join(reasons).capitalize() + ".",
        "triggering_data": {
            "occupants": occupants,
            "building_type": params["building_type"],
            "water_proximity": proximity.get("classification"),
        },
        "calculations": {
            "demand_lpcd": lpcd,
            "baseline_demand_litres_per_day": round(baseline_lpd),
            "fixture_saving_litres_per_day": round(fixture_lpd),
            "greywater_reuse_litres_per_day": round(greywater_lpd),
            "combined_reduction_litres_per_day": round(fixture_lpd + greywater_lpd),
            "residual_demand_litres_per_day": round(baseline_lpd - fixture_lpd - greywater_lpd),
            "formula": "saving_L_day = occupants * lpcd * (fixture_saving + greywater_share)",
        },
        "guideline_basis": [
            bg.citation("water", lpcd_key.split(".")[1]),
            bg.citation("water", "low_flow_fixture_saving"),
            bg.citation("water", "greywater_reuse_share"),
        ],
    }


def _water_body_setback(site: dict, params: dict, skipped: list) -> dict | None:
    proximity = site["derived"].get("water_proximity", {})
    if proximity.get("classification") not in {"within_water_body_cell", "adjacent_to_water"}:
        return None

    setback = bg.value("site", "water_body_setback_m")
    return {
        "recommendation": (
            f"Confirm the statutory construction setback from the adjacent water body "
            f"before finalising the site layout; {setback} m is indicative only"
        ),
        "category": "site_planning",
        "priority": HIGH if proximity["classification"] == "within_water_body_cell" else MEDIUM,
        "reason": proximity["reason"],
        "triggering_data": {
            "water_proximity": proximity["classification"],
            "occurrence_pct": proximity.get("occurrence_pct"),
            "water_body_status": proximity.get("water_body_status"),
        },
        "calculations": {
            "indicative_setback_m": setback,
            "note": (
                "Statutory setbacks are set by state wetland, river and coastal "
                "regulation and are frequently larger than this figure."
            ),
        },
        "guideline_basis": [bg.citation("site", "water_body_setback_m")],
    }


def _urban_context(site: dict, params: dict, skipped: list) -> dict | None:
    """Surface what the expansion model says about the surrounding area.

    Advisory context, not a construction measure: a citizen deciding where to build
    should know whether the area is a favoured growth direction or one the model
    marks as unsuitable.
    """
    urban = site["model_predictions"].get("urban_expansion")
    if not urban:
        return None

    label = urban["suitability_class"]
    score = urban["suitability_score"]
    constraints = urban.get("constraints", [])
    constraint_text = "; ".join(c["reason"] for c in constraints[:3])

    if label == "RED":
        recommendation = (
            "Reconsider this location, or expect to carry higher servicing costs: the "
            "expansion model places the area in its least-developed-growth class"
        )
        priority = HIGH
    elif label == "YELLOW":
        recommendation = (
            "Verify water supply, drainage and access provision with the local "
            "authority, since the area shows conditional expansion suitability"
        )
        priority = MEDIUM
    else:
        recommendation = (
            "Expect continued development nearby: plan for future traffic, drainage "
            "load and loss of open ground around the plot"
        )
        priority = LOW

    return {
        "recommendation": recommendation,
        "category": "site_planning",
        "priority": priority,
        "reason": (
            f"Urban expansion suitability for this cell is {label} with a score of "
            f"{score:.2f}. {constraint_text}"
        ).strip(),
        "triggering_data": {
            "suitability_class": label,
            "suitability_score": score,
            "constraints": [c["constraint"] for c in constraints],
        },
        "calculations": {
            "score_definition": urban.get("score_definition"),
            "classification_rule": urban.get("classification_rule"),
        },
        "guideline_basis": [],
    }


_RULES = (
    _rainwater_harvesting,
    _solar,
    _passive_cooling,
    _flood_resilience,
    _green_and_permeable,
    _water_conservation,
    _water_body_setback,
    _urban_context,
)


def generate_recommendations(site: dict, params: dict) -> dict:
    """Run every rule against a site assessment.

    Returns the fired recommendations ordered by priority, the rules that were
    skipped with the reason, and the guideline ruleset that was applied.
    """
    recommendations: list[dict] = []
    skipped: list[dict] = []

    for rule in _RULES:
        try:
            result = rule(site, params, skipped)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("Rule %s failed: %s", rule.__name__, exc)
            skipped.append({
                "rule": rule.__name__,
                "reason": f"Rule could not be evaluated: {exc}",
            })
            continue
        if result:
            recommendations.append(result)

    recommendations.sort(key=lambda r: _PRIORITY_ORDER.get(r["priority"], 9))
    logger.info(
        "Building planner: %d recommendations, %d rules skipped",
        len(recommendations), len(skipped),
    )
    return {
        "recommendations": recommendations,
        "skipped_rules": skipped,
        "priority_counts": {
            level: sum(1 for r in recommendations if r["priority"] == level)
            for level in (HIGH, MEDIUM, LOW)
        },
        "guidelines_applied": bg.export(),
        "disclaimer": bg.DISCLAIMER,
    }
