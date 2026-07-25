"""Tests for OllamaModelSource request-body construction (offline).

httpx.Client is replaced with a fake that captures the posted JSON and returns
a canned chat response, so no Ollama server is contacted.
"""

from __future__ import annotations

import cei_labs_agent.model_source as ms
from cei_labs_agent.model_source import GenerateRequest, OllamaModelSource


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Captures the last posted body into the class-level ``last_body``."""

    last_body: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def post(self, url: str, json: dict) -> _FakeResponse:
        type(self).last_body = json
        return _FakeResponse({"message": {"content": '{"action":"list_notes"}'}})


def _req(**kw) -> GenerateRequest:
    base = dict(messages=[{"role": "user", "content": "hi"}], model="qwen3:4b",
                num_ctx=8192, num_predict=768)
    base.update(kw)
    return GenerateRequest(**base)


def test_format_passed_through_when_set(monkeypatch) -> None:
    monkeypatch.setattr(ms.httpx, "Client", _FakeClient)
    schema = {"type": "object", "properties": {"action": {"type": "string"}}}
    OllamaModelSource().generate(_req(format=schema))
    assert _FakeClient.last_body["format"] == schema


def test_format_absent_when_none(monkeypatch) -> None:
    monkeypatch.setattr(ms.httpx, "Client", _FakeClient)
    _FakeClient.last_body = None
    OllamaModelSource().generate(_req(format=None))
    assert "format" not in _FakeClient.last_body


def test_think_flag_forwarded(monkeypatch) -> None:
    monkeypatch.setattr(ms.httpx, "Client", _FakeClient)
    OllamaModelSource().generate(_req(think=True))
    assert _FakeClient.last_body["think"] is True
