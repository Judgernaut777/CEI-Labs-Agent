"""Sandboxed notes storage tool.

Read, write, and list plain-text notes under the agent's notes directory.
Every filename is validated through :func:`safe_join` so the model cannot
read or write outside the sandbox.
"""

from __future__ import annotations

from ..workspace import ensure_notes_dir, safe_join


def read_notes(filename: str) -> str:
    """Read a note file's contents.

    Args:
        filename: Bare filename of the note to read.

    Returns:
        The file contents, ``"note not found: <filename>"`` if missing, or
        ``"invalid filename"`` if the name escapes the sandbox.
    """
    base = ensure_notes_dir()
    try:
        path = safe_join(base, filename)
    except ValueError:
        return "invalid filename"
    if not path.exists():
        return f"note not found: {filename}"
    return path.read_text(encoding="utf-8")


def write_notes(filename: str, content: str) -> str:
    """Write content to a note file, overwriting any existing content.

    Args:
        filename: Bare filename of the note to write.
        content: Text content to store.

    Returns:
        ``"wrote <n> chars to <filename>"`` on success, or
        ``"invalid filename"`` if the name escapes the sandbox.
    """
    base = ensure_notes_dir()
    try:
        path = safe_join(base, filename)
    except ValueError:
        return "invalid filename"
    path.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {filename}"


def list_notes() -> str:
    """List the note filenames currently stored in the sandbox.

    Returns:
        Newline-joined filenames sorted alphabetically, or
        ``"no notes yet"`` if the sandbox contains no note files.
    """
    base = ensure_notes_dir()
    names = sorted(p.name for p in base.iterdir() if p.is_file())
    if not names:
        return "no notes yet"
    return "\n".join(names)
