"""Smoke test: pull the first Semgrep finding and print its code snippet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running directly: `python scripts/test_snippet_reader.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.snippet_reader import read_snippet

FINDINGS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "semgrep_juiceshop.json"
)


def main() -> None:
    with FINDINGS_PATH.open() as f:
        data = json.load(f)

    finding = data["results"][0]
    path = finding["path"]
    start_line = finding["start"]["line"]
    end_line = finding["end"]["line"]

    print(f"Finding: {finding['check_id']}")
    print(f"File:    {path}")
    print(f"Range:   lines {start_line}-{end_line}")
    print("-" * 72)

    snippet = read_snippet(path, start_line, end_line, context=3)
    print(snippet)


if __name__ == "__main__":
    main()
