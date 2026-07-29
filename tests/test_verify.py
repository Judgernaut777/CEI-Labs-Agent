"""Tests for the ctf-agent-verify CLI (cei_labs_agent.verify).

All tests are fully offline: httpx.Client and paramiko.SSHClient are
monkeypatched with fakes, and the installed-package check is monkeypatched
via importlib.metadata, so no network, Ollama server, or SSH connection is
ever actually touched.
"""

from __future__ import annotations

import httpx
import paramiko
import pytest

from cei_labs_agent import verify


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


def _fake_httpx_client(tags: list[str] | None = None, up: bool = True):
    """Build a fake httpx.Client whose .get('/api/tags') reports Ollama state."""

    class _FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def get(self, url: str, *args: object, **kwargs: object) -> _FakeResponse:
            if not up:
                raise httpx.ConnectError("refused")
            models = [{"name": tag} for tag in (tags or [])]
            return _FakeResponse(status_code=200, payload={"models": models})

    return _FakeClient


def _fake_ssh_client(ok: bool = True):
    class _FakeStream:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

    class _FakeClient:
        def set_missing_host_key_policy(self, policy: object) -> None:
            pass

        def connect(self, *args: object, **kwargs: object) -> None:
            if not ok:
                raise OSError("refused")

        def exec_command(self, command: str, timeout: object = None):
            out = command.split("echo ", 1)[1].encode() if "echo " in command else b""
            return (object(), _FakeStream(out + b"\n"), _FakeStream(b""))

        def close(self) -> None:
            pass

    return _FakeClient


def test_ollama_down_reports_fail(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "Client", _fake_httpx_client(up=False))
    assert verify._check_ollama("http://localhost:11434") is False


def test_ollama_up_no_models_reports_fail(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "Client", _fake_httpx_client(tags=[]))
    assert verify._check_ollama("http://localhost:11434") is True
    assert verify._check_model("http://localhost:11434") == []


def test_ollama_up_with_model_reports_pass(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "Client", _fake_httpx_client(tags=["qwen3:4b"]))
    assert verify._check_model("http://localhost:11434") == ["qwen3:4b"]


def test_installed_package_found(monkeypatch) -> None:
    monkeypatch.setattr(verify.metadata, "version", lambda name: "0.1.0")
    assert verify._check_installed() == "0.1.0"


def test_installed_package_missing(monkeypatch) -> None:
    def _raise(name: str) -> str:
        raise verify.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(verify.metadata, "version", _raise)
    assert verify._check_installed() is None


def test_ssh_success(monkeypatch) -> None:
    monkeypatch.setattr(paramiko, "SSHClient", _fake_ssh_client(ok=True))
    assert verify._check_ssh("example.test", 22, "user", "pw") is True


def test_ssh_failure(monkeypatch) -> None:
    monkeypatch.setattr(paramiko, "SSHClient", _fake_ssh_client(ok=False))
    assert verify._check_ssh("example.test", 22, "user", "pw") is False


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Help me figure out level 1 of Bandit.", True),
        ("help me with krypton level 2", True),
        ("Help me with Natas level 0", True),
        (None, False),
        ("", False),
        ("what is bandit", False),  # no "help me" / no "level"
        ("Help me pick a laptop", False),  # no track name
    ],
)
def test_prompt_pattern(prompt: str | None, expected: bool) -> None:
    assert verify._check_prompt(prompt) is expected


def test_main_prints_flag_only_for_passing_checks(monkeypatch, capsys) -> None:
    monkeypatch.setattr(httpx, "Client", _fake_httpx_client(tags=["qwen3:4b"]))
    monkeypatch.setattr(verify.metadata, "version", lambda name: "0.1.0")
    monkeypatch.setattr(paramiko, "SSHClient", _fake_ssh_client(ok=True))

    failed = verify.main(
        [
            "--host",
            "example.test",
            "--user",
            "player",
            "--password",
            "pw",
            "--prompt",
            "Help me with Bandit level 1",
        ]
    )
    out = capsys.readouterr().out
    assert failed == 0
    assert verify.FLAG_OLLAMA in out
    assert verify.FLAG_MODEL in out
    assert verify.FLAG_INSTALLED in out
    assert verify.FLAG_SSH in out
    assert verify.FLAG_PROMPT in out
    assert "5/5 complete" in out


def test_main_reports_partial_progress(monkeypatch, capsys) -> None:
    monkeypatch.setattr(httpx, "Client", _fake_httpx_client(up=False))
    monkeypatch.setattr(verify.metadata, "version", lambda name: "0.1.0")

    failed = verify.main([])
    out = capsys.readouterr().out
    assert failed > 0
    assert verify.FLAG_OLLAMA not in out
    assert verify.FLAG_INSTALLED in out
    assert "keep going" in out
