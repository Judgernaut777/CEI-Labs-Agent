"""Tests for the sandboxed notes tool and workspace path safety.

Each test points CEI_LABS_HOME at a fresh temporary directory so config and
notes stay isolated and offline.
"""

from __future__ import annotations

import pytest

from cei_labs_agent.tools.notes import list_notes, read_notes, write_notes
from cei_labs_agent.workspace import ensure_notes_dir, safe_join


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    """Point CEI_LABS_HOME at a per-test temporary directory."""
    monkeypatch.setenv("CEI_LABS_HOME", str(tmp_path))
    return tmp_path


def test_list_empty_reports_no_notes() -> None:
    """A fresh sandbox reports that no notes exist yet."""
    assert list_notes() == "no notes yet"


def test_write_read_list_round_trip() -> None:
    """Writing then reading a note round-trips, and it appears in the listing."""
    content = "level0 password: abc123"
    result = write_notes("bandit.md", content)
    assert result == f"wrote {len(content)} chars to bandit.md"

    assert read_notes("bandit.md") == content

    listing = list_notes()
    assert "bandit.md" in listing.splitlines()


def test_read_missing_note() -> None:
    """Reading a note that does not exist reports a not-found message."""
    assert read_notes("missing.md") == "note not found: missing.md"


def test_read_rejects_traversal() -> None:
    """A traversal filename is rejected as invalid rather than escaping."""
    assert read_notes("../secret.md") == "invalid filename"


def test_write_rejects_absolute_path() -> None:
    """An absolute filename is rejected as invalid rather than escaping."""
    assert write_notes("/etc/passwd", "pwned") == "invalid filename"


def test_ensure_notes_dir_exists(_home) -> None:
    """ensure_notes_dir creates and returns the notes directory."""
    path = ensure_notes_dir()
    assert path.exists()
    assert path.is_dir()
    assert path.name == "notes"
    assert path.parent.resolve() == _home.resolve()


def test_safe_join_accepts_bare_name(_home) -> None:
    """A bare filename joins to a path inside the base directory."""
    base = _home
    joined = safe_join(base, "ok.md")
    assert joined.name == "ok.md"
    assert base.resolve() in joined.parents


def test_safe_join_rejects_parent_traversal(_home) -> None:
    """A '..' component raises ValueError."""
    with pytest.raises(ValueError):
        safe_join(_home, "../x")


def test_safe_join_rejects_absolute(_home) -> None:
    """An absolute path raises ValueError."""
    with pytest.raises(ValueError):
        safe_join(_home, "/etc/passwd")
