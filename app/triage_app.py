"""Streamlit UI for the LLM-assisted SAST triage workflow.

This is the *user-facing* entry point — distinct from
``scripts/run_eval.py``, which is the *evaluation* entry point used to
measure prompt and model variants against ground-truth labels. The eval
script is for researchers; this app is for an AppSec engineer who has a
fresh ``semgrep --json`` output and wants triage verdicts.

Workflow:

1. Upload a Semgrep JSON file.
2. Pick a model provider and a prompt variant.
3. Click Run; the app calls :func:`~src.triage_engine.triage_finding`
   on every finding and shows verdict / confidence / reasoning per row.
4. Optionally export the per-finding results as JSON.

All API calls happen inside the Run button handler and the results live
in ``st.session_state["triage_results"]``, so Streamlit's per-interaction
re-runs don't trigger duplicate calls.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow ``streamlit run app/triage_app.py`` from the project root by
# putting the repo root on sys.path so ``import src.*`` works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402  (must come after sys.path setup)

from src.triage_engine import (  # noqa: E402
    MODEL_DISPATCH,
    PROMPT_VARIANTS,
    triage_finding,
)

GITHUB_URL = "https://github.com/Papuzzio/sast-llm-triage"
DISCLAIMER = (
    "Triage assistant. Not a replacement for human review. Do not "
    "auto-close findings based on this output alone."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_rule(check_id: str) -> str:
    """Last dotted segment of a Semgrep rule id, for compact display."""
    return check_id.rsplit(".", 1)[-1]


def _short_path(path: str) -> str:
    """Best-effort relative path; falls back to basename for absolute paths."""
    p = Path(path)
    parts = p.parts
    # If absolute and "juice-shop" (or similar repo-name folder) is in the
    # path, anchor on it. Otherwise just take the last 2 segments to keep
    # the table readable.
    for anchor in ("juice-shop", "juice_shop"):
        if anchor in parts:
            i = parts.index(anchor)
            return "/".join(parts[i + 1:]) or p.name
    if p.is_absolute() and len(parts) > 2:
        return "/".join(parts[-2:])
    return path


def _truncate(text: str | None, n: int = 100) -> str:
    if text is None:
        return ""
    return text if len(text) <= n else text[: n - 1] + "…"


def _run_triage(
    findings: list[dict],
    variant: str,
    model: str,
) -> list[dict]:
    """Triage every finding sequentially, capturing per-finding errors."""
    results: list[dict] = []
    progress = st.progress(0.0)
    status = st.empty()
    n = len(findings)

    for i, finding in enumerate(findings, start=1):
        rule_short = _short_rule(finding.get("check_id", "?"))
        status.text(f"Triaging {i} of {n}: {rule_short}")

        row: dict[str, Any] = {
            "finding_index": i - 1,
            "check_id": finding.get("check_id", "?"),
            "path": finding.get("path", "?"),
            "line": finding.get("start", {}).get("line", -1),
            "verdict": None,
            "confidence": None,
            "reasoning": None,
            "remediation": None,
            "cwe_confirmed": None,
            "error": None,
            "latency_seconds": None,
        }

        t0 = time.perf_counter()
        try:
            verdict = triage_finding(finding, variant=variant, model=model)
            row["latency_seconds"] = time.perf_counter() - t0
            row["verdict"] = verdict.verdict
            row["confidence"] = verdict.confidence
            row["reasoning"] = verdict.reasoning
            row["remediation"] = verdict.remediation
            row["cwe_confirmed"] = verdict.cwe_confirmed
        except Exception as exc:
            row["latency_seconds"] = time.perf_counter() - t0
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["verdict"] = "ERROR"

        results.append(row)
        progress.progress(i / n)

    status.text(f"Done — {n} findings triaged.")
    return results


def _results_table_rows(results: list[dict]) -> list[dict]:
    """Project per-finding results into the columns shown in st.dataframe."""
    return [
        {
            "rule": _short_rule(r["check_id"]),
            "file:line": f"{_short_path(r['path'])}:{r['line']}",
            "verdict": r["verdict"] or "—",
            "confidence": (
                f"{r['confidence']:.2f}" if r["confidence"] is not None else "—"
            ),
            "reasoning": _truncate(r["reasoning"] or r["error"]),
        }
        for r in results
    ]


# ---------------------------------------------------------------------------
# Page setup + sidebar
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="TriageGPT — LLM-Assisted SAST Triage",
    layout="wide",
)

with st.sidebar:
    st.warning(DISCLAIMER)
    with st.expander("About"):
        st.markdown(
            f"""
**TriageGPT** — LLM-assisted triage of Static Application Security
Testing (SAST) findings.

- **Models:** {", ".join(sorted(MODEL_DISPATCH.keys()))}
- **Prompt variants:** {", ".join(sorted(PROMPT_VARIANTS.keys()))}
- **Source:** [{GITHUB_URL}]({GITHUB_URL})
"""
        )


# ---------------------------------------------------------------------------
# Main column: title, description, controls
# ---------------------------------------------------------------------------

st.title("TriageGPT — LLM-Assisted SAST Triage")
st.markdown(
    "Upload a Semgrep `--json` output, pick a model and prompt variant, "
    "and the app classifies every finding as **true_positive**, "
    "**false_positive**, or **needs_review** with a confidence score and "
    "reasoning. Each finding is reviewed independently; verdicts are "
    "model output and must be checked by a human."
)

uploaded = st.file_uploader(
    "Semgrep JSON output",
    accept_multiple_files=False,
    type=["json"],
)

col_model, col_variant = st.columns(2)
with col_model:
    model = st.selectbox(
        "Model",
        options=sorted(MODEL_DISPATCH.keys()),
        index=sorted(MODEL_DISPATCH.keys()).index("gemini"),
    )
with col_variant:
    variant = st.selectbox(
        "Prompt variant",
        options=sorted(PROMPT_VARIANTS.keys()),
        index=sorted(PROMPT_VARIANTS.keys()).index("baseline"),
    )

run_clicked = st.button(
    "Run triage",
    disabled=uploaded is None,
    type="primary",
)


# ---------------------------------------------------------------------------
# Triage execution (button handler) — only fires on click
# ---------------------------------------------------------------------------

if run_clicked and uploaded is not None:
    try:
        data = json.loads(uploaded.getvalue())
    except json.JSONDecodeError as exc:
        st.error(f"Could not parse uploaded file as JSON: {exc}")
        st.stop()

    findings = data.get("results")
    if not isinstance(findings, list) or not findings:
        st.error(
            "Uploaded JSON has no `results` array, or the array is empty. "
            "Expected the standard `semgrep --json` shape."
        )
        st.stop()

    with st.spinner(f"Triaging {len(findings)} findings with {model} / {variant}…"):
        results = _run_triage(findings, variant=variant, model=model)

    st.session_state["triage_results"] = results
    st.session_state["triage_meta"] = {
        "model": model,
        "variant": variant,
        "n_findings": len(findings),
    }


# ---------------------------------------------------------------------------
# Results rendering (always renders if session state has results)
# ---------------------------------------------------------------------------

if "triage_results" in st.session_state:
    results = st.session_state["triage_results"]
    meta = st.session_state.get("triage_meta", {})

    st.subheader("Results")
    if meta:
        st.caption(
            f"{meta.get('n_findings', len(results))} findings  ·  "
            f"model: `{meta.get('model', '?')}`  ·  "
            f"variant: `{meta.get('variant', '?')}`"
        )

    n_error = sum(1 for r in results if r["verdict"] == "ERROR")
    if n_error:
        st.warning(f"{n_error} of {len(results)} findings errored — see ERROR rows.")

    st.dataframe(
        _results_table_rows(results),
        use_container_width=True,
        hide_index=False,
    )

    st.markdown("##### Per-finding details")
    for r in results:
        title = (
            f"#{r['finding_index']}  ·  {_short_rule(r['check_id'])}  ·  "
            f"{_short_path(r['path'])}:{r['line']}  ·  "
            f"verdict: {r['verdict'] or '—'}"
        )
        with st.expander(title):
            if r["error"]:
                st.error(r["error"])
            else:
                st.markdown(f"**Verdict:** {r['verdict']}")
                st.markdown(f"**Confidence:** {r['confidence']:.2f}")
                st.markdown(f"**CWE confirmed:** {r['cwe_confirmed']}")
                st.markdown("**Reasoning**")
                st.write(r["reasoning"])
                st.markdown("**Remediation**")
                st.write(r["remediation"])
            if r["latency_seconds"] is not None:
                st.caption(f"Latency: {r['latency_seconds']:.2f}s")

    st.download_button(
        label="Download results as JSON",
        data=json.dumps(results, indent=2, ensure_ascii=False),
        file_name="triage_results.json",
        mime="application/json",
    )
