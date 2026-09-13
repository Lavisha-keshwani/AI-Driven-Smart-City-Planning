"""
Groq LLM client for the agent layer.

The model is configurable through GROQ_MODEL and defaults to openai/gpt-oss-120b.
An optional GROQ_FALLBACK_MODEL is tried if the primary fails. No key is ever
hard-coded or logged.

Every call goes through `structured_call`, which binds a Pydantic schema to the
request so responses are validated before they reach the graph. If the LLM is
unreachable, disabled, or returns something that fails validation, the caller gets
`None` and falls back to a deterministic narrative — the pipeline never stalls on
the LLM, and never presents an LLM failure as an analysis.

The shared system prompt encodes the project's central constraint: predictions come
from the ML models and rules, and the LLM only interprets them.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core import config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Prepended to every agent prompt. The numbered constraints are the project's
# guardrails against the LLM drifting from interpreter into predictor.
GUARDRAILS = """You are one agent in a geospatial urban-planning decision-support system.

Your role is INTERPRETATION ONLY. Follow these rules without exception:

1. Every predictive number is produced by a machine-learning model or a
   deterministic rules engine, and is supplied to you as evidence. You never
   compute, estimate, adjust, round or re-derive one.
2. Never invent a value that was not supplied. If a figure you would want is
   absent, say it is unavailable and explain what that prevents you concluding.
3. Never contradict or override a supplied model prediction. You may explain what
   it means, what it does not establish, and how confident it is.
4. Keep the four kinds of information distinct, and make which is which clear from
   your wording, in ordinary prose:
   - measured data (satellite observations, meteorological records)
   - model predictions (probabilities and classifications from trained models)
   - rule-based recommendations (deterministic calculations from guidelines)
   - your own interpretation
   Write it the way a careful analyst speaks, for example "satellite observations
   show...", "the flood model predicts...", "the rules engine recommends...", "in my
   reading...". Never append bracketed source tags, citation markers, or footnote
   labels: this text is shown directly to a reader, and such markers only clutter it.
5. State uncertainty plainly. Where a model's recall is moderate, a negative
   result means absence of evidence, not evidence of absence.
6. Make no claim the supplied evidence does not support. No regulatory compliance
   claims, no structural engineering instructions, no chemical measurements.
7. Return output conforming exactly to the requested schema. Where a field is a
   list of strings, every element must be a plain sentence, never a nested object,
   even when the evidence you were given was structured that way.

Write for a professional planner who is not a machine-learning specialist: plain
language, specific about evidence, no jargon for its own sake."""


class LLMUnavailable(RuntimeError):
    """The LLM could not be used for this call."""


def llm_status() -> dict:
    """Configuration state of the LLM layer, without exposing the key."""
    return {
        "enabled": config.LLM_ENABLED,
        "api_key_configured": bool(config.GROQ_API_KEY),
        "provider": "groq",
        "model": config.GROQ_MODEL,
        "fallback_model": config.GROQ_FALLBACK_MODEL or None,
        "temperature": config.LLM_TEMPERATURE,
        "timeout_seconds": config.LLM_TIMEOUT,
    }


def is_available() -> bool:
    return bool(config.LLM_ENABLED and config.GROQ_API_KEY)


@lru_cache(maxsize=4)
def _client(model: str):
    """Build and cache one ChatGroq client per model id."""
    from langchain_groq import ChatGroq

    return ChatGroq(
        api_key=config.GROQ_API_KEY,
        model=model,
        temperature=config.LLM_TEMPERATURE,
        timeout=config.LLM_TIMEOUT,
        max_retries=1,
    )


def _candidate_models() -> list[str]:
    models = [config.GROQ_MODEL]
    if config.GROQ_FALLBACK_MODEL and config.GROQ_FALLBACK_MODEL != config.GROQ_MODEL:
        models.append(config.GROQ_FALLBACK_MODEL)
    return models


def structured_call(prompt: str, schema: type[T], *, context: str) -> tuple[T | None, dict]:
    """Ask the LLM for a schema-validated object.

    Returns `(instance, meta)`. `instance` is None when the LLM is unavailable or
    every attempt failed; `meta` always records what happened, so the caller can
    report the degradation honestly instead of hiding it.
    """
    if not config.LLM_ENABLED:
        return None, {"source": "deterministic_fallback",
                      "note": "LLM interpretation is disabled (LLM_ENABLED=false)."}
    if not config.GROQ_API_KEY:
        return None, {"source": "deterministic_fallback",
                      "note": "GROQ_API_KEY is not configured, so no LLM interpretation was generated."}

    errors: list[str] = []
    for model in _candidate_models():
        try:
            structured = _client(model).with_structured_output(schema)
            result = structured.invoke([
                {"role": "system", "content": GUARDRAILS},
                {"role": "user", "content": prompt},
            ])
        except ValidationError as exc:
            errors.append(f"{model}: response failed schema validation ({exc.error_count()} errors)")
            logger.warning("LLM %s returned invalid structure for %s", model, context)
            continue
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
            errors.append(f"{model}: {type(exc).__name__}: {exc}")
            logger.warning("LLM %s failed for %s: %s", model, context, exc)
            continue

        if not isinstance(result, schema):
            try:
                result = schema.model_validate(result)
            except ValidationError as exc:
                errors.append(f"{model}: could not coerce response ({exc.error_count()} errors)")
                continue

        logger.info("LLM %s produced %s for %s", model, schema.__name__, context)
        return result, {"source": "llm", "llm_model": model}

    logger.error("All LLM attempts failed for %s: %s", context, "; ".join(errors))
    return None, {
        "source": "deterministic_fallback",
        "note": (
            "LLM interpretation unavailable, so a deterministic summary was generated "
            "from the model outputs instead. Attempts: " + "; ".join(errors)
        ),
    }


def reset_clients() -> None:
    """Drop cached clients — used by tests after changing configuration."""
    _client.cache_clear()
