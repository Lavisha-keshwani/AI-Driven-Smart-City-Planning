"""
Water Authority Agent.

Focus: water allocation, reservoir management, groundwater conservation.
Consumes: water_demand + groundwater stub predictions.

This is intentionally rule-based right now — thresholds on the stub model
outputs. Once the real groundwater/demand models are trained, swap the
inputs (predictions dict) for real ones; the reasoning below doesn't change.
"""


def run(city_name: str, predictions: dict) -> dict:
    gw = predictions["groundwater"]
    demand = predictions["water_demand"]

    trend = gw["trend_cm_per_year"]
    anomaly = gw["latest_anomaly_cm"]
    total_demand = demand["latest_total_mld"]

    if trend <= -8:
        tone = "alert"
        text = (
            f"Groundwater in {city_name} is declining at {abs(trend):.1f}cm/year "
            f"(currently {anomaly}cm anomaly). At this rate, recharge cannot keep pace "
            f"with extraction — recommend an immediate freeze on new borewell permits "
            f"and mandatory rainwater harvesting for any new construction."
        )
    elif trend <= -4:
        tone = "caution"
        text = (
            f"Groundwater is falling at {abs(trend):.1f}cm/year ({anomaly}cm anomaly). "
            f"Current total demand is {total_demand} MLD. Recommend rainwater harvesting "
            f"mandates before approving further residential permits in low-recharge zones."
        )
    else:
        tone = "neutral"
        text = (
            f"Groundwater trend is comparatively stable ({trend:+.1f}cm/year), though "
            f"total demand of {total_demand} MLD should be monitored as population grows."
        )

    return {"agent": "Water Authority", "tone": tone, "text": text}
