"""Tests for action parsing (cei_labs_agent.actions.parse_action)."""

from __future__ import annotations

from cei_labs_agent.actions import (
    Action,
    FinalAnswer,
    InvalidAction,
    parse_action,
)


def test_clean_json_ssh_exec() -> None:
    """A bare JSON object parses into an Action with args minus 'action'."""
    text = '{"action":"ssh_exec","command":"ls -la"}'
    result = parse_action(text)
    assert isinstance(result, Action)
    assert result.name == "ssh_exec"
    assert result.args == {"command": "ls -la"}
    assert "action" not in result.args


def test_fenced_json_block() -> None:
    """A ```json fenced block has its fences stripped before parsing."""
    text = '```json\n{"action":"read_notes","filename":"bandit.md"}\n```'
    result = parse_action(text)
    assert isinstance(result, Action)
    assert result.name == "read_notes"
    assert result.args == {"filename": "bandit.md"}


def test_prose_then_json() -> None:
    """Surrounding prose is ignored; the first JSON object wins."""
    text = "Sure, let me check what notes exist first.\n" '{"action":"list_notes"}'
    result = parse_action(text)
    assert isinstance(result, Action)
    assert result.name == "list_notes"
    assert result.args == {}


def test_no_json_is_final_answer() -> None:
    """Text with no JSON object becomes a stripped FinalAnswer."""
    text = "  I walked you through how the password was recovered, without pasting it.  "
    result = parse_action(text)
    assert isinstance(result, FinalAnswer)
    assert result.text == text.strip()


def test_unknown_action_is_invalid() -> None:
    """An unrecognised action name yields InvalidAction carrying raw text."""
    text = '{"action":"delete_everything","path":"/"}'
    result = parse_action(text)
    assert isinstance(result, InvalidAction)
    assert result.raw == text
    assert result.reason


def test_missing_required_arg_is_invalid() -> None:
    """A known action missing a required argument yields InvalidAction."""
    text = '{"action":"write_notes","filename":"a.md"}'  # missing "content"
    result = parse_action(text)
    assert isinstance(result, InvalidAction)
    assert result.raw == text
    assert "content" in result.reason


def test_malformed_json_object_is_invalid() -> None:
    """A brace-delimited blob that is not valid JSON yields InvalidAction."""
    text = "{not valid json}"
    result = parse_action(text)
    assert isinstance(result, InvalidAction)
    assert result.raw == text
    assert result.reason


def test_each_action_parses() -> None:
    """Every one of the five known actions parses with the right args."""
    samples: dict[str, tuple[str, dict]] = {
        "ssh_exec": ('{"action":"ssh_exec","command":"whoami"}', {"command": "whoami"}),
        "read_notes": (
            '{"action":"read_notes","filename":"n.md"}',
            {"filename": "n.md"},
        ),
        "write_notes": (
            '{"action":"write_notes","filename":"n.md","content":"hi"}',
            {"filename": "n.md", "content": "hi"},
        ),
        "list_notes": ('{"action":"list_notes"}', {}),
        "finish": (
            '{"action":"finish","summary":"nice work solving it"}',
            {"summary": "nice work solving it"},
        ),
    }
    for name, (text, expected_args) in samples.items():
        result = parse_action(text)
        assert isinstance(result, Action), f"{name} did not parse to an Action"
        assert result.name == name
        assert result.args == expected_args
        assert "action" not in result.args


def test_args_excludes_action_key() -> None:
    """The 'action' key is never carried into Action.args."""
    result = parse_action('{"action":"finish","summary":"done"}')
    assert isinstance(result, Action)
    assert "action" not in result.args
    assert result.args == {"summary": "done"}
