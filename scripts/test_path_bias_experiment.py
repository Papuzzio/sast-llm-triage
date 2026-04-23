"""Path-bias experiment: baseline vs. no_path_bias prompt on the ReDoS finding.

Session 3 observed that Gemini returned ``true_positive`` with 0.9
confidence on ``lib/codingChallenges.ts:76``, citing "juice-shop" in the
file path as evidence rather than any data-flow reasoning. This script
re-runs the same finding twice: once with the baseline prompt, and once
with an added instruction telling the model to ignore paths and project
names. The side-by-side output makes it easy to see whether the bias is
steerable via prompt wording alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running directly: `python scripts/test_path_bias_experiment.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.triage_engine import triage_finding

FINDINGS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "semgrep_juiceshop.json"
)

SEPARATOR = "=" * 72


def _run_and_print(finding: dict, variant: str) -> None:
    print(SEPARATOR)
    print(f"Variant: {variant}")
    print(SEPARATOR)

    verdict = triage_finding(finding, variant=variant)

    print(f"verdict:    {verdict.verdict}")
    print(f"confidence: {verdict.confidence}")
    print()
    print("reasoning:")
    print(verdict.reasoning)
    print()


def main() -> None:
    with FINDINGS_PATH.open() as f:
        data = json.load(f)

    finding = data["results"][0]
    print(f"Finding: {finding['check_id']}")
    print(f"File:    {finding['path']}")
    print(f"Range:   lines {finding['start']['line']}-{finding['end']['line']}")
    print()

    _run_and_print(finding, variant="baseline")
    print()
    print("#" * 72)
    print("#" + " " * 30 + "SWITCHING VARIANT" + " " * 23 + "#")
    print("#" * 72)
    print()
    _run_and_print(finding, variant="no_path_bias")


if __name__ == "__main__":
    main()
