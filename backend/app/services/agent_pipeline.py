"""
Runs the full agent pipeline for a city: each stakeholder agent reasons over
the stub model predictions, then the coordinator balances their outputs.
"""

from app.services.models.stub_models import get_all_predictions
from app.services.agents import (
    water_agent,
    urban_agent,
    environment_agent,
    industry_agent,
    citizen_agent,
    coordinator_agent,
)
from app.data.city_data import CITIES

_CITY_NAMES = {c["id"]: c["name"] for c in CITIES}


def run_agent_pipeline(city_id: str) -> list[dict]:
    city_name = _CITY_NAMES[city_id]
    predictions = get_all_predictions(city_id)

    outputs = [
        water_agent.run(city_name, predictions),
        urban_agent.run(city_name, predictions),
        environment_agent.run(city_name, predictions),
        industry_agent.run(city_name, predictions),
        citizen_agent.run(city_name, predictions),
    ]
    outputs.append(coordinator_agent.run(city_name, outputs))
    return outputs
