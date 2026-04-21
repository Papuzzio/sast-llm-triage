"""Pydantic schema for LLM-generated SAST triage verdicts.

The Gemini triage pipeline asks the model to classify each Semgrep finding
as a true positive, false positive, or needs-review case, along with a
confidence score, human-readable reasoning, remediation guidance, and a
check on whether the rule's CWE mapping is appropriate for the finding.

The model is instructed to return a JSON object matching this schema, and
we parse that response into a :class:`TriageVerdict`. Pydantic's validation
guarantees downstream consumers (reports, dashboards, CSV exports) see
well-formed data: confidence is bounded to [0.0, 1.0], reasoning and
remediation have minimum lengths that reject empty or one-word responses,
and the verdict field is restricted to a known enum of labels.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TriageVerdict(BaseModel):
    """A structured triage judgment for a single Semgrep finding.

    One :class:`TriageVerdict` is produced per finding by the LLM. The
    ``verdict`` field is the top-line label; ``confidence`` quantifies how
    sure the model is; ``reasoning`` and ``remediation`` provide the
    auditable narrative a security engineer can review; and
    ``cwe_confirmed`` sanity-checks whether the rule's declared CWE is the
    right one for the observed code pattern.
    """

    verdict: Literal["true_positive", "false_positive", "needs_review"] = Field(
        ...,
        description="The triage classification for this finding.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in the verdict, 0.0 to 1.0.",
    )
    reasoning: str = Field(
        ...,
        min_length=50,
        description=(
            "Explanation of why this verdict was assigned. Must reference "
            "the code and the rule."
        ),
    )
    remediation: str = Field(
        ...,
        min_length=30,
        description=(
            "For true_positive: suggested fix. For false_positive: "
            "suppression justification. For needs_review: what context "
            "would resolve the ambiguity."
        ),
    )
    cwe_confirmed: bool = Field(
        ...,
        description=(
            "Whether the CWE mapping in the Semgrep rule metadata is "
            "correct for this finding."
        ),
    )
