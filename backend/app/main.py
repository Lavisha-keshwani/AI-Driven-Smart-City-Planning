from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import cities, predictions, recommendations, whatif

app = FastAPI(
    title="SmartCityAI API",
    description="Multi-Agent AI Framework for Sustainable Urban Growth and Water Resource Planning",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cities.router)
app.include_router(predictions.router)
app.include_router(recommendations.router)
app.include_router(whatif.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "SmartCityAI API", "docs": "/docs"}
