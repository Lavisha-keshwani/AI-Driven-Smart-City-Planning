"""
Environment Agent.

Focus: green cover, wetlands, lakes, biodiversity.
Consumes: surface_water stub prediction.
"""


def run(city_name: str, predictions: dict) -> dict:
    sw = predictions["surface_water"]
    pct_change = sw["pct_change_since_2020"]
    latest = sw["latest_sqkm"]

    if pct_change <= -30:
        tone = "alert"
        text = (
            f"Lake and wetland area in {city_name} has shrunk {abs(pct_change):.0f}% "
            f"since 2020, down to {latest} km². This is beyond natural seasonal "
            f"variation — encroachment is the likely driver. Recommend an immediate "
            f"survey and a hard no-build buffer around remaining water bodies."
        )
    elif pct_change <= -15:
        tone = "caution"
        text = (
            f"Surface water extent has declined {abs(pct_change):.0f}% since 2020 "
            f"({latest} km² remaining). Recommend a protective buffer zone before any "
            f"nearby development is approved."
        )
    else:
        tone = "neutral"
        text = (
            f"Surface water extent ({latest} km²) has held relatively steady since 2020 "
            f"({pct_change:+.0f}%)."
        )

    return {"agent": "Environment", "tone": tone, "text": text}
