"""Exercise the TriageVerdict schema: one valid case and two invalid cases."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly: `python scripts/test_triage_schema.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from src.triage_schema import TriageVerdict


def main() -> None:
    # --- Case 1: valid verdict --------------------------------------------
    print("=" * 72)
    print("Case 1: valid TriageVerdict")
    print("=" * 72)
    valid = TriageVerdict(
        verdict="false_positive",
        confidence=0.85,
        reasoning=(
            "The RegExp() call on line 76 is built from `challengeKey`, "
            "which originates from Juice Shop's own challenge definitions, "
            "not user input. The ReDoS rule (CWE-1333) fires on any "
            "non-literal regex, but here the source is trusted."
        ),
        remediation=(
            "Suppress with `// nosemgrep: detect-non-literal-regexp` and a "
            "comment noting challengeKey is trusted internal data."
        ),
        cwe_confirmed=True,
    )
    print(valid)
    print()
    print("As JSON:")
    print(valid.model_dump_json(indent=2))
    print()

    # --- Case 2: confidence out of range ----------------------------------
    print("=" * 72)
    print("Case 2: invalid — confidence=1.5")
    print("=" * 72)
    try:
        TriageVerdict(
            verdict="true_positive",
            confidence=1.5,
            reasoning=(
                "User-controlled input flows directly into a SQL query "
                "with no parameterization, enabling classic SQL injection."
            ),
            remediation="Use parameterized queries via Sequelize's built-in binding.",
            cwe_confirmed=True,
        )
    except ValidationError as e:
        print(e)
    print()

    # --- Case 3: verdict not in the allowed literal set -------------------
    print("=" * 72)
    print('Case 3: invalid — verdict="maybe"')
    print("=" * 72)
    try:
        TriageVerdict(
            verdict="maybe",  # type: ignore[arg-type]
            confidence=0.5,
            reasoning=(
                "The finding is ambiguous because the sink is reachable "
                "only from an admin-authenticated route."
            ),
            remediation="Need to confirm whether admin auth is enforced upstream.",
            cwe_confirmed=False,
        )
    except ValidationError as e:
        print(e)


if __name__ == "__main__":
    main()
