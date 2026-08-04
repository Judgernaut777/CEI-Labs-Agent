"""Destructive-command guard for the agent's shell tool.

The coach runs commands a small model dreamed up on a shared practice box,
driven by a beginner who can't vet them. Most turns are harmless (``ls``,
``cat``, ``grep``), but a model that goes off-script can do real damage —
``rm -rf`` a home directory, kill the box's services, or worse. The box is
disposable, but on event day a nuked box means staff time and a stalled
learner.

This module is the deterministic backstop: a small denylist of command
*shapes* that are never legitimate on a CTF practice box. It runs BEFORE the
command touches SSH, and a block becomes a normal OBSERVATION so the model
sees the refusal and can pick another approach — the refusal is itself a
teachable moment, which fits the coaching philosophy.

Deliberately a denylist, not an allowlist: wargames legitimately need weird
commands (piping into ``su``, ``nc`` chains, ``crontab`` games), and an
allowlist would break levels. The cost of that choice is acknowledged: this
is a speed bump, not a sandbox. It catches the catastrophic patterns, not
every bad idea.
"""

from __future__ import annotations

import re

# (pattern, human-readable reason). Patterns are matched case-insensitively
# against the raw command string; keep them tight to avoid false positives on
# legitimate wargame commands (e.g. `rm -rf /tmp/x` is fine, `rm -rf /` is not).
_BLOCKED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+/(\s|$|\*)"),
     "recursive force-delete from the filesystem root"),
    (re.compile(r"\bmkfs\b"), "formatting a filesystem"),
    (re.compile(r"\bdd\b[^;|&]*\bof=/dev/"), "writing a raw image to a device"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;:"), "fork bomb"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff|init\s+0|init\s+6)\b"),
     "shutting down or rebooting the box"),
    (re.compile(r">\s*/dev/(sd[a-z]|nvme|hd[a-z])"), "overwriting a block device"),
    (re.compile(r"\b(chmod|chown|chgrp)\b[^;|&]*\s-R[^;|&]*\s/(\s|$)"),
     "recursive permission/ownership change from the filesystem root"),
    (re.compile(r"\biptables\b|\bnft\b\s+(add|flush)"),
     "altering the box firewall"),
    (re.compile(r"\b(useradd|userdel|usermod|passwd)\b"),
     "changing the box's accounts"),
    (re.compile(r"\b(kill|killall|pkill)\b[^;|&]*\b(sshd|ssh)\b"),
     "killing the SSH service (that is your own way in)"),
]


def check_command(command: str) -> str | None:
    """Return a block reason if ``command`` matches the denylist, else None.

    Args:
        command: The raw shell command the model wants to run.

    Returns:
        None when the command is allowed, otherwise a short human-readable
        explanation of the matched pattern (suitable for an OBSERVATION).
    """
    for pattern, reason in _BLOCKED:
        if pattern.search(command):
            return reason
    return None


def blocked_observation(command: str, reason: str) -> str:
    """Render the OBSERVATION text the model sees when its command is blocked."""
    return (
        f"BLOCKED by safety guard: {reason}. The command was not executed. "
        "This box is a shared practice target — pick a command that reads or "
        "explores rather than destroys, and explain to the learner why this "
        "kind of command is dangerous on a real system."
    )
