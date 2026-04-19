"""Thin wrapper around the google-genai SDK for Gemini API calls."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai

# Load .env once at import time so callers don't need to remember.
load_dotenv()

_MODEL = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    """Build a Gemini client, raising a clear error if the API key is missing."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and paste "
            "your real key, or export GEMINI_API_KEY in your shell."
        )
    return genai.Client(api_key=api_key)


def call_gemini(prompt: str) -> str:
    """Send `prompt` to Gemini and return the response text."""
    client = _get_client()
    response = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
    )
    return response.text
