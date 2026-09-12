from fastapi import APIRouter, HTTPException
from app.data.city_data import CITY_METRICS
from app.schemas.models import CityMetrics

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/{city_id}", response_model=CityMetrics)
def get_predictions(city_id: str):
    if city_id not in CITY_METRICS:
        raise HTTPException(status_code=404, detail=f"Unknown city '{city_id}'")
    return CITY_METRICS[city_id]
