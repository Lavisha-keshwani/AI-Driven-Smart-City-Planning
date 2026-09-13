"""
Domain exceptions and their HTTP mapping.

The rule the whole backend follows: when something cannot be computed, say so.
No endpoint substitutes a plausible-looking number for a missing model, a
missing dataset or an unreachable upstream API.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class SmartCityError(Exception):
    """Base class for every error this service raises deliberately."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ModelUnavailableError(SmartCityError):
    """A trained model artifact is missing or failed to load."""

    status_code = 503
    error_code = "model_unavailable"


class DatasetUnavailableError(SmartCityError):
    """A required feature dataset is missing or unreadable."""

    status_code = 503
    error_code = "dataset_unavailable"


class GridNotFoundError(SmartCityError):
    """The requested grid cell is not part of the analysis grid."""

    status_code = 404
    error_code = "grid_not_found"


class InvalidInputError(SmartCityError):
    """Caller-supplied input is outside the accepted domain."""

    status_code = 400
    error_code = "invalid_input"


class UpstreamServiceError(SmartCityError):
    """An external dependency (NASA POWER, Groq) could not be reached."""

    status_code = 502
    error_code = "upstream_unavailable"


class InferenceError(SmartCityError):
    """The model loaded but prediction failed."""

    status_code = 500
    error_code = "inference_failed"


async def smartcity_exception_handler(request: Request, exc: SmartCityError) -> JSONResponse:
    """Render a SmartCityError as the documented error envelope."""
    logger.warning(
        "%s on %s %s: %s", exc.error_code, request.method, request.url.path, exc.message
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message, "detail": exc.detail},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the traceback server-side, return no filesystem detail."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected server error occurred. See server logs for details.",
            "detail": {"exception": type(exc).__name__},
        },
    )
