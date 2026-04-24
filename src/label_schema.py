"""Pydantic schema for human-authored ground-truth triage labels.

Distinct from :class:`src.triage_schema.TriageVerdict`, which is the
*model's* output. A :class:`GroundTruthLabel` is written by a human
reviewer (you) who has inspected the actual code around a Semgrep
finding — typically with more context than the LLM sees — and recorded
what the correct verdict should be.

The eval harness uses these labels as the reference standard: for each
``(finding, prompt_variant)`` pair, it runs the model N times and
computes what fraction of runs agree with the ground-truth verdict.
Match-rate across all findings, stratified by variant, is the primary
metric for comparing prompt changes.

Fields capture enough context to review or re-label without rerunning
Semgrep (``check_id``, ``path_relative``, ``line``) and enough
provenance to audit the label set over time (``labeler``,
``labeled_at``, the labeler's own ``confidence`` in their verdict).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GroundTruthLabel(BaseModel):
    """A single human-authored ground-truth label for a Semgrep finding.

    One :class:`GroundTruthLabel` per finding in the labeled set. The
    ``verdict`` field is the reference label the eval harness compares
    model output against; ``reasoning`` documents why the labeler chose
    that verdict so the judgment is auditable. ``confidence`` is the
    *labeler's* confidence in their own call — some findings are
    genuinely hard to adjudicate without running the app, and a low
    labeler confidence flags those cases so we don't over-weight them
    in the aggregate metrics.
    """

    finding_index: int = Field(
        ...,
        ge=0,
        description="Index into results[] array of semgrep_juiceshop.json",
    )
    check_id: str = Field(
        ...,
        min_length=1,
        description="Semgrep rule ID for human readability",
    )
    path_relative: str = Field(
        ...,
        min_length=1,
        description="Path relative to juice-shop/ for human readability",
    )
    line: int = Field(
        ...,
        ge=1,
        description="Start line of the finding",
    )
    verdict: Literal["true_positive", "false_positive", "needs_review"] = Field(
        ...,
        description="Labeler's ground-truth verdict",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Labeler's confidence in their own verdict",
    )
    reasoning: str = Field(
        ...,
        min_length=50,
        description="Labeler's reasoning, referencing specific code",
    )
    labeler: str = Field(
        default="phillip",
        description="Who labeled this",
    )
    labeled_at: str = Field(
        ...,
        description="ISO timestamp of when labeled",
    )
