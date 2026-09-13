"""
SmartCityAI — FastAPI application entry point.

Multi-Agent AI Framework for Sustainable Urban Growth and Water Resource Planning.

Architecture:

    React  ->  FastAPI  ->  Models 1/2/3 + Building Planner rules
                              |
                              v
                          LangGraph  ->  Groq LLM
                              |
                              v
                         Coordinator  ->  final explainable recommendation

The models predict, the rules calculate, LangGraph orchestrates, the LLM interprets,
and the Coordinator synthesises. No layer substitutes for another.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents import llm
from app.core.config import CORS_ORIGINS
from app.core.errors import (
    SmartCityError,
    smartcity_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging_config import RequestIdMiddleware, configure_logging
from app.routers import agents, building, flood, microplastics, system, urban, water
from app.services.models import registry

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the models at startup so the first request is not the slow one.

    A missing artifact is logged and reported through /health rather than aborting
    startup: the rest of the API stays usable, and the affected endpoints return a
    503 explaining exactly what is missing.
    """
    logger.info("SmartCityAI API starting")
    try:
        status = registry.warm_up()
        if not status["all_models_loaded"]:
            missing = [k for k, v in status["models"].items() if not v["loaded"]]
            logger.warning("Starting with models unavailable: %s", ", ".join(missing))
        if not status["all_datasets_present"]:
            missing = [k for k, v in status["datasets"].items() if not v]
            logger.warning("Starting with datasets missing: %s", ", ".join(missing))
    except Exception:  # noqa: BLE001 - startup must not die on a warm-up failure
        logger.exception("Model warm-up failed; endpoints will report per-model status")

    status_line = llm.llm_status()
    logger.info(
        "LLM: provider=%s model=%s enabled=%s key_configured=%s",
        status_line["provider"], status_line["model"],
        status_line["enabled"], status_line["api_key_configured"],
    )
    yield
    logger.info("SmartCityAI API shutting down")


app = FastAPI(
    title="SmartCityAI API",
    version="3.0.0",
    description=(
        "Multi-Agent AI Framework for Sustainable Urban Growth and Water Resource "
        "Planning.\n\n"
        "**Predictive models**\n"
        "- Model 1 — Surface Water Monitoring (XGBoost, city-holdout validated)\n"
        "- Model 2 — Urban Expansion Suitability (LightGBM, forward validation 2000 to 2020)\n"
        "- Model 3 — Urban Flood Risk (Random Forest, city-holdout validated)\n"
        "- Microplastic Screening (ResNet18 on HMPD polarimetric microscopy)\n\n"
        "**Deterministic module**\n"
        "- Sustainable Building Planner (rules, calculations and cited guidelines)\n\n"
        "**Agent layer** — LangGraph, interpretation via Groq\n"
        "- Water/Environment, Urban Planning, Flood/Resilience, Building Sustainability, "
        "and the Coordinator\n\n"
        "**Architectural principle**: LLM agents interpret predictive model outputs; they "
        "do not replace the predictive models. Every probability and score comes from a "
        "trained model or a deterministic rule, never from the language model."
    ),
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)

# ── Error handling: one envelope for every failure ───────────────────────────
app.add_exception_handler(SmartCityError, smartcity_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


def _serialisable_errors(errors: list) -> list[dict]:
    """Make Pydantic validation errors JSON-safe.

    A `model_validator` that raises ValueError puts the exception object itself into
    the error's `ctx`, which `json.dumps` cannot encode — the handler would then fail
    with a 500 while trying to report a 422. Coercing every non-primitive to its string
    form keeps the message intact and the response valid.
    """
    safe = []
    for error in errors:
        entry = {
            "location": [str(part) for part in error.get("loc", ())],
            "message": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        context = error.get("ctx")
        if context:
            entry["context"] = {k: str(v) for k, v in context.items()}
        safe.append(entry)
    return safe


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Render FastAPI validation failures in the same envelope as everything else."""
    errors = _serialisable_errors(exc.errors())
    logger.info(
        "invalid_input on %s %s: %s",
        request.method, request.url.path,
        "; ".join(e["message"] for e in errors) or "validation failed",
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "invalid_input",
            "message": "The request did not pass validation.",
            "detail": {"errors": errors},
        },
    )


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(system.router)
app.include_router(water.router)
app.include_router(urban.router)
app.include_router(flood.router)
app.include_router(microplastics.router)
app.include_router(building.router)
app.include_router(agents.router)


@app.get("/", tags=["system"])
def root():
    """Service description and endpoint index."""
    return {
        "service": "SmartCityAI API",
        "version": "3.0.0",
        "docs": "/docs",
        "principle": (
            "LLM agents interpret predictive model outputs; they do not replace the "
            "predictive models."
        ),
        "endpoints": {
            "system": [
                "GET  /health",
                "GET  /api/models/status",
                "GET  /api/grid/cities",
                "GET  /api/grid/cities/{city}/cells",
                "GET  /api/grid/cities/{city}/geojson",
                "GET  /api/grid/cell/{grid_id}",
                "GET  /api/grid/nearest?lat=&lon=",
            ],
            "water": [
                "POST /api/water",
                "GET  /api/water/cell/{grid_id}",
                "GET  /api/water/city/{city}",
                "GET  /api/water/city/{city}/geojson",
                "GET  /api/water/monitoring/{city}",
                "GET  /api/water/metrics",
            ],
            "urban_expansion": [
                "POST /api/urban-expansion",
                "GET  /api/urban-expansion/cell/{grid_id}",
                "GET  /api/urban-expansion/city/{city}",
                "GET  /api/urban-expansion/city/{city}/geojson",
                "GET  /api/urban-expansion/thresholds",
                "GET  /api/urban-expansion/metrics",
            ],
            "flood_risk": [
                "POST /api/flood-risk",
                "GET  /api/flood-risk/cell/{grid_id}",
                "GET  /api/flood-risk/city/{city}",
                "GET  /api/flood-risk/city/{city}/geojson",
                "GET  /api/flood-risk/thresholds",
                "GET  /api/flood-risk/metrics",
            ],
            "microplastics": [
                "POST /api/microplastics/analyze",
                "POST /api/microplastics/analyze-composite",
                "GET  /api/microplastics/metrics",
            ],
            "building_planner": [
                "POST /api/building-planner",
                "GET  /api/building-planner/site?lat=&lon=",
                "GET  /api/building-planner/guidelines",
                "POST /api/building-planner/nasa-power",
            ],
            "agents": [
                "POST /api/agents/analyze",
                "POST /api/coordinator",
                "POST /api/agents/{water|urban|flood}",
                "GET  /api/agents",
                "GET  /api/agents/graph",
            ],
        },
    }
