"""
Multi-Objective Optimization Engine — stub.

The project spec calls for NSGA-II / MOEA here, optimizing water allocation,
industrial siting, green corridors, land use, and reservoir management
jointly. That needs trained models feeding it real objective functions, so
for now this applies transparent multipliers to the latest known metrics,
exactly mirroring the frontend's mock projection math (see
frontend/src/api/client.js -> runWhatIfScenario) so behavior is identical
whether USE_MOCK is true or false on the frontend.

Swap-in plan: once models/*.pkl exist, replace evaluate_scenario's body with
a call into pymoo's NSGA-II, using the trained models as objective functions
instead of these fixed multipliers.
"""

from app.data.city_data import CITY_METRICS


def evaluate_scenario(city_id: str, scenario: dict) -> dict:
    base = CITY_METRICS[city_id]
    latest_demand = base["waterDemand"][-1]
    latest_groundwater = base["groundwater"][-1]["level"]

    demand_multiplier = 1 + scenario["populationGrowth"] / 100
    green_reduction = scenario["greenCoverIncrease"] / 100
    harvesting_offset = 0.15 if scenario["rainwaterHarvesting"] else 0
    industry_bump = 1.2 if scenario["newIndustry"] else 1.0

    projected_demand = round(
        (latest_demand["residential"] * demand_multiplier + latest_demand["industrial"] * industry_bump)
        * (1 - harvesting_offset)
    )

    projected_groundwater_change = round(
        latest_groundwater * demand_multiplier * (1 - harvesting_offset - green_reduction * 0.3)
    )

    score_delta = round(
        green_reduction * 20
        + harvesting_offset * 30
        - (demand_multiplier - 1) * 25
        - (industry_bump - 1) * 15
    )

    return {
        "projectedWaterDemand": projected_demand,
        "projectedGroundwaterChange": projected_groundwater_change,
        "sustainabilityScoreDelta": score_delta,
    }
