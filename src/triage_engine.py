"""Triage a single Semgrep finding by asking Gemini for a structured verdict.

Given a raw finding dict (as produced by ``semgrep --json``), this module
pulls the relevant fields, reads the surrounding source-code snippet from
disk, assembles an AppSec-engineer-style prompt, and asks Gemini for a
:class:`~src.triage_schema.TriageVerdict` in structured JSON. Pydantic
validates the response before it's returned.

Multiple prompt variants live in :data:`PROMPT_VARIANTS` so we can A/B
test prompt-engineering changes (e.g. whether an explicit instruction to
ignore file paths suppresses the "this is juice-shop so it must be
exploitable" bias we observed in Session 3, or whether seeding the prompt
with worked examples drawn from the human-labeled ground truth nudges
the model toward more grounded, line-referenced reasoning). Callers pick
a variant by name via the ``variant`` argument to :func:`triage_finding`.

This is the per-finding unit of work; the orchestrator (not yet written)
will loop over all findings and persist verdicts to disk.
"""

from __future__ import annotations

from .gemini_client import call_gemini_structured
from .snippet_reader import read_snippet
from .triage_schema import TriageVerdict


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
# Templates are *plain* strings (not f-strings) with ``{check_id}``,
# ``{cwe}``, ``{severity}``, ``{message}``, ``{path}``, ``{start_line}``,
# ``{end_line}``, and ``{snippet}`` placeholders. :func:`triage_finding`
# fills them via ``str.format``. Any literal braces inside a template
# (e.g. JS template-literal ``${{...}}`` inside a worked example) must
# be doubled to escape the format machinery.

_BASELINE_PROMPT = """You are an application security (AppSec) engineer triaging output from a Static Application Security Testing (SAST) tool (Semgrep). Classify the following finding as one of:
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


# Derive the no_path_bias prompt from baseline so shared text stays in sync.
_NO_PATH_BIAS_PROMPT = _BASELINE_PROMPT.replace(
    "Return JSON matching the provided schema.",
    (
        "Base your verdict strictly on the code visible in the snippet. "
        "Do not infer exploitability from the file path, project name, "
        "or repository reputation."
        "\n\n"
        "Return JSON matching the provided schema."
    ),
)


# Worked examples drawn from the human-labeled ground truth in
# ``eval/ground_truth.json``. They span all three verdict labels and
# demonstrate line-anchored reasoning, variable-source tracing, and
# escalation to ``needs_review`` when context is insufficient. The
# JS template-literal ``${{...}}`` braces in EXAMPLE 3 are doubled so
# ``str.format`` treats them as literal output.
_FEW_SHOT_EXAMPLES_BLOCK = """BEGIN EXAMPLES
Here are three worked examples of correctly triaged findings. Reason in the same style — reference specific lines, trace variables to their sources, escalate to needs_review when context is insufficient.

EXAMPLE 1:
Rule: express-open-redirect
File: routes/redirect.ts (line 19)
Code (excerpt): res.redirect(toUrl) where toUrl = query.to and gated by security.isRedirectAllowed (imported, not visible in this file).
Verdict: needs_review
Confidence: 0.55
Reasoning: The redirect destination originates from query.to (untrusted user input). The gate function security.isRedirectAllowed is not visible in this file. The companion isUnintendedRedirect uses startsWith for URL matching, which is known to be bypassable. Without inspecting the actual gate, exploitability cannot be confirmed.

EXAMPLE 2:
Rule: hardcoded-jwt-secret
File: lib/insecurity.ts (line 56)
Code (excerpt): jwt.sign(user, privateKey, ...) where privateKey is defined at line 23 as a literal RSA private key string.
Verdict: true_positive
Confidence: 0.95
Reasoning: The signing secret is hardcoded as a literal string in source. Anyone with repo access can extract the private key and forge JWT tokens for any user, achieving full authentication bypass. The companion publicKey is loaded from a file, which is appropriate for a public key but not for the private key.

EXAMPLE 3:
Rule: express-sequelize-injection
File: routes/login.ts (line 34)
Code (excerpt): sequelize.query(`SELECT * FROM Users WHERE email = '${{req.body.email}}' AND password = '${{security.hash(req.body.password)}}' ...`)
Verdict: true_positive
Confidence: 0.95
Reasoning: User input from req.body is interpolated directly into a raw SQL string via template literal. There is no parameterization, no ORM query builder, no escape function. A payload like ' OR 1=1 -- in the email field bypasses authentication.
END EXAMPLES

"""


# Derive the few_shot prompt from baseline by inserting the examples block
# right after the classification instructions and before the finding data.
_FEW_SHOT_PROMPT = _BASELINE_PROMPT.replace(
    "Rule: {check_id}",
    _FEW_SHOT_EXAMPLES_BLOCK + "Rule: {check_id}",
)


PROMPT_VARIANTS: dict[str, str] = {
    "baseline": _BASELINE_PROMPT,
    "no_path_bias": _NO_PATH_BIAS_PROMPT,
    "few_shot": _FEW_SHOT_PROMPT,
}


def triage_finding(finding: dict, variant: str = "baseline") -> TriageVerdict:
    """Classify a single Semgrep finding via Gemini structured output.

    Extracts the file path, line range, rule id, CWE, severity, and rule
    description from ``finding``; reads a ``context=3`` snippet around the
    flagged range; formats the selected prompt template; and asks Gemini
    for a :class:`TriageVerdict`.

    Args:
        finding: One element of the ``results`` array in Semgrep's JSON
            output. Must contain ``path``, ``start.line``, ``end.line``,
            ``check_id``, and ``extra.{message, severity, metadata}``.
        variant: Which prompt template in :data:`PROMPT_VARIANTS` to use.
            Defaults to ``"baseline"``. Available variants:

            * ``"baseline"`` — the original Session 3 prompt.
            * ``"no_path_bias"`` — baseline + an explicit instruction to
              ignore file paths, project names, and repository
              reputation when forming the verdict.
            * ``"few_shot"`` — baseline + three worked examples drawn
              from the human-labeled ground truth, one per verdict
              label (``needs_review``, ``true_positive``,
              ``true_positive``), demonstrating line-anchored reasoning
              and proper escalation to ``needs_review`` when context is
              insufficient.

    Returns:
        A validated :class:`TriageVerdict` with the model's classification.

    Raises:
        KeyError: If ``variant`` is not a key in :data:`PROMPT_VARIANTS`,
            or if ``finding`` is missing a required field.
        FileNotFoundError: If the file at ``finding['path']`` cannot be read.
        pydantic.ValidationError: If Gemini returns JSON that does not
            conform to the :class:`TriageVerdict` schema.
    """
    try:
        template = PROMPT_VARIANTS[variant]
    except KeyError:
        raise KeyError(
            f"Unknown prompt variant: {variant!r}. "
            f"Available variants: {sorted(PROMPT_VARIANTS)}"
        ) from None

    path = finding["path"]
    start_line = finding["start"]["line"]
    end_line = finding["end"]["line"]
    check_id = finding["check_id"]
    message = finding["extra"]["message"]
    cwe = finding["extra"]["metadata"].get("cwe", ["unknown"])[0]
    severity = finding["extra"]["severity"]

    snippet = read_snippet(path, start_line, end_line, context=3)

    prompt = template.format(
        check_id=check_id,
        cwe=cwe,
        severity=severity,
        message=message,
        path=path,
        start_line=start_line,
        end_line=end_line,
        snippet=snippet,
    )

    verdict = call_gemini_structured(prompt, TriageVerdict)
    # call_gemini_structured returns BaseModel; narrow to TriageVerdict.
    assert isinstance(verdict, TriageVerdict)
    return verdict
