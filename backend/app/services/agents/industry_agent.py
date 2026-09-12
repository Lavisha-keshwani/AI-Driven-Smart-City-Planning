"""
Industry Agent.

Focus: industrial development, economic growth.
Consumes: water_demand series (industrial component).
"""


def run(city_name: str, predictions: dict) -> dict:
    series = predictions["water_demand"]["series"]
    first, last = series[0]["industrial"], series[-1]["industrial"]
    industrial_growth_pct = (last - first) / first * 100

    if industrial_growth_pct >= 30:
        tone = "caution"
        text = (
            f"Industrial water demand in {city_name} has grown {industrial_growth_pct:.0f}% "
            f"since 2020 ({last} MLD now). Further industrial expansion should be "
            f"conditional on mandated water recycling, not just approved on economic merit."
        )
    else:
        tone = "neutral"
        text = (
            f"Industrial demand growth ({industrial_growth_pct:.0f}% since 2020, {last} MLD) "
            f"is within a range existing supply infrastructure can support."
        )

    return {"agent": "Industry", "tone": tone, "text": text}
