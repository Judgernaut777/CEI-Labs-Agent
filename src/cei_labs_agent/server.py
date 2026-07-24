"""FastAPI application exposing the CEI Labs Agent to the local web UI.

The server wires the static single-page UI to the agent runtime: it reports
system/RAM and Ollama status, serves the annotated model catalogue, persists a
small configuration file, tests SSH targets, streams model pulls, and streams
the agent's act -> tool -> act loop over Server-Sent Events. It is intentionally
stateless per chat request (a fresh :class:`AgentState` is built each time).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import psutil
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import models as models_mod
from . import model_source as model_source_mod
from .config import AppConfig, SSHConfig, default_runtime_config, load_config, save_config
from .graph import stream_agent
from .prompts import build_system_prompt
from .state import AgentState
from .tools.ssh import ssh_exec

__all__ = ["create_app", "app"]

STATIC_DIR: Path = Path(__file__).resolve().parent / "static"
INDEX_FILE: Path = STATIC_DIR / "index.html"


class ConfigUpdate(BaseModel):
    """Partial configuration update accepted by ``POST /api/config``.

    Attributes:
        model: New model tag, if changing.
        preset: New preset name, if changing.
        ssh: New SSH target, if changing.
    """

    model: str | None = None
    preset: str | None = None
    ssh: SSHConfig | None = None


class PullRequest(BaseModel):
    """Body for ``POST /api/pull``.

    Attributes:
        tag: The Ollama model tag to pull.
    """

    tag: str


class ChatRequest(BaseModel):
    """Body for ``POST /api/chat``.

    Attributes:
        message: The learner's message to the agent.
    """

    message: str


def _ram_gb(num_bytes: int) -> float:
    """Convert a byte count to gigabytes (decimal), rounded to one decimal.

    Decimal gigabytes are used so RAM figures line up with the model
    registry's ``estimate_ram_gb`` (which divides KV bytes by 1e9).

    Args:
        num_bytes: A byte count.

    Returns:
        The value in gigabytes, rounded to one decimal place.
    """
    return round(num_bytes / 1e9, 1)


def _system_info() -> dict:
    """Collect RAM and Ollama status for the current host and config.

    Returns:
        A dict with ``ram_total_gb``, ``ram_free_gb``, ``ollama_up``,
        ``ollama_host`` and ``local_models``.
    """
    cfg = load_config()
    vm = psutil.virtual_memory()
    host = cfg.ollama_host
    up = model_source_mod.ollama_up(host)
    local = model_source_mod.list_local_models(host) if up else []
    return {
        "ram_total_gb": _ram_gb(vm.total),
        "ram_free_gb": _ram_gb(vm.available),
        "ollama_up": up,
        "ollama_host": host,
        "local_models": local,
    }


def _resolve_preset(cfg: AppConfig) -> tuple[int, int, bool]:
    """Resolve ``(num_ctx, num_predict, think)`` for the configured model/preset.

    Falls back to the model's default preset, then its first preset, then a
    conservative built-in default when the model tag is unknown.

    Args:
        cfg: The loaded application configuration.

    Returns:
        A ``(num_ctx, num_predict, think)`` tuple.
    """
    spec = models_mod.get_model(cfg.model)
    if spec is None:
        return 8192, 768, False

    preset = next((p for p in spec.presets if p.name == cfg.preset), None)
    if preset is None:
        preset = next((p for p in spec.presets if p.name == spec.default_preset), None)
    if preset is None and spec.presets:
        preset = spec.presets[0]
    if preset is None:
        return 8192, 768, False
    return preset.num_ctx, preset.num_predict, preset.think


def _sse(payload: dict) -> str:
    """Serialise a payload as a single Server-Sent Events ``data:`` frame.

    ``json.dumps`` escapes embedded newlines, so each frame stays on one
    physical line as SSE requires.

    Args:
        payload: The JSON-serialisable event.

    Returns:
        A ready-to-write SSE frame string.
    """
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    Returns:
        A configured :class:`FastAPI` app with all endpoints and the static
        UI mount registered.
    """
    application = FastAPI(title="CEI Labs Agent", version="0.1.0")

    @application.get("/")
    def index() -> FileResponse:
        """Serve the single-page UI."""
        if not INDEX_FILE.exists():
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content={"error": "UI not built: static/index.html is missing."},
            )
        return FileResponse(INDEX_FILE)

    @application.get("/api/system")
    def api_system() -> dict:
        """Report RAM, Ollama reachability and locally installed models."""
        return _system_info()

    @application.get("/api/models")
    def api_models() -> dict:
        """Return the annotated model catalogue for the current host."""
        info = _system_info()
        free = info["ram_free_gb"]
        local = info["local_models"]
        return {
            "recommended": models_mod.recommend_model(free),
            "models": models_mod.models_view(free, local, include_hidden=False),
        }

    @application.get("/api/config")
    def api_get_config() -> dict:
        """Return the persisted config with the SSH password redacted."""
        cfg = load_config()
        data = cfg.model_dump()
        ssh_configured = cfg.ssh is not None
        if isinstance(data.get("ssh"), dict) and data["ssh"].get("password"):
            data["ssh"]["password"] = None
        data["ssh_configured"] = ssh_configured
        return data

    @application.post("/api/config")
    def api_set_config(update: ConfigUpdate) -> dict:
        """Merge a partial update into the persisted configuration."""
        current = load_config()
        if update.model is not None:
            current.model = update.model
        if update.preset is not None:
            current.preset = update.preset
        if update.ssh is not None:
            new_ssh = update.ssh
            # Preserve a stored password when the client sends none (the GET
            # endpoint redacts it, so a UI round-trip must not wipe it).
            if (
                new_ssh.password is None
                and current.ssh is not None
                and current.ssh.password
            ):
                new_ssh = new_ssh.model_copy(update={"password": current.ssh.password})
            current.ssh = new_ssh
        save_config(current)
        return {"ok": True}

    @application.post("/api/ssh/test")
    def api_ssh_test(ssh: SSHConfig) -> dict:
        """Run a trivial ``echo ok`` over SSH and report success."""
        result = ssh_exec(ssh, "echo ok", max_chars=500, timeout=ssh.timeout)
        ok = not result.startswith("ssh error:")
        return {"ok": ok, "message": result.strip()}

    @application.post("/api/pull")
    def api_pull(body: PullRequest) -> StreamingResponse:
        """Stream Ollama pull progress for a model tag as SSE."""
        cfg = load_config()
        host = cfg.ollama_host
        tag = body.tag

        def gen() -> Iterator[str]:
            try:
                for chunk in model_source_mod.pull_model(host, tag):
                    yield _sse(chunk)
            except Exception as exc:  # noqa: BLE001 - report, never crash the stream
                yield _sse({"error": str(exc)})
            yield _sse({"done": True})

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.post("/api/chat")
    def api_chat(body: ChatRequest) -> StreamingResponse:
        """Stream the agent's act -> tool -> act loop for one message as SSE."""
        cfg = load_config()
        runtime = default_runtime_config()
        runtime.allow_shell = cfg.ssh is not None

        num_ctx, num_predict, think = _resolve_preset(cfg)

        ssh_target: str | None = None
        if cfg.ssh is not None:
            ssh_target = f"{cfg.ssh.username}@{cfg.ssh.host}:{cfg.ssh.port}"

        system_prompt = build_system_prompt(runtime, ssh_target)
        st = AgentState(system_prompt=system_prompt, max_steps=runtime.max_steps)
        source = model_source_mod.OllamaModelSource(host=cfg.ollama_host)

        def gen() -> Iterator[str]:
            try:
                for event in stream_agent(
                    body.message,
                    st,
                    source,
                    runtime,
                    cfg.model,
                    num_ctx,
                    num_predict,
                    think,
                    cfg.ssh,
                ):
                    yield _sse(event)
            except Exception as exc:  # noqa: BLE001 - report, never crash the stream
                yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"done": True})

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Mount the static assets last so explicit routes above take precedence.
    # ``check_dir=False`` keeps import from failing before the UI is built.
    application.mount(
        "/",
        StaticFiles(directory=str(STATIC_DIR), html=True, check_dir=False),
        name="static",
    )

    return application


app = create_app()
