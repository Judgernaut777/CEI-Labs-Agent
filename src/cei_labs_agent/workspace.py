"""Filesystem sandbox helpers for the notes workspace.

Provides a traversal-safe path join and a helper that guarantees the
notes directory exists. All note file access must flow through
:func:`safe_join` so that user- or model-supplied filenames cannot escape
the sandbox.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from .config import notes_dir


def safe_join(base: Path, name: str) -> Path:
    """Join ``name`` onto ``base``, rejecting absolute paths and traversal.

    Args:
        base: The sandbox root directory the result must stay within.
        name: A bare filename (no directory components, no ``..``).

    Returns:
        The resolved absolute path inside ``base``.

    Raises:
        ValueError: If ``name`` is empty, absolute, contains a drive or
            root, or would escape ``base`` via ``..`` traversal.
    """
    if not name or not name.strip():
        raise ValueError("empty filename")

    # Reject anything that looks absolute on either POSIX or Windows, or
    # that carries a drive/root component. This catches "/etc/passwd",
    # "C:\\Windows", "\\\\server\\share", etc.
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).is_absolute():
        raise ValueError(f"absolute path not allowed: {name}")
    if PureWindowsPath(name).drive:
        raise ValueError(f"drive component not allowed: {name}")

    # Reject explicit parent-directory traversal in any position.
    parts = PurePosixPath(name).parts
    if ".." in parts:
        raise ValueError(f"path traversal not allowed: {name}")

    base_resolved = base.resolve()
    candidate = (base_resolved / name).resolve()

    # Final defensive check: the resolved candidate must live under base.
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise ValueError(f"path escapes sandbox: {name}")

    return candidate


def ensure_notes_dir() -> Path:
    """Return the notes directory, creating it (and parents) if needed.

    Returns:
        The path to the notes directory, guaranteed to exist.
    """
    path = notes_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
