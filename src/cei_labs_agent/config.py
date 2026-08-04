"""Filesystem paths and persisted application configuration.

The base directory honours the ``CEI_LABS_HOME`` environment variable (used by
tests to point at a temporary directory); otherwise it defaults to
``~/.cei-labs-agent``. All path helpers read the environment at call time so
that per-test overrides take effect.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

__all__ = [
    "config_dir",
    "config_path",
    "notes_dir",
    "RuntimeConfig",
    "SSHConfig",
    "AppConfig",
    "default_runtime_config",
    "load_config",
    "save_config",
]


def config_dir() -> Path:
    """Return the base configuration directory.

    Returns:
        ``$CEI_LABS_HOME`` when set, otherwise ``~/.cei-labs-agent``. The path
        is not created as a side effect.
    """
    override = os.environ.get("CEI_LABS_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cei-labs-agent"


def config_path() -> Path:
    """Return the path to the persisted ``config.json`` file.

    Returns:
        ``<base>/config.json``.
    """
    return config_dir() / "config.json"


def notes_dir() -> Path:
    """Return the notes directory, creating it if necessary.

    Returns:
        ``<base>/notes`` after ensuring it (and its parents) exist.
    """
    path = config_dir() / "notes"
    path.mkdir(parents=True, exist_ok=True)
    return path


class RuntimeConfig(BaseModel):
    """Runtime capability and safety toggles.

    Attributes:
        allow_shell: Whether the agent may run SSH shell commands.
        allow_notes: Whether the agent may read/write scratch notes.
        observation_max_chars: Maximum characters kept per tool observation.
        max_steps: Maximum number of agent steps before forced completion.
        constrain_actions: When true, grammar-constrain each action turn to the
            action JSON schema (Ollama structured outputs) so weak models can't
            emit unparseable JSON. Automatically skipped on turns where the
            preset enables thinking (the two are incompatible). Off falls back
            to lenient post-hoc JSON extraction only.
        redact_flags: When true, redact runtime-discovered secrets (flags /
            passwords the box handed back in an observation) from the coach's
            final answer, so a model that ignores the "don't blurt the flag"
            instruction still can't paste it. A pedagogy default, not a gate.
        guard_shell: When true, run each ssh_exec command through the
            destructive-command denylist (:mod:`.guard`) before it touches the
            box. A speed bump against catastrophic commands, not a sandbox.
    """

    allow_shell: bool = False
    allow_notes: bool = True
    observation_max_chars: int = 4000
    max_steps: int = 20
    constrain_actions: bool = True
    redact_flags: bool = True
    guard_shell: bool = True


class SSHConfig(BaseModel):
    """Connection details for the target SSH box.

    Attributes:
        host: Hostname or IP address of the target.
        port: SSH port.
        username: Login user.
        password: Login password, if any.
        timeout: Connection/command timeout in seconds.
    """

    host: str
    port: int = 22
    username: str
    password: str | None = None
    timeout: int = 15


class AppConfig(BaseModel):
    """Top-level persisted application configuration.

    Attributes:
        model: Selected model tag.
        preset: Selected preset name.
        ssh: Optional SSH target configuration.
        ollama_host: Base URL of the local Ollama server.
    """

    model: str = "qwen3:4b"
    preset: str = "Standard"
    ssh: SSHConfig | None = None
    ollama_host: str = "http://localhost:11434"


def default_runtime_config() -> RuntimeConfig:
    """Return a fresh default runtime configuration.

    Returns:
        A :class:`RuntimeConfig` with contract defaults.
    """
    return RuntimeConfig()


def load_config() -> AppConfig:
    """Load the persisted application configuration.

    Returns:
        The parsed :class:`AppConfig`, or defaults when the file is missing or
        cannot be parsed.
    """
    path = config_path()
    if not path.exists():
        return AppConfig()
    try:
        return AppConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    """Persist the application configuration to ``config.json``.

    Args:
        cfg: The configuration to write. The parent directory is created if
            needed.
    """
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    config_path().write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
