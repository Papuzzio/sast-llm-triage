"""Resolve API keys from environment variables or Streamlit secrets.

Both client modules (:mod:`src.gemini_client`, :mod:`src.claude_client`)
need to find their API keys from one of two sources:

* **Local development**: keys live in ``.env`` at the project root.
  ``python-dotenv`` populates ``os.environ`` when the client modules
  are imported.
* **Streamlit Community Cloud deployment**: there is no ``.env`` file;
  keys are injected through ``st.secrets`` instead.

This module centralizes the lookup logic so the same priority order
(environment first, Streamlit secrets second) is used by both clients.
"""

from __future__ import annotations

import os

# Placeholder value that ships in .env.example. Treated as "not set" in
# both sources so a half-configured .env doesn't shadow real secrets
# coming from Streamlit Cloud.
_PLACEHOLDER = "your_key_here"


def resolve_api_key(name: str) -> str | None:
    """Return the named API key from env or Streamlit secrets, or None.

    Lookup order:

    1. Process environment (populated by ``.env`` via ``load_dotenv``).
    2. Streamlit's ``st.secrets``, used by Streamlit Community Cloud.

    The placeholder string ``"your_key_here"`` is treated as missing in
    both sources.

    Args:
        name: The environment-variable name, also used as the
            Streamlit-secret name. E.g. ``"GEMINI_API_KEY"``.

    Returns:
        The resolved API key, or ``None`` if neither source has a real
        value.
    """
    value = os.getenv(name)
    if value and value != _PLACEHOLDER:
        return value

    # Try Streamlit secrets. Only available when running under Streamlit;
    # any failure (no streamlit installed, no secrets.toml, missing key)
    # maps to None and falls through to the caller's error handling.
    try:
        import streamlit as st

        secret = st.secrets.get(name)
        if secret and secret != _PLACEHOLDER:
            return secret
    except Exception:
        pass

    return None
