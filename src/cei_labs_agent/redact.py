"""Redact runtime-discovered secrets from the coach's final answer.

The agent is a teaching copilot: when it solves a level it should explain the
*method* without pasting the flag/password it just uncovered. The system prompt
asks for this, but small models don't reliably comply -- the eval harness caught
qwen3:4b solving a level and then writing the raw flag verbatim into its
summary. This module is the deterministic backstop for that. It is a pedagogy
guard, not a security boundary (a learner can always read the box directly);
the goal is a good default, not an anti-cheat gate.

A "secret" here is a token that (a) actually appeared in a tool OBSERVATION --
i.e. the box handed it back during this run -- and (b) looks like a credential
rather than prose: length >= 8 with at least one letter AND one digit. That
matches OTW-style flags/passwords (mixed alphanumerics) while leaving ordinary
words alone -- an 8+ char English word almost never carries a digit, so prose
like "directory" or "frequency" is untouched. Only observation-derived tokens
are eligible, so nothing the learner typed or the prompt contains is redacted.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./+=:-]{8,}")
PLACEHOLDER = "[redacted — recover this yourself]"


def _looks_secret(token: str) -> bool:
    """A token is credential-like if it mixes at least one letter and digit."""
    return any(c.isalpha() for c in token) and any(c.isdigit() for c in token)


def observation_secrets(observations: list[str]) -> set[str]:
    """Return the credential-like tokens that appeared in any observation."""
    blob = "\n".join(observations)
    return {tok for tok in _TOKEN_RE.findall(blob) if _looks_secret(tok)}


def redact(text: str, observations: list[str]) -> tuple[str, bool]:
    """Redact observation-derived secrets from ``text``.

    Args:
        text: The candidate final answer (finish summary or free-form final).
        observations: Every tool observation seen so far this run.

    Returns:
        ``(redacted_text, changed)`` -- each secret-looking token that appeared
        in an observation and also appears verbatim in ``text`` is replaced with
        :data:`PLACEHOLDER`. Longest tokens first so a secret that contains a
        shorter one isn't partially rewritten. ``changed`` is True iff anything
        was redacted.
    """
    secrets = observation_secrets(observations)
    if not secrets:
        return text, False
    out = text
    for secret in sorted(secrets, key=len, reverse=True):
        if secret in out:
            out = out.replace(secret, PLACEHOLDER)
    return out, out != text
