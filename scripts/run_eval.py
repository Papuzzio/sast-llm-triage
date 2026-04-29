"""Run the evaluation harness against the labeled findings + 3 prompt variants.

Loads:
- ``data/semgrep_juiceshop.json`` (the 26 Semgrep findings)
- ``eval/ground_truth.json`` (human-authored labels, parsed via
  :class:`~src.label_schema.GroundTruthLabel`)

Calls :func:`~src.eval_harness.run_evaluation` with all three prompt
variants and N=5 trials per (label, variant) pair, then:

- Writes the full per-trial results + summary to
  ``eval/results_<UTC YYYYMMDD-HHMMSS>.json``.
- Prints a plain-text summary table to stdout.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running directly: `python scripts/run_eval.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval_harness import run_evaluation
from src.label_schema import GroundTruthLabel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINDINGS_PATH = PROJECT_ROOT / "data" / "semgrep_juiceshop.json"
LABELS_PATH = PROJECT_ROOT / "eval" / "ground_truth.json"
RESULTS_DIR = PROJECT_ROOT / "eval"

VARIANTS = ["baseline", "no_path_bias", "few_shot"]
N_TRIALS = 5


def _load_findings() -> list[dict]:
    with FINDINGS_PATH.open() as f:
        return json.load(f)["results"]


def _load_labels() -> list[GroundTruthLabel]:
    with LABELS_PATH.open() as f:
        raw = json.load(f)
    return [GroundTruthLabel.model_validate(label) for label in raw["labels"]]


def _print_summary_table(summary: dict) -> None:
    headers = [
        "variant",
        "n_succeeded",
        "n_errored",
        "match_rate",
        "avg_confidence",
        "avg_latency_seconds",
        "skipped_contaminated",
    ]
    rows: list[list[str]] = []
    for variant, stats in summary.items():
        rows.append(
            [
                variant,
                str(stats["n_trials_succeeded"]),
                str(stats["n_trials_errored"]),
                f"{stats['match_rate'] * 100:.1f}%",
                f"{stats['avg_confidence']:.3f}",
                f"{stats['avg_latency_seconds']:.2f}",
                str(stats["skipped_contaminated_count"]),
            ]
        )

    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    def _format_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(cells, widths))

    print(_format_row(headers))
    print(_format_row(["-" * w for w in widths]))
    for row in rows:
        print(_format_row(row))


def main() -> None:
    findings = _load_findings()
    labels = _load_labels()

    print(f"Findings: {len(findings)} total")
    print(f"Labels:   {len(labels)} (will evaluate)")
    print(f"Variants: {VARIANTS}")
    print(f"N trials per (label, variant): {N_TRIALS}")
    print()

    result = run_evaluation(
        findings=findings,
        labels=labels,
        variants=VARIANTS,
        n_trials=N_TRIALS,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_path = RESULTS_DIR / f"results_{timestamp}.json"
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )

    rel_path = output_path.relative_to(PROJECT_ROOT)
    print(f"Wrote {rel_path} ({len(result['trials'])} trials)")
    print()
    _print_summary_table(result["summary"])


if __name__ == "__main__":
    main()
