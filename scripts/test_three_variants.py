"""Three-variant comparison: baseline vs. no_path_bias vs. few_shot.

Runs the same Semgrep finding (results[0], the ReDoS in
``lib/codingChallenges.ts``) through each of the three prompt variants
defined in :data:`src.triage_engine.PROMPT_VARIANTS`. The side-by-side
output makes it easy to eyeball whether the prompt-engineering changes
produce visibly different verdicts or reasoning styles.

Note: this is N=1 per variant. The Session 4 path-bias experiment
showed that single-shot comparisons of LLM prompts are noisy. Use this
script for spot-checking only, not for drawing conclusions about
variant performance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running directly: `python scripts/test_three_variants.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.triage_engine import triage_finding

FINDINGS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "semgrep_juiceshop.json"
)

VARIANTS = ["baseline", "no_path_bias", "few_shot"]

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

    for i, variant in enumerate(VARIANTS):
        if i > 0:
            print("#" * 72)
            label = f"  SWITCHING TO: {variant}  "
            pad = (72 - len(label) - 2) // 2
            print("#" + " " * pad + label + " " * (70 - len(label) - pad) + "#")
            print("#" * 72)
            print()
        _run_and_print(finding, variant=variant)


if __name__ == "__main__":
    main()
