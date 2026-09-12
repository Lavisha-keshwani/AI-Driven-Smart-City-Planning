"""
Response/request models. Field names are camelCase (via alias) to match
frontend/src/data/mockData.js and client.js exactly, so the frontend needs
zero changes when USE_MOCK flips to false.
"""

from pydantic import BaseModel, ConfigDict, Field


def to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class City(CamelModel):
    id: str
    name: str
    state: str
    lat: float
    lon: float


class Population(CamelModel):
    current: float
    projected2030: float = Field(alias="projected2030")
    unit: str


class WaterDemandPoint(BaseModel):
    year: int
    residential: float
    industrial: float


class GroundwaterPoint(BaseModel):
    year: int
    level: float


class LakeAreaPoint(BaseModel):
    year: int
    sqkm: float


class CityMetrics(CamelModel):
    sustainability_score: int
    population: Population
    water_demand: list[WaterDemandPoint]
    groundwater: list[GroundwaterPoint]
    lake_area: list[LakeAreaPoint]
    flood_risk: str
    drought_risk: str
    risk_zones: int


class Recommendation(BaseModel):
    agent: str
    tone: str
    text: str


class ScenarioInput(CamelModel):
    new_industry: bool = False
    population_growth: float = 15
    rainwater_harvesting: bool = False
    green_cover_increase: float = 10


class ScenarioResult(CamelModel):
    projected_water_demand: float
    projected_groundwater_change: float
    sustainability_score_delta: float
