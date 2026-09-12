from fastapi import APIRouter
from app.data.city_data import CITIES
from app.schemas.models import City

router = APIRouter(prefix="/api/cities", tags=["cities"])


@router.get("", response_model=list[City])
def list_cities():
    return CITIES
