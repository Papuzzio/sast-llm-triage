"""Smoke test: verify the Gemini pipeline is wired up end-to-end."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly: `python scripts/hello_gemini.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gemini_client import call_gemini


def main() -> None:
    prompt = "Respond with exactly this text and nothing else: pipeline works"
    response = call_gemini(prompt)
    print(response)


if __name__ == "__main__":
    main()
