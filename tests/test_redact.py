"""Tests for the flag-redaction guard (cei_labs_agent.redact)."""

from __future__ import annotations

from cei_labs_agent.redact import PLACEHOLDER, observation_secrets, redact


def test_redacts_observation_derived_secret() -> None:
    obs = ["natas7 password is flag_KRYPT0Nr0t here"]
    out, changed = redact("We decoded it to flag_KRYPT0Nr0t, nice.", obs)
    assert changed is True
    assert "flag_KRYPT0Nr0t" not in out
    assert PLACEHOLDER in out


def test_leaves_prose_untouched() -> None:
    """8+ char words without a digit are prose, not secrets."""
    obs = ["you are working in the home directory using frequency analysis"]
    text = "Use frequency analysis in your home directory."
    out, changed = redact(text, obs)
    assert changed is False
    assert out == text


def test_only_observation_secrets_are_redacted() -> None:
    """A secret-looking token the box never handed back is left alone."""
    obs = ["nothing sensitive here"]
    text = "Totally made up token aB3xY9kLmn should stay."
    out, changed = redact(text, obs)
    assert changed is False
    assert "aB3xY9kLmn" in out


def test_requires_letter_and_digit() -> None:
    secrets = observation_secrets(["word alldigits 12345678 mixed a1b2c3d4 UPPERCASE"])
    assert "a1b2c3d4" in secrets       # letter+digit -> secret
    assert "12345678" not in secrets   # digits only -> not
    assert "UPPERCASE" not in secrets  # letters only -> not


def test_longest_first_no_partial_rewrite() -> None:
    """A secret containing a shorter secret is fully redacted, not fragmented."""
    obs = ["pw_ab12 and pw_ab12_long99"]
    out, _ = redact("found pw_ab12_long99 today", obs)
    assert PLACEHOLDER in out
    assert "pw_ab12" not in out.replace(PLACEHOLDER, "")


def test_no_secrets_is_noop() -> None:
    out, changed = redact("plain summary", ["plain observation"])
    assert changed is False
    assert out == "plain summary"
