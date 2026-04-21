"""Read source-code snippets around a finding's location.

Semgrep's OSS engine omits the `lines` field in JSON output (it shows
``"requires login"`` for registry-auth'd users only), so we have to re-read
the snippet from disk ourselves. This module pulls a window of lines around
a finding's reported range, with a configurable number of context lines
above and below, and prefixes each line with its 1-indexed line number.

The output is intended to be passed verbatim into an LLM triage prompt so
the model can reason about the finding with the surrounding code visible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


def read_snippet(
    path: PathLike,
    start_line: int,
    end_line: int,
    context: int = 3,
) -> str:
    """Return a numbered code snippet centered on ``start_line..end_line``.

    The returned snippet spans from ``max(1, start_line - context)`` to
    ``min(total_lines, end_line + context)``, inclusive. Each line is
    prefixed with its 1-indexed line number followed by a tab, e.g.
    ``"73\\tconst something = ..."``. Lines are joined with ``"\\n"`` and no
    trailing newline is appended.

    Args:
        path: Filesystem path to the source file (``str`` or ``Path``).
        start_line: 1-indexed first line of the finding's range.
        end_line: 1-indexed last line of the finding's range (inclusive).
        context: Extra lines to include above and below the range.
            Defaults to ``3``.

    Returns:
        A string containing the numbered snippet.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``start_line`` or ``end_line`` is out of range
            (non-positive, beyond EOF, or ``end_line < start_line``), or
            if ``context`` is negative.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(
            f"Cannot read snippet: no file at {file_path!s}"
        )

    if context < 0:
        raise ValueError(
            f"context must be >= 0, got {context}"
        )

    # splitlines() drops the trailing newline on each line, which is what we
    # want for the numbered output.
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total_lines = len(lines)

    if total_lines == 0:
        raise ValueError(
            f"Cannot read snippet: file is empty ({file_path!s})"
        )

    if start_line < 1 or start_line > total_lines:
        raise ValueError(
            f"start_line {start_line} is out of range for {file_path!s} "
            f"(file has {total_lines} lines)"
        )
    if end_line < 1 or end_line > total_lines:
        raise ValueError(
            f"end_line {end_line} is out of range for {file_path!s} "
            f"(file has {total_lines} lines)"
        )
    if end_line < start_line:
        raise ValueError(
            f"end_line ({end_line}) must be >= start_line ({start_line})"
        )

    first = max(1, start_line - context)
    last = min(total_lines, end_line + context)

    # Slice is 0-indexed; lines are 1-indexed.
    window = lines[first - 1 : last]
    numbered = [f"{first + i}\t{line}" for i, line in enumerate(window)]
    return "\n".join(numbered)
