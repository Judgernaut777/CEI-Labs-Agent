"""Setup-verification CLI for the CEI Labs CTF's "AI Copilot Setup" track.

Checks five concrete, real milestones toward a working, useful CEI Labs
Agent install and prints one static flag per milestone that is actually
satisfied. Every flag only appears when its underlying condition is
independently, mechanically true -- nothing here is guessable without
doing the real step, since each check calls the exact same code paths the
app itself uses (Ollama's HTTP API, this package's own installed metadata,
a real SSH connection via the agent's own ``ssh_exec`` tool).

This is a separate entry point (``ctf-agent-verify``) from the main app
(``ctf-agent``) so it can run headless, non-interactively, print plain text
to a terminal, and exit -- suited to a CTFd submission workflow rather than
launching a web server.
"""

from __future__ import annotations

import argparse
import re
import sys
from importlib import metadata

from .config import SSHConfig
from .model_source import list_local_models, ollama_up
from .tools.ssh import ssh_exec

__all__ = ["main"]

FLAG_OLLAMA = "CEI-AGENT-1-OLLAMA-IS-ALIVE"
FLAG_MODEL = "CEI-AGENT-2-A-BRAIN-IS-INSTALLED"
FLAG_INSTALLED = "CEI-AGENT-3-CTF-AGENT-IS-RUNNING"
FLAG_SSH = "CEI-AGENT-4-CONNECTED-TO-MY-BOX"
FLAG_PROMPT = "CEI-AGENT-5-I-KNOW-HOW-TO-ASK"

# Loosely matches the example prompts from README.md's "Using it -- the
# short version" section (e.g. "Help me figure out level 1 of Bandit.").
# Deliberately forgiving on exact wording/punctuation -- what proves the
# learner understands the pattern is naming a track and a level alongside
# an explicit ask for help, not transcribing the example byte-for-byte.
_PROMPT_PATTERN = re.compile(
    r"(?=.*help me)(?=.*\b(?:bandit|krypton|natas)\b)(?=.*\blevel\b)",
    re.IGNORECASE | re.DOTALL,
)

_PING = "cei-labs-agent-verify-ok"


def _check_ollama(host: str) -> bool:
    """Return True if an Ollama server answers at ``host``."""
    return ollama_up(host)


def _check_model(host: str) -> list[str]:
    """Return the locally installed Ollama model tags at ``host``."""
    return list_local_models(host)


def _check_installed() -> str | None:
    """Return the installed ``cei-labs-agent`` package version, or None."""
    try:
        return metadata.version("cei-labs-agent")
    except metadata.PackageNotFoundError:
        return None


def _check_ssh(host: str, port: int, username: str, password: str | None) -> bool:
    """Return True if a real command round-trips over SSH to the target."""
    ssh_cfg = SSHConfig(host=host, port=port, username=username, password=password)
    result = ssh_exec(ssh_cfg, f"echo {_PING}")
    return _PING in result and not result.startswith("ssh error:")


def _check_prompt(prompt: str | None) -> bool:
    """Return True if ``prompt`` matches the documented help-prompt shape."""
    return bool(prompt) and bool(_PROMPT_PATTERN.search(prompt))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ctf-agent-verify",
        description=(
            "Verify your CEI Labs Agent setup for the 'AI Copilot Setup' CTF track "
            "and print the flag for each milestone you've actually completed."
        ),
    )
    parser.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
        help="Base URL of your local Ollama server (default: http://localhost:11434).",
    )
    parser.add_argument("--host", help="SSH host of your challenge box (from the launch panel).")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22).")
    parser.add_argument("--user", help="SSH username for your challenge box.")
    parser.add_argument("--password", help="SSH password for your challenge box.")
    parser.add_argument(
        "--prompt",
        help='The prompt you would type into the agent to ask for help, e.g. "Help me with Bandit level 1".',
    )
    return parser.parse_args(argv)


def _report(step: int, label: str, passed: bool, flag: str, *, missing: str | None = None) -> None:
    status = "PASS" if passed else "FAIL"
    print(f"[{step}/5] {status} -- {label}")
    if passed:
        print(f"      flag: {flag}")
    elif missing:
        print(f"      not checked yet -- {missing}")


def main(argv: list[str] | None = None) -> int:
    """Run all five checks and print a flag for each one that passes.

    Returns:
        The number of checks that did NOT pass (0 means all five passed).
    """
    args = _parse_args(argv)
    print("CEI Labs Agent -- CTF setup verification\n")

    ok_ollama = _check_ollama(args.ollama_host)
    _report(1, "Ollama is installed and running", ok_ollama, FLAG_OLLAMA)

    models = _check_model(args.ollama_host) if ok_ollama else []
    _report(
        2,
        "At least one model is installed",
        bool(models),
        FLAG_MODEL,
        missing="install a model from the app's model picker first" if ok_ollama else "get Ollama running first (step 1)",
    )

    version = _check_installed()
    _report(
        3,
        "ctf-agent is installed and importable",
        version is not None,
        FLAG_INSTALLED,
        missing="run the bootstrap script from the challenge files, then re-run this check",
    )

    ok_ssh = False
    if args.host and args.user:
        ok_ssh = _check_ssh(args.host, args.port, args.user, args.password)
    _report(
        4,
        "Connected to your challenge box over SSH",
        ok_ssh,
        FLAG_SSH,
        missing="pass --host, --user, and --password from your launched instance's connect panel",
    )

    ok_prompt = _check_prompt(args.prompt)
    _report(
        5,
        "You know the basic help-prompt pattern",
        ok_prompt,
        FLAG_PROMPT,
        missing='pass --prompt "Help me with Bandit level 1" (or Krypton/Natas, any level)',
    )

    print()
    failed = sum(not ok for ok in (ok_ollama, bool(models), version is not None, ok_ssh, ok_prompt))
    if failed:
        print(f"{5 - failed}/5 complete -- keep going.")
    else:
        print("5/5 complete -- you're set up and ready to use the agent for real.")
    return failed


if __name__ == "__main__":
    sys.exit(main())
