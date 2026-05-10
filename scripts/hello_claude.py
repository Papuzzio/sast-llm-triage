"""Smoke test: verify the Claude pipeline is wired up end-to-end."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly: `python scripts/hello_claude.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.claude_client import call_claude


def main() -> None:
    prompt = "Respond with exactly this text and nothing else: pipeline works"
    response = call_claude(prompt)
    print(response)


if __name__ == "__main__":
    main()
