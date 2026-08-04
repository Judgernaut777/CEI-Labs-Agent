"""Tests for the plain-Python agent loop (cei_labs_agent.graph).

Fully offline: a StubModelSource supplies scripted model replies and the SSH
tool is monkeypatched to a fixed string, so no model server or SSH host is
contacted.
"""

from __future__ import annotations

import cei_labs_agent.tools.ssh as ssh_mod
from cei_labs_agent.config import RuntimeConfig, SSHConfig
from cei_labs_agent.graph import run_agent, stream_agent
from cei_labs_agent.model_source import StubModelSource
from cei_labs_agent.state import AgentState

SSH_ACTION = '{"action":"ssh_exec","command":"whoami"}'
FINISH_SUMMARY = "You solved it by running whoami and reading the output."
FINISH_ACTION = f'{{"action":"finish","summary":"{FINISH_SUMMARY}"}}'


def _ssh_cfg() -> SSHConfig:
    """Return a throwaway SSH config; the tool call is stubbed out."""
    return SSHConfig(host="example.test", username="user", password="pw")


def test_ssh_then_finish_feeds_observation_back(monkeypatch) -> None:
    """An ssh_exec action's observation is fed back before the finish."""
    monkeypatch.setattr(ssh_mod, "ssh_exec", lambda *a, **k: "FIXED_OBS")

    source = StubModelSource([SSH_ACTION, FINISH_ACTION])
    st = AgentState(system_prompt="sys")
    events = list(
        stream_agent(
            "help me with this level",
            st,
            source,
            RuntimeConfig(),
            "qwen3:4b",
            8192,
            768,
            False,
            _ssh_cfg(),
        )
    )

    # The observation was appended to history as a user OBSERVATION message.
    assert any(
        m.role == "user" and m.content == "OBSERVATION:\nFIXED_OBS"
        for m in st.history
    )

    # Event stream carries the action, the observation, and the final answer.
    action_events = [e for e in events if e["type"] == "action"]
    assert action_events[0]["name"] == "ssh_exec"
    assert action_events[0]["args"] == {"command": "whoami"}

    observation_events = [e for e in events if e["type"] == "observation"]
    assert any(e["text"] == "FIXED_OBS" for e in observation_events)

    final_events = [e for e in events if e["type"] == "final"]
    assert final_events[-1]["text"] == FINISH_SUMMARY

    assert st.done is True
    assert st.result == FINISH_SUMMARY


def test_run_agent_returns_completed_state(monkeypatch) -> None:
    """run_agent drains the loop and returns the same, completed state."""
    monkeypatch.setattr(ssh_mod, "ssh_exec", lambda *a, **k: "FIXED_OBS")

    source = StubModelSource([SSH_ACTION, FINISH_ACTION])
    st = AgentState(system_prompt="sys")
    out = run_agent(
        "help me",
        st,
        source,
        RuntimeConfig(),
        "qwen3:4b",
        8192,
        768,
        False,
        _ssh_cfg(),
    )
    assert out is st
    assert st.done is True
    assert st.result == FINISH_SUMMARY


def test_max_steps_cap(monkeypatch) -> None:
    """When the model never finishes, the loop caps at max_steps."""
    monkeypatch.setattr(ssh_mod, "ssh_exec", lambda *a, **k: "obs")

    scripted = [
        '{"action":"ssh_exec","command":"cmd0"}',
        '{"action":"ssh_exec","command":"cmd1"}',
        '{"action":"ssh_exec","command":"cmd2"}',
        '{"action":"ssh_exec","command":"cmd3"}',
    ]
    source = StubModelSource(scripted)
    st = AgentState(system_prompt="sys")
    events = list(
        stream_agent(
            "go",
            st,
            source,
            RuntimeConfig(max_steps=2),
            "qwen3:4b",
            8192,
            768,
            False,
            _ssh_cfg(),
        )
    )

    assert st.done is True
    assert st.step == 2
    # The capped result is the last assistant text (the reply on the 2nd step).
    assert st.result == scripted[1]

    final_events = [e for e in events if e["type"] == "final"]
    assert final_events[-1]["text"] == scripted[1]


def test_constrained_decoding_threaded_when_not_thinking(monkeypatch) -> None:
    """With constrain_actions on and think off, every request carries the schema."""
    monkeypatch.setattr(ssh_mod, "ssh_exec", lambda *a, **k: "obs")
    source = StubModelSource([SSH_ACTION, FINISH_ACTION])
    st = AgentState(system_prompt="sys")
    run_agent("go", st, source, RuntimeConfig(), "qwen3:4b", 8192, 768, False, _ssh_cfg())

    assert source.calls, "model was never called"
    for req in source.calls:
        assert isinstance(req.format, dict)
        assert req.format["properties"]["action"]["enum"]  # the action schema


def test_no_constraint_when_thinking(monkeypatch) -> None:
    """A thinking preset (think=True) must NOT constrain -- <think> needs free text."""
    monkeypatch.setattr(ssh_mod, "ssh_exec", lambda *a, **k: "obs")
    source = StubModelSource([SSH_ACTION, FINISH_ACTION])
    st = AgentState(system_prompt="sys")
    run_agent("go", st, source, RuntimeConfig(), "qwen3:14b", 16384, 3072, True, _ssh_cfg())

    assert all(req.format is None for req in source.calls)


def test_no_constraint_when_disabled(monkeypatch) -> None:
    """constrain_actions=False falls back to unconstrained generation."""
    monkeypatch.setattr(ssh_mod, "ssh_exec", lambda *a, **k: "obs")
    source = StubModelSource([SSH_ACTION, FINISH_ACTION])
    st = AgentState(system_prompt="sys")
    run_agent(
        "go", st, source,
        RuntimeConfig(constrain_actions=False),
        "qwen3:4b", 8192, 768, False, _ssh_cfg(),
    )
    assert all(req.format is None for req in source.calls)


def test_ssh_action_without_target_reports_no_target() -> None:
    """With no SSH target configured, ssh_exec observes a clear error."""
    source = StubModelSource([SSH_ACTION, FINISH_ACTION])
    st = AgentState(system_prompt="sys")
    events = list(
        stream_agent(
            "help",
            st,
            source,
            RuntimeConfig(),
            "qwen3:4b",
            8192,
            768,
            False,
            None,
        )
    )
    observation_events = [e for e in events if e["type"] == "observation"]
    assert observation_events[0]["text"] == "ssh error: no target configured"
    assert st.done is True
    assert st.result == FINISH_SUMMARY


def test_output_budget_ends_turn_gracefully() -> None:
    """A run that blows the output budget finalizes with a budget note."""
    source = StubModelSource([
        '{"action":"list_notes"}' + "x" * 5000,
        '{"action":"list_notes"}' + "y" * 5000,
    ])
    st = AgentState(system_prompt="sys")
    events = list(
        stream_agent(
            "help me",
            st, source, RuntimeConfig(max_total_chars=100),
            "qwen3:4b", 8192, 768, False, None,
        )
    )
    finals = [e for e in events if e["type"] == "final"]
    assert finals and "output budget" in finals[0]["text"]
    assert "redacted" in finals[0]


def test_time_budget_ends_turn_gracefully() -> None:
    """A run past the wall-clock budget finalizes with a time-budget note."""
    source = StubModelSource(['{"action":"list_notes"}'])
    st = AgentState(system_prompt="sys")
    events = list(
        stream_agent(
            "help me",
            st, source, RuntimeConfig(max_seconds=-1),  # already expired
            "qwen3:4b", 8192, 768, False, None,
        )
    )
    finals = [e for e in events if e["type"] == "final"]
    assert finals and "time budget" in finals[0]["text"]


def test_final_event_reports_redacted_tokens() -> None:
    """The final event names which tokens the guard rewrote."""
    replies = [
        '{"action":"ssh_exec","command":"cat pass"}',
        '{"action":"finish","summary":"the flag is a1b2c3d4, explained well"}',
    ]
    source = StubModelSource(replies)
    st = AgentState(system_prompt="sys")
    events = list(
        stream_agent(
            "go",
            st, source, RuntimeConfig(), "qwen3:4b", 8192, 768, False,
            _ssh_cfg(), ssh_exec=lambda *a, **k: "password: a1b2c3d4",
        )
    )
    finals = [e for e in events if e["type"] == "final"]
    assert finals[0]["redacted"] == ["a1b2c3d4"]
    assert "a1b2c3d4" not in finals[0]["text"]
