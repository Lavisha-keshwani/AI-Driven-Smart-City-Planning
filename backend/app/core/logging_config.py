"""
Logging setup and per-request correlation.

Every log line carries a request id so a single call can be traced end to end:
request -> model inference -> agent -> coordinator -> response. Secrets are
never logged; only key presence is ever reported.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import LOG_LEVEL

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging() -> None:
    """Install the root handler. Safe to call more than once."""
    root = logging.getLogger()
    if any(getattr(h, "_smartcity", False) for h in root.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(request_id)-8s  %(name)-42s  %(levelname)-7s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    handler.addFilter(_RequestIdFilter())
    handler._smartcity = True  # type: ignore[attr-defined]

    root.handlers = [handler]
    root.setLevel(LOG_LEVEL)

    # Third-party libraries are chatty at INFO; keep them at WARNING.
    for noisy in ("httpx", "httpcore", "urllib3", "matplotlib", "shap"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign each request a short id and expose it on the response."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._log = logging.getLogger("app.request")

    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        token = _request_id.set(rid)
        try:
            self._log.info("--> %s %s", request.method, request.url.path)
            response = await call_next(request)
            self._log.info("<-- %s %s %s", request.method, request.url.path, response.status_code)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            _request_id.reset(token)
