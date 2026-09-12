from fastapi import APIRouter, HTTPException
from app.data.city_data import CITY_METRICS
from app.schemas.models import ScenarioInput, ScenarioResult
from app.services.optimizer import evaluate_scenario

router = APIRouter(prefix="/api/whatif", tags=["whatif"])


@router.post("/{city_id}", response_model=ScenarioResult)
def run_whatif(city_id: str, scenario: ScenarioInput):
    if city_id not in CITY_METRICS:
        raise HTTPException(status_code=404, detail=f"Unknown city '{city_id}'")
    result = evaluate_scenario(city_id, scenario.model_dump(by_alias=True))
    return result
