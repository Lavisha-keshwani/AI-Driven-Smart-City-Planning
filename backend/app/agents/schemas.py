"""
Structured output contracts for the agent layer.

Agents return validated Pydantic objects, not free-form prose. This is what keeps
the LLM inside its role: the schema has no field in which a model prediction could
be restated or altered, so an agent physically cannot hand back a different flood
probability or suitability score than the one the ML model produced. Numbers
travel in `evidence`, copied from model output by code, never by the LLM.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["high", "medium", "low"]


class AgentResult(BaseModel):
    """One domain agent's interpretation of its model's output."""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(description="The domain this agent covers.")
    summary: str = Field(
        description="Two or three sentences interpreting the model output for a planner."
    )
    findings: list[str] = Field(
        default_factory=list,
        description=(
            "What the evidence shows. Each item must be a plain sentence (a string, "
            "never an object) and must trace to supplied evidence."
        ),
    )
    risks: list[str] = Field(
        default_factory=list,
        description=(
            "Risks or cautions this evidence raises. Each item is a plain sentence "
            "(a string, never an object)."
        ),
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description=(
            "Actions a planner should consider. Each item is a plain sentence (a "
            "string, never an object)."
        ),
    )
    uncertainty: str = Field(
        default="",
        description="What is not known, and how that limits the interpretation.",
    )
    interpretation_confidence: Confidence = Field(
        default="medium",
        description=(
            "The agent's confidence in its own interpretation. This is not the model's "
            "predicted probability and must never be presented as one."
        ),
    )


class DomainAnalysis(BaseModel):
    """An agent result together with the machine evidence it was given.

    `evidence` is assembled in code from the model output. `source` records whether
    the narrative came from the LLM or from the deterministic fallback, so a reader
    always knows which parts of a response an LLM touched.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    agent: str
    model: str | None = None
    result: AgentResult
    evidence: dict = Field(default_factory=dict)
    source: Literal["llm", "deterministic_fallback"] = "llm"
    llm_model: str | None = None
    note: str | None = None


class TradeOff(BaseModel):
    """A conflict between two domains that the Coordinator identified."""

    model_config = ConfigDict(extra="forbid")

    between: list[str] = Field(description="The domains in tension.")
    tension: str = Field(description="What the conflict is.")
    resolution: str = Field(description="How development should proceed given the conflict.")


class CoordinatorResult(BaseModel):
    """The Coordinator's synthesis across all domain agents."""

    model_config = ConfigDict(extra="forbid")

    overall_recommendation: Literal[
        "proceed",
        "proceed_with_conditions",
        "proceed_with_strong_mitigation",
        "discourage",
        "insufficient_evidence",
    ] = Field(description="The headline decision for this location.")
    headline: str = Field(description="One sentence a non-specialist can act on.")
    rationale: str = Field(
        description="Four to six sentences explaining the decision from the evidence."
    )
    trade_offs: list[TradeOff] = Field(
        default_factory=list, description="Conflicts between domains and how to resolve them."
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Measures required for development to be acceptable here.",
    )
    priority_actions: list[str] = Field(
        default_factory=list, description="What to do first, in order."
    )
    evidence_gaps: list[str] = Field(
        default_factory=list, description="Missing evidence that limits this conclusion."
    )


class CoordinatorReport(BaseModel):
    """The Coordinator result plus the deterministic signals behind it."""

    model_config = ConfigDict(extra="forbid")

    result: CoordinatorResult
    signals: dict = Field(
        default_factory=dict,
        description="Deterministic domain signals the synthesis was based on.",
    )
    detected_conflicts: list[dict] = Field(
        default_factory=list,
        description="Conflicts found by the rule-based trade-off detector, before the LLM.",
    )
    source: Literal["llm", "deterministic_fallback"] = "llm"
    llm_model: str | None = None
    note: str | None = None
