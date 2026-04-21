"""End-to-end smoke test: triage the first Semgrep finding via Gemini."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running directly: `python scripts/test_triage_engine.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.triage_engine import triage_finding

FINDINGS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "semgrep_juiceshop.json"
)


def main() -> None:
    with FINDINGS_PATH.open() as f:
        data = json.load(f)

    finding = data["results"][0]
    print(f"check_id: {finding['check_id']}")
    print(f"path:     {finding['path']}")
    print("-" * 72)

    verdict = triage_finding(finding)
    print(verdict.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
