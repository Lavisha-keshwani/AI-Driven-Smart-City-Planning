"""
Shared machinery for the domain agents.

Each agent follows the same three steps:

  1. run its model or rules engine, writing the raw output to `*_result`
  2. extract the evidence the LLM is allowed to see, in code
  3. ask the LLM to interpret that evidence, and validate the response

Step 3 is optional in effect: when the LLM is unavailable, `deterministic_result`
composes a summary from the model output itself. The response then says
`source: "deterministic_fallback"`, so a degraded run is visible rather than
disguised.
"""

from __future__ import annotations

import json
import logging

from app.agents import llm
from app.agents.schemas import AgentResult, DomainAnalysis
from app.core.errors import SmartCityError

logger = logging.getLogger(__name__)


def render_evidence(evidence: dict) -> str:
    """Serialise evidence for the prompt.

    JSON rather than prose: it keeps numbers verbatim, makes nulls explicit as
    unavailable, and gives the model no sentence to paraphrase a figure out of.
    """
    return json.dumps(evidence, indent=2, default=str, sort_keys=False)


def interpret(
    *,
    domain: str,
    agent: str,
    model_name: str | None,
    task: str,
    evidence: dict,
    fallback: AgentResult,
) -> DomainAnalysis:
    """Ask the LLM to interpret evidence, falling back deterministically."""
    prompt = (
        f"{task}\n\n"
        f"EVIDENCE (authoritative — use these values exactly, do not recompute):\n"
        f"{render_evidence(evidence)}\n\n"
        f"Interpret this evidence for the {domain} domain. Cite the specific values "
        f"that drive your reading, and distinguish measured observations from model "
        f"predictions. If a value is null it was unavailable — say so rather than "
        f"guessing it."
    )
    result, meta = llm.structured_call(prompt, AgentResult, context=f"{agent} ({domain})")

    if result is None:
        return DomainAnalysis(
            domain=domain, agent=agent, model=model_name,
            result=fallback, evidence=evidence, **meta,
        )

    # The agent declares its own domain; keep ours so the key is always consistent.
    result.domain = domain
    return DomainAnalysis(
        domain=domain, agent=agent, model=model_name,
        result=result, evidence=evidence, **meta,
    )


def failure_analysis(
    *, domain: str, agent: str, model_name: str | None, exc: SmartCityError
) -> DomainAnalysis:
    """Represent an unavailable model without fabricating a finding."""
    return DomainAnalysis(
        domain=domain,
        agent=agent,
        model=model_name,
        result=AgentResult(
            domain=domain,
            summary=(
                f"No analysis is available for the {domain} domain: {exc.message} "
                f"No substitute value was generated."
            ),
            findings=[],
            risks=[
                f"The {domain} domain could not be assessed, so any overall conclusion "
                f"is missing this evidence."
            ],
            recommendations=[
                f"Restore the {domain} inputs and re-run the analysis before relying "
                f"on the recommendation."
            ],
            uncertainty=(
                f"Complete: the {domain} evidence is absent ({exc.error_code})."
            ),
            interpretation_confidence="low",
        ),
        evidence={"error": exc.error_code, "message": exc.message, "detail": exc.detail},
        source="deterministic_fallback",
        note=f"{domain} evidence unavailable: {exc.error_code}",
    )


def error_entry(domain: str, exc: SmartCityError) -> dict:
    """A structured entry for the state's `errors` list."""
    return {
        "domain": domain,
        "error": exc.error_code,
        "message": exc.message,
        "detail": exc.detail,
    }
