"""Thin wrapper around the google-genai SDK for Gemini API calls.

Exposes two entry points:

* :func:`call_gemini` — free-form prompt, returns the model's text.
* :func:`call_gemini_structured` — prompt + Pydantic schema, returns a
  validated Pydantic instance by asking Gemini for JSON that matches the
  schema.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig
from pydantic import BaseModel

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


def call_gemini_structured(
    prompt: str,
    schema: type[BaseModel],
) -> BaseModel:
    """Send `prompt` to Gemini with a Pydantic schema and return a validated instance.

    Uses Gemini's structured-output mode: the SDK converts ``schema`` into a
    JSON schema and instructs the model to return a JSON response that
    conforms to it. The model's response text is then parsed and validated
    through ``schema.model_validate_json``.

    Args:
        prompt: The user-facing prompt.
        schema: A Pydantic ``BaseModel`` subclass describing the expected
            response shape.

    Returns:
        An instance of ``schema`` populated from Gemini's JSON response.

    Raises:
        RuntimeError: If the Gemini API key is missing (see :func:`_get_client`).
        pydantic.ValidationError: If Gemini's response does not conform to
            ``schema``.
    """
    client = _get_client()
    response = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return schema.model_validate_json(response.text)
