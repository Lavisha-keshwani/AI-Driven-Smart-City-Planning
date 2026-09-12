"""
Stub prediction functions — placeholders for the 5 trained models described
in the project spec (urban_growth.pkl, water_demand.pkl, groundwater.pkl,
surface_water.pkl, climate.pkl).

Each function's signature and return shape is what the real model will
eventually produce. Right now they just read the seeded values in
app/data/city_data.py. To wire in a real model later:

    1. Load it once at import time: MODEL = joblib.load("models/urban_growth.pkl")
    2. Replace the function body with MODEL.predict(features_for(city_id))
    3. Nothing outside this file needs to change — agents and routers only
       ever call these functions, never touch CITY_METRICS directly.
"""

from app.data.city_data import CITY_METRICS


def urban_growth_prediction(city_id: str) -> dict:
    """Model 1 — future residential/industrial expansion. Stubbed via population trend."""
    m = CITY_METRICS[city_id]
    growth_rate = (m["population"]["projected2030"] - m["population"]["current"]) / m["population"]["current"]
    return {
        "population_current_millions": m["population"]["current"],
        "population_2030_millions": m["population"]["projected2030"],
        "growth_rate_pct": round(growth_rate * 100, 1),
    }


def water_demand_forecast(city_id: str) -> dict:
    """Model 2 — LSTM/GRU/Prophet stand-in. Returns the seeded time series."""
    m = CITY_METRICS[city_id]
    latest = m["waterDemand"][-1]
    return {
        "series": m["waterDemand"],
        "latest_total_mld": latest["residential"] + latest["industrial"],
    }


def groundwater_prediction(city_id: str) -> dict:
    """Model 3 — groundwater depletion / GRACE-anomaly stand-in."""
    m = CITY_METRICS[city_id]
    series = m["groundwater"]
    trend_per_year = (series[-1]["level"] - series[0]["level"]) / (len(series) - 1)
    return {
        "series": series,
        "latest_anomaly_cm": series[-1]["level"],
        "trend_cm_per_year": round(trend_per_year, 1),
        "risk_zones": m["riskZones"],
    }


def surface_water_monitoring(city_id: str) -> dict:
    """Model 4 — U-Net/SegFormer lake extraction stand-in."""
    m = CITY_METRICS[city_id]
    series = m["lakeArea"]
    pct_change = (series[-1]["sqkm"] - series[0]["sqkm"]) / series[0]["sqkm"] * 100
    return {
        "series": series,
        "latest_sqkm": series[-1]["sqkm"],
        "pct_change_since_2020": round(pct_change, 1),
    }


def climate_flood_risk_assessment(city_id: str) -> dict:
    """Model 5 — flood/drought risk stand-in."""
    m = CITY_METRICS[city_id]
    return {
        "flood_risk": m["floodRisk"],
        "drought_risk": m["droughtRisk"],
    }


def get_all_predictions(city_id: str) -> dict:
    """Convenience aggregator — what the agents consume."""
    return {
        "urban_growth": urban_growth_prediction(city_id),
        "water_demand": water_demand_forecast(city_id),
        "groundwater": groundwater_prediction(city_id),
        "surface_water": surface_water_monitoring(city_id),
        "climate_risk": climate_flood_risk_assessment(city_id),
    }
