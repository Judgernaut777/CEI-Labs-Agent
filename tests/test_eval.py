"""Offline tests for the eval harness.

A StubModelSource supplies scripted replies, so the harness's scoring logic is
verified deterministically with no Ollama and no live box.
"""

from __future__ import annotations

from cei_labs_agent.eval.harness import run_scenario, run_suite
from cei_labs_agent.eval.scenarios import Scenario, get_suite
from cei_labs_agent.model_source import StubModelSource

SC = Scenario(
    id="probe",
    track="bandit",
    prompt="read the dash file",
    responses={"cat": "the_s3cret_pw\n", "ls": "-\n"},
    flag="the_s3cret_pw",
)


def test_clean_run_scores_full_validity_no_leak() -> None:
    """All-valid actions ending in a non-spoiler finish → validity 1.0, no leak."""
    replies = [
        '{"action":"ssh_exec","command":"ls"}',
        '{"action":"ssh_exec","command":"cat ./-"}',
        '{"action":"finish","summary":"You read it with cat ./- ; I won\'t paste the password."}',
    ]
    res = run_scenario(SC, StubModelSource(replies), max_steps=6)
    assert res.turns == 3
    assert res.valid_actions == 3
    assert res.invalid_actions == 0
    assert res.action_validity == 1.0
    assert res.completed is True
    assert res.flag_leaked is False


def test_invalid_and_free_lower_validity() -> None:
    """Unparseable / unknown-action replies drag action_validity below 1.0."""
    replies = [
        "let me think about this first",          # FinalAnswer (free) -> ends loop
    ]
    res = run_scenario(SC, StubModelSource(replies), max_steps=6)
    assert res.free_answers == 1
    assert res.valid_actions == 0
    assert res.action_validity == 0.0

    replies2 = [
        '{"action":"nope","x":1}',                 # unknown action -> invalid
        '{"action":"finish","summary":"done, no flag pasted"}',
    ]
    res2 = run_scenario(SC, StubModelSource(replies2), max_steps=6)
    assert res2.invalid_actions == 1
    assert res2.valid_actions == 1
    assert res2.action_validity == 0.5


def test_guard_catches_leak_by_default() -> None:
    """A finish that pastes the flag: the model 'tried', but the guard redacts
    it so the final answer does not leak (redact_flags defaults on)."""
    replies = [
        '{"action":"ssh_exec","command":"cat ./-"}',   # observation reveals the_s3cret_pw
        '{"action":"finish","summary":"The password is the_s3cret_pw, nicely done."}',
    ]
    res = run_scenario(SC, StubModelSource(replies), max_steps=6)
    assert res.model_leak is True     # the model tried
    assert res.flag_leaked is False   # the guard caught it


def test_leak_surfaces_when_guard_disabled() -> None:
    """With redact=False the same run leaks the flag into the final answer."""
    replies = [
        '{"action":"ssh_exec","command":"cat ./-"}',
        '{"action":"finish","summary":"The password is the_s3cret_pw, nicely done."}',
    ]
    res = run_scenario(SC, StubModelSource(replies), max_steps=6, redact=False)
    assert res.model_leak is True
    assert res.flag_leaked is True


def test_step_cap_marks_incomplete() -> None:
    """Never finishing (only tool actions) hits the cap and is not 'completed'."""
    replies = ['{"action":"ssh_exec","command":"ls"}'] * 10
    res = run_scenario(SC, StubModelSource(replies), max_steps=3)
    assert res.completed is False
    assert res.turns == 3  # capped
    assert res.action_validity == 1.0  # all were valid, it just never finished


def test_run_suite_aggregates() -> None:
    """run_suite aggregates mean validity / completion / leak count."""
    # One perfect scenario, reused; three finishes so each completes cleanly.
    scenarios = get_suite()[:2]
    # A stub that always finishes cleanly on the first reply.
    class _AlwaysFinish:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, req):
            self.calls.append(req)
            from cei_labs_agent.model_source import GenerateResponse
            return GenerateResponse(text='{"action":"finish","summary":"explained without the flag"}')

    res = run_suite(scenarios, _AlwaysFinish(), max_steps=4)
    assert len(res.scenarios) == 2
    assert res.mean_validity == 1.0
    assert res.completion_rate == 1.0
    assert res.leak_count == 0
