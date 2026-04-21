"""Triage a single Semgrep finding by asking Gemini for a structured verdict.

Given a raw finding dict (as produced by ``semgrep --json``), this module
pulls the relevant fields, reads the surrounding source-code snippet from
disk, assembles an AppSec-engineer-style prompt, and asks Gemini for a
:class:`~src.triage_schema.TriageVerdict` in structured JSON. Pydantic
validates the response before it's returned.

This is the per-finding unit of work; the orchestrator (not yet written)
will loop over all findings and persist verdicts to disk.
"""

from __future__ import annotations

from .gemini_client import call_gemini_structured
from .snippet_reader import read_snippet
from .triage_schema import TriageVerdict


def triage_finding(finding: dict) -> TriageVerdict:
    """Classify a single Semgrep finding via Gemini structured output.

    Extracts the file path, line range, rule id, CWE, severity, and rule
    description from ``finding``; reads a ``context=3`` snippet around the
    flagged range; and prompts Gemini for a :class:`TriageVerdict`.

    Args:
        finding: One element of the ``results`` array in Semgrep's JSON
            output. Must contain ``path``, ``start.line``, ``end.line``,
            ``check_id``, and ``extra.{message, severity, metadata}``.

    Returns:
        A validated :class:`TriageVerdict` with the model's classification.

    Raises:
        KeyError: If ``finding`` is missing a required field.
        FileNotFoundError: If the file at ``finding['path']`` cannot be read.
        pydantic.ValidationError: If Gemini returns JSON that does not
            conform to the :class:`TriageVerdict` schema.
    """
    path = finding["path"]
    start_line = finding["start"]["line"]
    end_line = finding["end"]["line"]
    check_id = finding["check_id"]
    message = finding["extra"]["message"]
    cwe = finding["extra"]["metadata"].get("cwe", ["unknown"])[0]
    severity = finding["extra"]["severity"]

    snippet = read_snippet(path, start_line, end_line, context=3)

    prompt = f"""You are an application security (AppSec) engineer triaging output from a Static Application Security Testing (SAST) tool (Semgrep). Classify the following finding as one of:
- true_positive: a real, exploitable vulnerability
- false_positive: the rule fired but the code is safe in this context
- needs_review: insufficient information to determine exploitability from the code alone

Rule: {check_id}
CWE: {cwe}
Severity: {severity}

Rule description:
{message}

File: {path}
Line range: {start_line}-{end_line}

Code (with surrounding context):
{snippet}

Analyze the code carefully. Your reasoning must reference specific line numbers from the snippet above and explain why the rule's precondition does or does not hold in this specific code. Do not hallucinate facts about the code you cannot see.

Return JSON matching the provided schema."""

    verdict = call_gemini_structured(prompt, TriageVerdict)
    # call_gemini_structured returns BaseModel; narrow to TriageVerdict.
    assert isinstance(verdict, TriageVerdict)
    return verdict
