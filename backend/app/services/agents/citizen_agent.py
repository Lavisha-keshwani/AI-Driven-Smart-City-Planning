"""
Citizen Agent.

Focus: water availability, public welfare, living conditions.
Consumes: groundwater risk_zones + water_demand total.
"""


def run(city_name: str, predictions: dict) -> dict:
    risk_zones = predictions["groundwater"]["risk_zones"]
    total_demand = predictions["water_demand"]["latest_total_mld"]

    if risk_zones >= 15:
        tone = "alert"
        text = (
            f"{risk_zones} zones in {city_name} are already classified as high-risk for "
            f"supply shortfall, against total demand of {total_demand} MLD. This warrants "
            f"an emergency water-security review before any further expansion is approved."
        )
    elif risk_zones >= 8:
        tone = "caution"
        text = (
            f"{risk_zones} zones currently show elevated shortfall risk. Supply reliability "
            f"is holding for most residents but that margin is narrowing as demand "
            f"({total_demand} MLD) climbs."
        )
    else:
        tone = "positive"
        text = (
            f"Supply reliability remains solid across most of {city_name}, with only "
            f"{risk_zones} zones flagged for elevated risk."
        )

    return {"agent": "Citizen Welfare", "tone": tone, "text": text}
