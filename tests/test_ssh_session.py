"""Tests for the persistent SSH session (cei_labs_agent.tools.ssh.SSHSession).

Fully offline: paramiko.SSHClient is monkeypatched with a fake that serves a
scripted interactive shell, so no network or real SSH connection is attempted.
"""

from __future__ import annotations

import json

import paramiko
import pytest

from cei_labs_agent.config import SSHConfig
from cei_labs_agent.tools import ssh as ssh_mod
from cei_labs_agent.tools.ssh import SSHSession, session_exec, verify_host_key


def _cfg() -> SSHConfig:
    """Return a throwaway SSH config (never actually connected)."""
    return SSHConfig(host="example.test", username="user", password="pw", timeout=5)


class _FakeKey:
    def asbytes(self) -> bytes:
        return b"fake-host-key-v1"


class _FakeTransport:
    def get_remote_server_key(self):
        return _FakeKey()


class _FakeChannel:
    """A scripted interactive shell channel.

    ``script`` maps a command prefix to the bytes the shell 'prints' for it;
    every command ends with the __CEI_END_<code>__ marker, appended
    automatically unless ``hang`` is set (simulating a stuck command).
    """

    def __init__(self, script: dict[str, bytes] | None = None, hang: bool = False) -> None:
        self.script = script or {}
        self.hang = hang
        self.sent: list[str] = []
        self._queue: list[bytes] = []
        self.closed = False
        self.timeout = None

    def settimeout(self, t) -> None:
        self.timeout = t

    def send(self, data: str) -> None:
        self.sent.append(data)
        if self.hang and "printf" in data:
            return  # never answer -> read side times out
        for prefix, out in self.script.items():
            if data.startswith(prefix):
                self._queue.append(out + b"__CEI_END_0__\n")
                return
        if "printf" in data:
            self._queue.append(b"__CEI_END_0__\n")

    def recv(self, n: int) -> bytes:
        if not self._queue:
            if self.hang:
                raise TimeoutError("timed out")
            return b""  # drained
        return self._queue.pop(0)

    def close(self) -> None:
        self.closed = True


def _make_fake_client(channel: _FakeChannel, connect_error: Exception | None = None):
    created: list[object] = []

    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False
            created.append(self)

        def set_missing_host_key_policy(self, policy) -> None:
            self.policy = policy

        def connect(self, *args, **kwargs) -> None:
            if connect_error is not None:
                raise connect_error

        def get_transport(self):
            return _FakeTransport()

        def invoke_shell(self, term: str = "", width: int = 0, height: int = 0):
            return channel

        def exec_command(self, command: str, timeout=None):
            raise AssertionError("session must not use exec_command")

        def close(self) -> None:
            self.closed = True

    return _FakeClient, created


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point the TOFU store at a temp dir and clear the session cache."""
    monkeypatch.setenv("CEI_LABS_HOME", str(tmp_path))
    ssh_mod._sessions.clear()
    yield
    ssh_mod._sessions.clear()


def test_session_reuses_one_connection(monkeypatch) -> None:
    """Multiple exec calls share a single TCP connection/shell."""
    chan = _FakeChannel({"ls": b"level1  level2\n"})
    fake_cls, created = _make_fake_client(chan)
    monkeypatch.setattr(paramiko, "SSHClient", fake_cls)

    s = SSHSession(_cfg())
    assert s.exec("ls") == "level1  level2"
    assert s.exec("ls") == "level1  level2"
    assert len(created) == 1  # one client, not one per command


def test_session_returns_output_without_marker(monkeypatch) -> None:
    chan = _FakeChannel({"cat readme": b"the password is xyz\n"})
    fake_cls, _ = _make_fake_client(chan)
    monkeypatch.setattr(paramiko, "SSHClient", fake_cls)

    s = SSHSession(_cfg())
    out = s.exec("cat readme")
    assert "the password is xyz" in out
    assert "__CEI_END_" not in out


def test_session_timeout_is_reported_not_raised(monkeypatch) -> None:
    chan = _FakeChannel(hang=True)
    fake_cls, _ = _make_fake_client(chan)
    monkeypatch.setattr(paramiko, "SSHClient", fake_cls)

    s = SSHSession(_cfg())
    out = s.exec("sleep 999")
    assert "timed out" in out


def test_connect_failure_becomes_ssh_error(monkeypatch) -> None:
    fake_cls, _ = _make_fake_client(_FakeChannel(), connect_error=OSError("refused"))
    monkeypatch.setattr(paramiko, "SSHClient", fake_cls)

    s = SSHSession(_cfg())
    out = s.exec("whoami")
    assert out.startswith("ssh error:")
    assert "refused" in out


def test_session_exec_caches_per_target(monkeypatch) -> None:
    chan = _FakeChannel({"pwd": b"/home/user\n"})
    fake_cls, created = _make_fake_client(chan)
    monkeypatch.setattr(paramiko, "SSHClient", fake_cls)

    session_exec(_cfg(), "pwd")
    session_exec(_cfg(), "pwd")
    assert len(created) == 1


def test_tofu_records_then_accepts_same_key(tmp_path, monkeypatch) -> None:
    assert verify_host_key(_cfg(), "fp-one") is None  # first sight: record
    assert verify_host_key(_cfg(), "fp-one") is None  # same key: ok
    stored = json.loads((tmp_path / "known_hosts.json").read_text())
    assert stored["user@example.test:22"] == "fp-one"


def test_tofu_rejects_changed_key(tmp_path, monkeypatch) -> None:
    assert verify_host_key(_cfg(), "fp-one") is None
    err = verify_host_key(_cfg(), "fp-two")
    assert err is not None
    assert err.startswith("ssh error:")
    assert "CHANGED" in err


def test_tofu_enforced_on_session_connect(tmp_path, monkeypatch) -> None:
    """A session whose host key changes between connects is refused."""
    chan = _FakeChannel({"id": b"uid=1000\n"})
    fake_cls, _ = _make_fake_client(chan)
    monkeypatch.setattr(paramiko, "SSHClient", fake_cls)

    # Pre-seed the store with a DIFFERENT key than the fake presents.
    store = tmp_path / "known_hosts.json"
    store.write_text(json.dumps({"user@example.test:22": "some-other-key"}))

    s = SSHSession(_cfg())
    out = s.exec("id")
    assert out.startswith("ssh error:")
    assert "CHANGED" in out
