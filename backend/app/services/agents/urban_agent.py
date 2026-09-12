"""
Urban Planning Agent.

Focus: residential expansion, industrial zones, infrastructure planning.
Consumes: urban_growth stub prediction.
"""


def run(city_name: str, predictions: dict) -> dict:
    growth = predictions["urban_growth"]
    rate = growth["growth_rate_pct"]
    pop_2030 = growth["population_2030_millions"]

    if rate >= 18:
        tone = "alert"
        text = (
            f"{city_name} is projected to grow {rate:.1f}% by 2030, reaching "
            f"{pop_2030}M residents. Planned infrastructure expansion is likely to lag "
            f"population growth at this pace — recommend front-loading water and transit "
            f"infrastructure before approving new peripheral zones."
        )
    elif rate >= 12:
        tone = "caution"
        text = (
            f"Population growth of {rate:.1f}% to {pop_2030}M by 2030 will add real "
            f"pressure on existing infrastructure. New expansion zones should be checked "
            f"against groundwater recharge maps before approval."
        )
    else:
        tone = "neutral"
        text = (
            f"Growth to {pop_2030}M by 2030 ({rate:.1f}%) is manageable at current "
            f"infrastructure investment levels."
        )

    return {"agent": "Urban Planner", "tone": tone, "text": text}
