"""
Building guideline parameters, kept in one transparent, configurable place.

Every number the Sustainable Building Planner uses is declared here with its
source, so a reviewer can check each rule against the document it came from and
change it without touching rule logic.

IMPORTANT — regulatory status.
Two kinds of entry live in this file, and they are labelled distinctly:

  `origin: "guideline"`
      A published reference figure (BEE Eco-Niwas Samhita, CPHEEO, NBC, MNRE).
      The planner cites these as design references. It does NOT verify compliance
      with them: Eco-Niwas Samhita compliance depends on envelope U-values, window
      assembly specifications and climate-zone-specific RETV calculations that
      require actual architectural drawings, none of which this tool has.

  `origin: "project_assumption"`
      A modelling assumption this project adopts to make an estimate possible
      (for example, what share of a plot becomes roof). These are not regulatory
      requirements and are not presented as such.

Nothing here should be read as a statement that a design satisfies any code.
Local municipal by-laws and the state building regulations always govern.
"""

from __future__ import annotations

# ── Sources cited by the rules ───────────────────────────────────────────────
SOURCES = {
    "eco_niwas_samhita": {
        "title": "Eco-Niwas Samhita (Energy Conservation Building Code - Residential)",
        "publisher": "Bureau of Energy Efficiency (BEE), Government of India",
        "scope": (
            "Residential envelope performance: Residential Envelope Transmittance "
            "Value (RETV), thermal transmittance, window-to-wall ratio and openable "
            "area for ventilation."
        ),
        "url": "https://beeindia.gov.in/",
    },
    "cpheeo": {
        "title": "CPHEEO Manual on Water Supply and Treatment",
        "publisher": "Central Public Health and Environmental Engineering Organisation",
        "scope": "Domestic water demand benchmarks (litres per capita per day).",
    },
    "nbc_2016": {
        "title": "National Building Code of India 2016",
        "publisher": "Bureau of Indian Standards",
        "scope": "Rainwater harvesting provisions, plot coverage, plinth level guidance.",
    },
    "mnre": {
        "title": "MNRE rooftop solar programme guidance",
        "publisher": "Ministry of New and Renewable Energy",
        "scope": "Rooftop area per kW of installed photovoltaic capacity.",
    },
}


def _rule(value, unit, origin, source_key, note):
    return {
        "value": value,
        "unit": unit,
        "origin": origin,
        "source": source_key,
        "note": note,
    }


# ── Water ────────────────────────────────────────────────────────────────────
WATER = {
    "domestic_demand_lpcd": _rule(
        135, "litres/person/day", "guideline", "cpheeo",
        "CPHEEO benchmark for domestic supply in towns with piped water and sewerage.",
    ),
    "office_demand_lpcd": _rule(
        45, "litres/person/day", "guideline", "cpheeo",
        "CPHEEO benchmark for office occupancy without residential use.",
    ),
    "low_flow_fixture_saving": _rule(
        0.30, "fraction", "guideline", "cpheeo",
        "Typical demand reduction from aerators, dual-flush cisterns and efficient "
        "showerheads. Treated as a planning estimate, not a guaranteed saving.",
    ),
    "greywater_reuse_share": _rule(
        0.25, "fraction", "project_assumption", "cpheeo",
        "Share of domestic demand that can be met by treated greywater for flushing "
        "and landscape irrigation.",
    ),
}

# ── Rainwater harvesting ─────────────────────────────────────────────────────
RAINWATER = {
    "roof_runoff_coefficient": _rule(
        0.85, "fraction", "guideline", "nbc_2016",
        "Runoff coefficient for an impervious terrace roof after first-flush and "
        "evaporation losses.",
    ),
    "roof_share_of_plot": _rule(
        0.55, "fraction", "project_assumption", "nbc_2016",
        "Assumed catchment roof area as a share of plot area, reflecting typical "
        "ground coverage limits. Overridden when the caller supplies a roof area.",
    ),
    "storage_days_of_demand": _rule(
        20, "days", "project_assumption", "nbc_2016",
        "Storage sized to carry roughly three weeks of demand, the usual compromise "
        "between dry-spell cover and tank cost.",
    ),
    "min_viable_annual_rainfall_mm": _rule(
        400, "mm/year", "project_assumption", "nbc_2016",
        "Below this annual rainfall, roof catchment yield rarely justifies the "
        "system cost on a single plot.",
    ),
    "mandatory_plot_area_sqm": _rule(
        100, "m^2", "guideline", "nbc_2016",
        "Many Indian municipal by-laws require rainwater harvesting above roughly "
        "this plot size. The exact trigger is set locally and must be checked.",
    ),
}

# ── Solar ────────────────────────────────────────────────────────────────────
SOLAR = {
    "area_per_kw_sqm": _rule(
        10, "m^2/kW", "guideline", "mnre",
        "Rooftop area per kW of installed capacity, including access and "
        "inter-row shading clearance.",
    ),
    "performance_ratio": _rule(
        0.75, "fraction", "guideline", "mnre",
        "System performance ratio covering inverter, temperature, soiling and "
        "wiring losses.",
    ),
    "usable_roof_share": _rule(
        0.60, "fraction", "project_assumption", "mnre",
        "Share of roof available for panels after water tanks, stairwells, services "
        "and setbacks.",
    ),
    "min_viable_irradiance": _rule(
        3.5, "kWh/m^2/day", "project_assumption", "mnre",
        "Below this irradiance a rooftop system is usually not economic.",
    ),
    "good_irradiance": _rule(
        4.5, "kWh/m^2/day", "project_assumption", "mnre",
        "Irradiance above which rooftop solar is clearly worthwhile.",
    ),
    "excellent_irradiance": _rule(
        5.5, "kWh/m^2/day", "project_assumption", "mnre",
        "Irradiance at which rooftop solar is strongly recommended.",
    ),
    "residential_kwh_per_person_month": _rule(
        75, "kWh/person/month", "project_assumption", "mnre",
        "Indicative household electricity use per occupant, used to size a system "
        "against demand rather than only against available roof area.",
    ),
    "office_kwh_per_sqm_month": _rule(
        7, "kWh/m^2/month", "project_assumption", "mnre",
        "Indicative office electricity intensity per unit of floor area.",
    ),
    "demand_headroom": _rule(
        1.2, "factor", "project_assumption", "mnre",
        "Allowance above present demand so a system is not undersized by future load "
        "growth. Capacity is recommended at the smaller of the roof-limited and "
        "demand-matched figures.",
    ),
}

# ── Envelope and thermal comfort ─────────────────────────────────────────────
THERMAL = {
    "openable_area_share_of_floor": _rule(
        0.125, "fraction", "guideline", "eco_niwas_samhita",
        "Eco-Niwas Samhita requires openable window area of at least 12.5% of floor "
        "area for natural ventilation in naturally ventilated dwellings.",
    ),
    "visible_light_transmittance_min": _rule(
        0.27, "fraction", "guideline", "eco_niwas_samhita",
        "Minimum visible light transmittance for non-opaque envelope components, so "
        "daylight is not traded away for solar control.",
    ),
    "passive_cooling_trigger_c": _rule(
        28, "degC", "project_assumption", "eco_niwas_samhita",
        "Mean annual temperature above which passive cooling measures become a "
        "priority rather than an option.",
    ),
    "record_high_trigger_c": _rule(
        40, "degC", "project_assumption", "eco_niwas_samhita",
        "Record high temperature above which envelope insulation and shading should "
        "be treated as essential. NASA POWER climatology reports T2M_MAX as the "
        "highest temperature observed, not a typical daily maximum, so this "
        "threshold is set against that extreme rather than an average.",
    ),
    "high_humidity_trigger_pct": _rule(
        65, "%", "project_assumption", "eco_niwas_samhita",
        "Relative humidity above which cross-ventilation outperforms evaporative "
        "cooling strategies.",
    ),
    "cool_roof_solar_reflectance": _rule(
        0.70, "fraction", "guideline", "eco_niwas_samhita",
        "Solar reflectance target for cool-roof surface finishes.",
    ),
}

# ── Site, green cover and flood resilience ───────────────────────────────────
SITE = {
    "max_ground_coverage": _rule(
        0.55, "fraction", "project_assumption", "nbc_2016",
        "Assumed ground coverage limit. Actual permissible coverage and FAR are set "
        "by the local development control regulations.",
    ),
    "min_permeable_share_of_open_area": _rule(
        0.30, "fraction", "project_assumption", "nbc_2016",
        "Baseline share of open area kept permeable so rainfall can infiltrate.",
    ),
    "flood_permeable_share_of_open_area": _rule(
        0.60, "fraction", "project_assumption", "nbc_2016",
        "Raised permeable share where flood probability is elevated.",
    ),
    "plinth_raise_moderate_m": _rule(
        0.45, "m", "guideline", "nbc_2016",
        "Plinth height above finished ground level where flood risk is moderate.",
    ),
    "plinth_raise_high_m": _rule(
        0.75, "m", "guideline", "nbc_2016",
        "Plinth height above finished ground level where flood risk is high. Local "
        "flood-level records override this figure.",
    ),
    "water_body_setback_m": _rule(
        30, "m", "guideline", "nbc_2016",
        "Indicative construction setback from a water body. Statutory setbacks are "
        "set by state wetland and coastal regulation and are frequently larger.",
    ),
}

ALL_GROUPS = {
    "water": WATER,
    "rainwater": RAINWATER,
    "solar": SOLAR,
    "thermal": THERMAL,
    "site": SITE,
}

DISCLAIMER = (
    "This is an advisory sustainability planning tool, not a certified structural "
    "engineering design or construction blueprint. Figures are planning-stage "
    "estimates. Guideline references are cited as design references only: this tool "
    "does not verify compliance with the Eco-Niwas Samhita, the National Building "
    "Code, or any local by-law. Engage a licensed structural engineer and architect, "
    "and confirm all requirements with your local authority, before construction."
)


def value(group: str, key: str):
    """The numeric value of one guideline parameter."""
    return ALL_GROUPS[group][key]["value"]


def citation(group: str, key: str) -> dict:
    """A guideline parameter with its provenance, for embedding in a response."""
    rule = ALL_GROUPS[group][key]
    source = SOURCES.get(rule["source"], {})
    return {
        "parameter": f"{group}.{key}",
        "value": rule["value"],
        "unit": rule["unit"],
        "origin": rule["origin"],
        "note": rule["note"],
        "source_title": source.get("title"),
        "source_publisher": source.get("publisher"),
    }


def export() -> dict:
    """The full ruleset, so the API can expose exactly what the planner applied."""
    return {
        "sources": SOURCES,
        "parameters": ALL_GROUPS,
        "disclaimer": DISCLAIMER,
        "regulatory_status": (
            "Entries marked origin='guideline' cite a published reference. Entries "
            "marked origin='project_assumption' are modelling assumptions adopted by "
            "this project and carry no regulatory weight. Compliance is not verified."
        ),
    }
