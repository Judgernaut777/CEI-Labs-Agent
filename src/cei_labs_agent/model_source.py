"""Model source abstractions for the agent loop.

Defines the request/response models exchanged with a language model, a
``ModelSource`` protocol, a concrete ``OllamaModelSource`` that talks to a local
Ollama server via its native ``/api/chat`` endpoint, small helpers for probing
and pulling Ollama models, and a scripted ``StubModelSource`` for tests.
"""

from __future__ import annotations

import json
import re
from typing import Iterator, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class GenerateRequest(BaseModel):
    """A single chat-completion request to a model source.

    Attributes:
        messages: Chat messages as ``{"role", "content"}`` dicts.
        model: Model tag to run (e.g. ``"qwen3:4b"``).
        num_ctx: Context window size in tokens.
        num_predict: Maximum number of tokens to generate.
        think: Whether to enable the model's thinking mode.
        temperature: Sampling temperature.
        format: Optional JSON schema (or ``"json"``) passed to Ollama's
            ``format`` field to grammar-constrain the output. ``None`` leaves
            generation unconstrained. Must be ``None`` whenever ``think`` is
            true -- a thinking model emits ``<think>`` prose that cannot
            satisfy a strict JSON schema.
    """

    messages: list[dict]
    model: str
    num_ctx: int
    num_predict: int
    think: bool = False
    temperature: float = 0.3
    format: dict | str | None = None


class GenerateResponse(BaseModel):
    """A model source's reply.

    Attributes:
        text: The assistant's message content (thinking blocks stripped).
        raw: The raw provider payload, when available.
    """

    text: str
    raw: dict | None = None


@runtime_checkable
class ModelSource(Protocol):
    """Anything that can turn a ``GenerateRequest`` into a ``GenerateResponse``."""

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        """Generate a completion for ``req``."""
        ...


def _strip_think(text: str) -> str:
    """Remove any ``<think>...</think>`` blocks from ``text`` defensively."""
    return _THINK_BLOCK_RE.sub("", text).strip()


class OllamaModelSource:
    """A ``ModelSource`` backed by a local Ollama server's ``/api/chat`` API."""

    def __init__(self, host: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        """Initialise the source.

        Args:
            host: Base URL of the Ollama server.
            timeout: Per-request timeout in seconds.
        """
        self.host = host.rstrip("/")
        self.timeout = timeout

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        """Run a non-streaming chat completion against Ollama.

        Args:
            req: The generation request.

        Returns:
            The assistant reply with any thinking block stripped.
        """
        body = {
            "model": req.model,
            "messages": req.messages,
            "stream": False,
            "think": req.think,
            "options": {
                "num_ctx": req.num_ctx,
                "num_predict": req.num_predict,
                "temperature": req.temperature,
            },
        }
        # Structured-output constraint: when a schema is supplied, Ollama
        # grammar-constrains the decode so the reply is guaranteed to be a
        # single valid JSON object matching it. Omitted entirely when None so
        # unconstrained (e.g. thinking) generation is unaffected.
        if req.format is not None:
            body["format"] = req.format
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.host}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data.get("message", {}).get("content", "")
        return GenerateResponse(text=_strip_think(text), raw=data)


def ollama_up(host: str = "http://localhost:11434", timeout: float = 2.0) -> bool:
    """Return True if the Ollama server responds on ``/api/tags``.

    Args:
        host: Base URL of the Ollama server.
        timeout: Request timeout in seconds.

    Returns:
        True if the server is reachable and returns a success status.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{host.rstrip('/')}/api/tags")
        return resp.status_code == 200
    except Exception:
        return False


def list_local_models(host: str = "http://localhost:11434") -> list[str]:
    """List locally installed Ollama model tags.

    Args:
        host: Base URL of the Ollama server.

    Returns:
        A list of model tags, or an empty list on any error.
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{host.rstrip('/')}/api/tags")
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []
    models = data.get("models", []) or []
    tags: list[str] = []
    for entry in models:
        tag = entry.get("name") or entry.get("model")
        if tag:
            tags.append(tag)
    return tags


def pull_model(host: str, tag: str) -> Iterator[dict]:
    """Stream ``ollama pull`` progress for ``tag``.

    Args:
        host: Base URL of the Ollama server.
        tag: The model tag to pull.

    Yields:
        Each JSON progress line as a dict; on error a ``{"error": ...}`` dict.
    """
    url = f"{host.rstrip('/')}/api/pull"
    body = {"model": tag, "stream": True}
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream("POST", url, json=body) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:  # noqa: BLE001 - surface the failure to the caller
        yield {"error": str(exc)}


class StubModelSource:
    """A scripted ``ModelSource`` for tests; returns queued strings in order."""

    def __init__(self, scripted: list[str]) -> None:
        """Initialise the stub.

        Args:
            scripted: Replies to hand out on successive ``generate`` calls.
        """
        self.scripted = list(scripted)
        self.calls: list[GenerateRequest] = []

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        """Return the next scripted reply.

        Args:
            req: The generation request (recorded for inspection).

        Returns:
            The next queued reply.

        Raises:
            IndexError: If no scripted replies remain.
        """
        self.calls.append(req)
        if not self.scripted:
            raise IndexError("StubModelSource exhausted: no scripted replies left")
        return GenerateResponse(text=self.scripted.pop(0), raw=None)
