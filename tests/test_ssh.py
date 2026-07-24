"""Tests for the SSH exec tool (cei_labs_agent.tools.ssh.ssh_exec).

All tests are fully offline: paramiko.SSHClient is monkeypatched with a fake
that returns scripted stdout/stderr or raises on demand, so no network or real
SSH connection is ever attempted.
"""

from __future__ import annotations

import paramiko

from cei_labs_agent.config import SSHConfig
from cei_labs_agent.tools.ssh import ssh_exec


def _make_fake_client(
    stdout: bytes = b"",
    stderr: bytes = b"",
    connect_error: Exception | None = None,
    exec_error: Exception | None = None,
) -> type:
    """Build a fake SSHClient class returning scripted output or raising.

    Args:
        stdout: Bytes returned by the stdout channel's read().
        stderr: Bytes returned by the stderr channel's read().
        connect_error: If set, connect() raises this.
        exec_error: If set, exec_command() raises this.

    Returns:
        A class usable as a drop-in replacement for paramiko.SSHClient.
    """

    class _FakeStream:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False

        def set_missing_host_key_policy(self, policy: object) -> None:
            self.policy = policy

        def connect(self, *args: object, **kwargs: object) -> None:
            if connect_error is not None:
                raise connect_error

        def exec_command(self, command: str, timeout: object = None):
            if exec_error is not None:
                raise exec_error
            return (object(), _FakeStream(stdout), _FakeStream(stderr))

        def close(self) -> None:
            self.closed = True

    return _FakeClient


def _cfg() -> SSHConfig:
    """Return a throwaway SSH config (never actually connected)."""
    return SSHConfig(host="example.test", username="user", password="pw")


def test_combined_stdout_and_stderr(monkeypatch) -> None:
    """Combined output contains stdout followed by stderr, decoded."""
    monkeypatch.setattr(
        paramiko,
        "SSHClient",
        _make_fake_client(stdout=b"hello\n", stderr=b"world\n"),
    )
    result = ssh_exec(_cfg(), "echo hi", max_chars=4000, timeout=15)
    assert result == "hello\nworld\n"
    assert "hello" in result
    assert "world" in result
    assert "[truncated]" not in result


def test_truncation_marker(monkeypatch) -> None:
    """Output longer than max_chars is truncated with the marker appended."""
    monkeypatch.setattr(
        paramiko,
        "SSHClient",
        _make_fake_client(stdout=b"A" * 100, stderr=b""),
    )
    result = ssh_exec(_cfg(), "spew", max_chars=10, timeout=15)
    assert result == "A" * 10 + "\n...[truncated]"
    assert result.endswith("...[truncated]")


def test_no_truncation_when_within_limit(monkeypatch) -> None:
    """Output at or under max_chars is returned verbatim without a marker."""
    monkeypatch.setattr(
        paramiko,
        "SSHClient",
        _make_fake_client(stdout=b"short", stderr=b""),
    )
    result = ssh_exec(_cfg(), "echo short", max_chars=100, timeout=15)
    assert result == "short"
    assert "[truncated]" not in result


def test_connect_exception_becomes_ssh_error(monkeypatch) -> None:
    """A connection failure is returned as an 'ssh error:' string, not raised."""
    monkeypatch.setattr(
        paramiko,
        "SSHClient",
        _make_fake_client(connect_error=OSError("boom")),
    )
    result = ssh_exec(_cfg(), "whoami", max_chars=4000, timeout=15)
    assert isinstance(result, str)
    assert result.startswith("ssh error:")
    assert "boom" in result


def test_exec_exception_becomes_ssh_error(monkeypatch) -> None:
    """An exec failure is returned as an 'ssh error:' string, not raised."""
    monkeypatch.setattr(
        paramiko,
        "SSHClient",
        _make_fake_client(exec_error=RuntimeError("exec-fail")),
    )
    result = ssh_exec(_cfg(), "whoami", max_chars=4000, timeout=15)
    assert isinstance(result, str)
    assert result.startswith("ssh error:")
    assert "exec-fail" in result


def test_client_is_closed(monkeypatch) -> None:
    """The client is always closed, even on the happy path."""
    fake_cls = _make_fake_client(stdout=b"ok", stderr=b"")
    created: list[object] = []

    class _Tracking(fake_cls):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            created.append(self)

    monkeypatch.setattr(paramiko, "SSHClient", _Tracking)
    ssh_exec(_cfg(), "echo ok", max_chars=100, timeout=15)
    assert created, "SSHClient was never instantiated"
    assert all(getattr(client, "closed", False) for client in created)
