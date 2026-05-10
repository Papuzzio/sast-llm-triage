"""Thin wrapper around the Anthropic SDK for Claude API calls.

Parallel structure to :mod:`src.gemini_client`. Exposes two entry points:

* :func:`call_claude` — free-form prompt, returns the model's text.
* :func:`call_claude_structured` — prompt + Pydantic schema, returns a
  validated Pydantic instance by forcing Claude to emit its response
  through a single tool call whose ``input_schema`` is the Pydantic
  schema's JSON schema.

Having a second provider lets the eval harness compare prompt-variant
behavior across model families. Anything in this module should remain
substitutable with :mod:`src.gemini_client` from the caller's POV — same
function shapes, same error semantics on a missing API key.
"""

from __future__ import annotations

import os

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env once at import time so callers don't need to remember. Use
# override=True so .env wins over stale shell vars (e.g. an empty
# ANTHROPIC_API_KEY exported by Claude for Desktop, which would
# otherwise silently shadow the real key in .env).
load_dotenv(override=True)

_MODEL = "claude-haiku-4-5"

# Name of the synthetic tool we force Claude to call when we want a
# structured response. The name is arbitrary but must match between the
# tool definition and the ``tool_choice`` constraint.
_STRUCTURED_TOOL_NAME = "submit_verdict"


def _get_client() -> Anthropic:
    """Build an Anthropic client, raising a clear error if the API key is missing."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and "
            "paste your real key, or export ANTHROPIC_API_KEY in your shell."
        )
    return Anthropic(api_key=api_key)


def call_claude(prompt: str) -> str:
    """Send `prompt` to Claude and return the response text."""
    client = _get_client()
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def call_claude_structured(
    prompt: str,
    schema: type[BaseModel],
) -> BaseModel:
    """Send `prompt` to Claude with a Pydantic schema and return a validated instance.

    Uses Anthropic's tool-use mechanism for structured output: the SDK is
    given a single tool whose ``input_schema`` is ``schema``'s JSON
    schema, and ``tool_choice`` is set to force the model to emit a
    ``tool_use`` block calling that tool. The block's ``input`` is then
    validated through ``schema.model_validate``.

    Args:
        prompt: The user-facing prompt.
        schema: A Pydantic ``BaseModel`` subclass describing the expected
            response shape.

    Returns:
        An instance of ``schema`` populated from Claude's tool-call input.

    Raises:
        RuntimeError: If the Anthropic API key is missing (see
            :func:`_get_client`), or if Claude returns no ``tool_use``
            block despite being forced to.
        pydantic.ValidationError: If the tool input does not conform to
            ``schema``.
    """
    client = _get_client()
    tool = {
        "name": _STRUCTURED_TOOL_NAME,
        "description": (
            "Submit the structured triage verdict. The arguments must "
            "conform exactly to the input schema."
        ),
        "input_schema": schema.model_json_schema(),
    }
    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        tools=[tool],
        tool_choice={"type": "tool", "name": _STRUCTURED_TOOL_NAME},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == _STRUCTURED_TOOL_NAME:
            return schema.model_validate(block.input)
    raise RuntimeError(
        f"Claude did not return a tool_use block named "
        f"{_STRUCTURED_TOOL_NAME!r} despite forced tool_choice; "
        f"response.content blocks: "
        f"{[getattr(b, 'type', '?') for b in response.content]}"
    )
