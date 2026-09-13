"""
NASA POWER service.

Retrieves solar irradiance and meteorology for a point from the NASA POWER API.
The endpoints used need no API key.

Two access patterns:

  `get_nasa_power_data(lat, lon, start_date, end_date)`
      Daily series for an explicit date range — the general-purpose entry point.

  `get_climatology(lat, lon)`
      Long-term monthly climatology, which is what the Building Planner wants: a
      building is designed against typical conditions, not one particular year.

Behaviour on failure is deliberate: this module raises `UpstreamServiceError` and
never substitutes plausible-looking regional averages. A building recommendation
derived from invented rainfall would be worse than no recommendation, so the
planner surfaces the outage instead.

Responses are cached on a coarsened coordinate grid, so nearby lookups and repeat
requests do not hit the API again.
"""

from __future__ import annotations

import datetime as dt
import logging
from functools import lru_cache

import httpx

from app.core import config
from app.core.errors import InvalidInputError, UpstreamServiceError
from app.core.grid import validate_coordinates

logger = logging.getLogger(__name__)

# Parameters requested from NASA POWER:
#   ALLSKY_SFC_SW_DWN  all-sky surface shortwave downward irradiance (kWh/m^2/day)
#   T2M                temperature at 2 m (deg C)
#   T2M_MAX / T2M_MIN  daily temperature extremes (deg C)
#   PRECTOTCORR        bias-corrected precipitation (mm/day)
#   RH2M               relative humidity at 2 m (%)
#   WS2M               wind speed at 2 m (m/s)
PARAMETERS = [
    "ALLSKY_SFC_SW_DWN",
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "RH2M",
    "WS2M",
]

PARAMETER_UNITS = {
    "ALLSKY_SFC_SW_DWN": "kWh/m^2/day",
    "T2M": "degC",
    "T2M_MAX": "degC",
    "T2M_MIN": "degC",
    "PRECTOTCORR": "mm/day",
    "RH2M": "%",
    "WS2M": "m/s",
}

# NASA POWER uses -999 as its missing-data sentinel.
_FILL_VALUE = -999.0
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_CACHE_GRID_DEG = 0.5


def _snap(value: float) -> float:
    """Coarsen a coordinate onto the cache grid.

    NASA POWER itself serves a ~0.5 degree reanalysis grid, so neighbouring
    requests would return the same cell anyway; snapping makes that explicit and
    keeps the cache effective.
    """
    return round(round(value / _CACHE_GRID_DEG) * _CACHE_GRID_DEG, 4)


def _is_missing(value) -> bool:
    return value is None or float(value) <= _FILL_VALUE + 1


def _request(url: str, params: dict, *, context: str) -> dict:
    """Perform one NASA POWER request, translating every failure mode."""
    try:
        with httpx.Client(timeout=config.NASA_POWER_TIMEOUT) as client:
            response = client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise UpstreamServiceError(
            "NASA POWER did not respond in time. Unable to retrieve meteorological data.",
            detail={"service": "NASA POWER", "context": context,
                    "timeout_seconds": config.NASA_POWER_TIMEOUT},
        ) from exc
    except httpx.RequestError as exc:
        raise UpstreamServiceError(
            "NASA POWER could not be reached. Unable to retrieve meteorological data.",
            detail={"service": "NASA POWER", "context": context, "reason": str(exc)},
        ) from exc

    if response.status_code == 429:
        raise UpstreamServiceError(
            "NASA POWER is rate-limiting requests. Please retry in a few minutes.",
            detail={"service": "NASA POWER", "context": context, "status": 429},
        )
    if response.status_code == 422:
        raise InvalidInputError(
            "NASA POWER rejected the request parameters, usually because the "
            "coordinates or date range are outside its coverage.",
            detail={"service": "NASA POWER", "context": context,
                    "response": response.text[:400]},
        )
    if response.status_code >= 400:
        raise UpstreamServiceError(
            f"NASA POWER returned HTTP {response.status_code}. Unable to retrieve "
            f"meteorological data.",
            detail={"service": "NASA POWER", "context": context,
                    "status": response.status_code},
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamServiceError(
            "NASA POWER returned a response that could not be parsed as JSON.",
            detail={"service": "NASA POWER", "context": context},
        ) from exc

    if "properties" not in payload or "parameter" not in payload.get("properties", {}):
        raise UpstreamServiceError(
            "NASA POWER returned no parameter data for this location.",
            detail={"service": "NASA POWER", "context": context,
                    "messages": payload.get("messages")},
        )
    return payload


@lru_cache(maxsize=config.NASA_POWER_CACHE_SIZE)
def _fetch_daily(lat: float, lon: float, start: str, end: str) -> dict:
    return _request(
        config.NASA_POWER_DAILY_URL,
        {
            "parameters": ",".join(PARAMETERS),
            "community": "RE",
            "latitude": lat,
            "longitude": lon,
            "start": start,
            "end": end,
            "format": "JSON",
        },
        context=f"daily {start}..{end}",
    )


@lru_cache(maxsize=config.NASA_POWER_CACHE_SIZE)
def _fetch_climatology(lat: float, lon: float) -> dict:
    return _request(
        config.NASA_POWER_CLIMATOLOGY_URL,
        {
            "parameters": ",".join(PARAMETERS),
            "community": "RE",
            "latitude": lat,
            "longitude": lon,
            "format": "JSON",
        },
        context="climatology",
    )


def _parse_date(value: str | dt.date, name: str) -> dt.date:
    if isinstance(value, dt.date):
        return value
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    raise InvalidInputError(
        f"{name} must be a date formatted YYYY-MM-DD.", detail={name: str(value)}
    )


def get_nasa_power_data(
    latitude: float,
    longitude: float,
    start_date: str | dt.date,
    end_date: str | dt.date,
) -> dict:
    """Daily NASA POWER series for a point over a date range.

    Returns per-parameter daily values keyed by YYYYMMDD, plus a summary carrying
    each parameter's mean over the period and the total precipitation. Missing days
    (NASA POWER fill value -999) are dropped rather than treated as zero, and the
    count of usable days is reported so the caller can judge coverage.
    """
    validate_coordinates(latitude, longitude)
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    if end < start:
        raise InvalidInputError(
            "end_date must not precede start_date.",
            detail={"start_date": str(start), "end_date": str(end)},
        )
    if end > dt.date.today():
        raise InvalidInputError(
            "end_date is in the future; NASA POWER only serves observed data.",
            detail={"end_date": str(end), "today": str(dt.date.today())},
        )

    payload = _fetch_daily(
        _snap(latitude), _snap(longitude), start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    )
    raw = payload["properties"]["parameter"]

    series: dict[str, dict[str, float]] = {}
    summary: dict[str, float | None] = {}
    for parameter in PARAMETERS:
        values = raw.get(parameter, {})
        clean = {day: float(v) for day, v in values.items() if not _is_missing(v)}
        series[parameter] = clean
        summary[f"{parameter}_mean"] = (
            round(sum(clean.values()) / len(clean), 3) if clean else None
        )

    rainfall = series.get("PRECTOTCORR", {})
    summary["PRECTOTCORR_total_mm"] = round(sum(rainfall.values()), 2) if rainfall else None

    days_requested = (end - start).days + 1
    days_available = len(rainfall) or max((len(v) for v in series.values()), default=0)
    if days_available == 0:
        raise UpstreamServiceError(
            "NASA POWER returned no usable daily values for this location and period.",
            detail={"service": "NASA POWER", "latitude": latitude, "longitude": longitude,
                    "start_date": str(start), "end_date": str(end)},
        )

    logger.info(
        "NASA POWER daily (%.2f, %.2f) %s..%s: %d/%d days usable",
        latitude, longitude, start, end, days_available, days_requested,
    )
    return {
        "source": "NASA POWER",
        "endpoint": "temporal/daily/point",
        "requested": {
            "latitude": latitude, "longitude": longitude,
            "start_date": str(start), "end_date": str(end),
        },
        "resolved_grid_point": {"latitude": _snap(latitude), "longitude": _snap(longitude)},
        "units": PARAMETER_UNITS,
        "daily": series,
        "summary": summary,
        "coverage": {
            "days_requested": days_requested,
            "days_available": days_available,
            "complete": days_available >= days_requested,
        },
    }


def get_climatology(latitude: float, longitude: float) -> dict:
    """Long-term monthly climatology for a point.

    Annual figures come from NASA POWER's own ANN aggregate where present. Annual
    rainfall is computed as the sum of monthly totals, converting each month's
    mm/day rate by that month's real length — never by a flat 30 or 365 factor.
    """
    validate_coordinates(latitude, longitude)
    payload = _fetch_climatology(_snap(latitude), _snap(longitude))
    raw = payload["properties"]["parameter"]

    monthly: dict[str, dict[str, float]] = {}
    annual: dict[str, float | None] = {}
    for parameter in PARAMETERS:
        values = raw.get(parameter, {})
        monthly[parameter] = {
            month: round(float(values[month]), 3)
            for month in _MONTHS
            if month in values and not _is_missing(values[month])
        }
        ann = values.get("ANN")
        if not _is_missing(ann):
            annual[parameter] = round(float(ann), 3)
        elif monthly[parameter]:
            annual[parameter] = round(
                sum(monthly[parameter].values()) / len(monthly[parameter]), 3
            )
        else:
            annual[parameter] = None

    # Monthly precipitation is a mm/day rate; weight each month by its own length.
    days_in_month = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    rain_monthly = monthly.get("PRECTOTCORR", {})
    monthly_rain_mm = {
        month: round(rain_monthly[month] * days, 2)
        for month, days in zip(_MONTHS, days_in_month)
        if month in rain_monthly
    }
    rainfall_annual_mm = round(sum(monthly_rain_mm.values()), 1) if monthly_rain_mm else None

    if annual.get("ALLSKY_SFC_SW_DWN") is None or rainfall_annual_mm is None:
        raise UpstreamServiceError(
            "NASA POWER returned climatology without usable solar or precipitation "
            "values for this location.",
            detail={"service": "NASA POWER", "latitude": latitude, "longitude": longitude},
        )

    wettest = max(monthly_rain_mm, key=monthly_rain_mm.get) if monthly_rain_mm else None
    logger.info(
        "NASA POWER climatology (%.2f, %.2f): solar=%.2f kWh/m2/day rainfall=%.0f mm/yr",
        latitude, longitude, annual["ALLSKY_SFC_SW_DWN"], rainfall_annual_mm,
    )

    return {
        "source": "NASA POWER",
        "endpoint": "temporal/climatology/point",
        "requested": {"latitude": latitude, "longitude": longitude},
        "resolved_grid_point": {"latitude": _snap(latitude), "longitude": _snap(longitude)},
        "units": PARAMETER_UNITS,
        "solar_kwh_m2_day": annual["ALLSKY_SFC_SW_DWN"],
        "temperature_c": annual.get("T2M"),
        "temperature_max_c": annual.get("T2M_MAX"),
        "temperature_min_c": annual.get("T2M_MIN"),
        "humidity_pct": annual.get("RH2M"),
        "wind_speed_m_s": annual.get("WS2M"),
        "rainfall_annual_mm": rainfall_annual_mm,
        "monthly_rainfall_mm": monthly_rain_mm,
        "monthly_solar_kwh_m2_day": monthly.get("ALLSKY_SFC_SW_DWN", {}),
        "monthly_temperature_c": monthly.get("T2M", {}),
        "monthly_humidity_pct": monthly.get("RH2M", {}),
        "wettest_month": wettest,
        "monsoon_concentration": (
            round(
                sum(monthly_rain_mm.get(m, 0) for m in ("JUN", "JUL", "AUG", "SEP"))
                / rainfall_annual_mm, 3
            )
            if rainfall_annual_mm else None
        ),
    }


def cache_info() -> dict:
    """Cache statistics, for the models/status endpoint."""
    return {
        "daily": _fetch_daily.cache_info()._asdict(),
        "climatology": _fetch_climatology.cache_info()._asdict(),
        "cache_grid_degrees": _CACHE_GRID_DEG,
    }
