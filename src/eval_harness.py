"""Statistical evaluation harness for prompt × model × ground-truth labels.

For each (labeled finding, prompt variant, model provider) cell, this
harness runs :func:`~src.triage_engine.triage_finding` ``n_trials``
times and records per-trial outcomes (model verdict, confidence,
reasoning, remediation, CWE check, latency, and any error). Aggregated
per (variant, model) cell: total trials, successes vs. errors,
match-rate against ground truth, verdict distribution, mean confidence,
mean latency, and number of trials skipped due to few-shot
contamination.

The harness handles the few-shot contamination problem: the
``few_shot`` prompt variant embeds three labeled findings as worked
examples in its prompt. Evaluating that variant on those same findings
would measure how well the model can copy from its own prompt, not its
triage skill. The contamination check is variant-only — it does not
depend on the model — so the same labels are skipped under every model
when ``skip_contaminated_few_shot=True`` (the default), and the skips
are counted separately per (variant, model) cell.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from .label_schema import GroundTruthLabel
from .triage_engine import triage_finding
from .triage_schema import TriageVerdict


# Findings used as worked examples in the few_shot prompt; evaluating
# the few_shot variant on these would test prompt-copying, not triage.
_FEW_SHOT_CONTAMINATED_INDICES: frozenset[int] = frozenset({3, 13, 15})


def run_evaluation(
    findings: list[dict],
    labels: list[GroundTruthLabel],
    variants: list[str],
    models: list[str],
    n_trials: int = 5,
    skip_contaminated_few_shot: bool = True,
) -> dict:
    """Run N trials per (label, variant, model) cell and aggregate the outcomes.

    For each label in ``labels``, look up the matching finding in
    ``findings`` by ``label.finding_index``. For each variant in
    ``variants`` and each model in ``models``, call
    :func:`~src.triage_engine.triage_finding` ``n_trials`` times,
    capturing the model's verdict, confidence, reasoning, remediation,
    CWE check, latency, and any error.

    Trials for the (label, ``"few_shot"``) pair are skipped when
    ``skip_contaminated_few_shot=True`` and ``label.finding_index`` is
    in the few-shot contamination set ``{3, 13, 15}`` — those findings
    are embedded as worked examples in the few_shot prompt itself, so
    evaluating against them measures prompt-copying rather than triage
    skill. The skip is variant-only (does not depend on the model), so
    each (``"few_shot"``, model) cell skips the same set of labels.

    Args:
        findings: The full ``results`` array from
            ``data/semgrep_juiceshop.json``. Indexed by
            ``label.finding_index``.
        labels: Human-authored ground-truth labels to evaluate against.
        variants: Prompt-variant names to evaluate. Each must be a key
            in :data:`src.triage_engine.PROMPT_VARIANTS`. (Validation
            is deferred to the per-trial ``triage_finding`` call;
            unknown variants will surface as per-trial errors.)
        models: Model-provider names to evaluate. Each must be a key in
            :data:`src.triage_engine.MODEL_DISPATCH`. Same validation
            note as ``variants``.
        n_trials: Number of trials per (label, variant, model) cell.
            Defaults to ``5``.
        skip_contaminated_few_shot: If ``True`` (default), skip the
            (label, ``"few_shot"``) combination — across all models —
            when ``label.finding_index`` is in the contamination set.

    Returns:
        A dict with two top-level keys:

        * ``"trials"``: list of per-trial result dicts. Each contains
          ``finding_index``, ``check_id``, ``variant``, ``model``
          (model-provider name string), ``trial_number``,
          ``ground_truth`` (nested ``{verdict, confidence}``),
          ``model_output`` (nested ``{verdict, confidence, reasoning,
          remediation, cwe_confirmed}`` or ``None`` on error),
          ``match`` (bool or ``None`` on error), ``latency_seconds``,
          and ``error``. (Note: ``model`` is the provider name;
          ``model_output`` is the structured response from that
          provider. Renamed from ``model`` in the single-model
          version to avoid the naming collision.)
        * ``"summary"``: dict mapping each
          ``"{variant}__{model}"`` cell key to its aggregate stats
          (``n_trials_total``, ``n_trials_succeeded``,
          ``n_trials_errored``, ``match_rate``,
          ``verdict_distribution``, ``avg_confidence``,
          ``avg_latency_seconds``, ``skipped_contaminated_count``).
          Match-rate, average confidence, and average latency are
          computed over succeeded trials only; verdict distribution
          likewise.

    Raises:
        IndexError: If ``label.finding_index`` is out of range for
            ``findings``. Raised before any trials run, so a misaligned
            label set fails fast rather than producing a partial
            results file.
    """
    trials: list[dict[str, Any]] = []
    skipped_per_cell: dict[tuple[str, str], int] = {
        (variant, model): 0 for variant in variants for model in models
    }

    for label in labels:
        # Fail fast on misaligned indices rather than silently producing
        # partial results.
        finding = findings[label.finding_index]

        for variant in variants:
            # The contamination check is variant-only; the same labels
            # are skipped under every model.
            is_contaminated_pair = (
                skip_contaminated_few_shot
                and variant == "few_shot"
                and label.finding_index in _FEW_SHOT_CONTAMINATED_INDICES
            )

            for model in models:
                if is_contaminated_pair:
                    skipped_per_cell[(variant, model)] += 1
                    continue

                for trial_num in range(1, n_trials + 1):
                    trial: dict[str, Any] = {
                        "finding_index": label.finding_index,
                        "check_id": label.check_id,
                        "variant": variant,
                        "model": model,
                        "trial_number": trial_num,
                        "ground_truth": {
                            "verdict": label.verdict,
                            "confidence": label.confidence,
                        },
                        "model_output": None,
                        "match": None,
                        "latency_seconds": None,
                        "error": None,
                    }

                    t0 = time.perf_counter()
                    try:
                        verdict: TriageVerdict = triage_finding(
                            finding, variant=variant, model=model
                        )
                        trial["latency_seconds"] = time.perf_counter() - t0
                        trial["model_output"] = {
                            "verdict": verdict.verdict,
                            "confidence": verdict.confidence,
                            "reasoning": verdict.reasoning,
                            "remediation": verdict.remediation,
                            "cwe_confirmed": verdict.cwe_confirmed,
                        }
                        trial["match"] = verdict.verdict == label.verdict
                    except Exception as exc:
                        trial["latency_seconds"] = time.perf_counter() - t0
                        trial["error"] = f"{type(exc).__name__}: {exc}"

                    trials.append(trial)

    summary: dict[str, dict[str, Any]] = {}
    for variant in variants:
        for model in models:
            cell_key = f"{variant}__{model}"
            cell_trials = [
                t for t in trials
                if t["variant"] == variant and t["model"] == model
            ]
            succeeded = [t for t in cell_trials if t["error"] is None]
            errored = [t for t in cell_trials if t["error"] is not None]

            if succeeded:
                match_rate = sum(t["match"] for t in succeeded) / len(succeeded)
                avg_confidence = (
                    sum(t["model_output"]["confidence"] for t in succeeded)
                    / len(succeeded)
                )
                avg_latency = (
                    sum(t["latency_seconds"] for t in succeeded) / len(succeeded)
                )
                verdict_distribution = dict(
                    Counter(t["model_output"]["verdict"] for t in succeeded)
                )
            else:
                match_rate = 0.0
                avg_confidence = 0.0
                avg_latency = 0.0
                verdict_distribution = {}

            summary[cell_key] = {
                "n_trials_total": len(cell_trials),
                "n_trials_succeeded": len(succeeded),
                "n_trials_errored": len(errored),
                "match_rate": match_rate,
                "verdict_distribution": verdict_distribution,
                "avg_confidence": avg_confidence,
                "avg_latency_seconds": avg_latency,
                "skipped_contaminated_count": skipped_per_cell[(variant, model)],
            }

    return {"trials": trials, "summary": summary}
