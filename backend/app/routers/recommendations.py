from fastapi import APIRouter, HTTPException
from app.data.city_data import CITY_METRICS
from app.schemas.models import Recommendation
from app.services.agent_pipeline import run_agent_pipeline

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/{city_id}", response_model=list[Recommendation])
def get_recommendations(city_id: str):
    if city_id not in CITY_METRICS:
        raise HTTPException(status_code=404, detail=f"Unknown city '{city_id}'")
    return run_agent_pipeline(city_id)
