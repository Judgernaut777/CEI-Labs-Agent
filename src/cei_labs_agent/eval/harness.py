"""Eval harness: run scenarios through the agent loop and score them.

Metrics are deliberately mechanical and model-agnostic so they mean the same
thing whether the model source is a real Ollama model or a scripted stub:

  * ``action_validity`` -- fraction of turns whose raw reply parsed into a
    valid, known action (including ``finish``). This is the number the
    constrained-decoding change is meant to drive to ~1.0 on weak models; an
    unconstrained small model scores well below it.
  * ``completed`` -- the model chose to end (a ``finish`` action or a
    free-form final answer) rather than hitting the step cap.
  * ``flag_leaked`` -- the raw scenario flag appears verbatim in the final
    summary. A good coach explains without pasting it, so this should be False.

Each raw assistant reply is re-classified here with :func:`parse_action`, so
scoring doesn't depend on the loop's event semantics.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..actions import Action, FinalAnswer, InvalidAction, parse_action
from ..config import RuntimeConfig, SSHConfig
from ..graph import stream_agent
from ..model_source import ModelSource
from ..prompts import build_system_prompt
from ..state import AgentState
from .scenarios import Scenario


class ScenarioResult(BaseModel):
    """Per-scenario metrics."""

    id: str
    track: str
    constrained: bool
    turns: int
    valid_actions: int
    invalid_actions: int
    free_answers: int
    action_validity: float
    completed: bool
    model_leak: bool  # the model's RAW summary contained the flag (its behaviour)
    flag_leaked: bool  # the FINAL surfaced answer contained the flag (after the guard)
    over_redacted: int = 0  # guard-fired redactions on tokens that are NOT the flag
    error: str | None = None


class SuiteResult(BaseModel):
    """Aggregate over a scenario run."""

    model: str
    constrained: bool
    scenarios: list[ScenarioResult]

    @property
    def mean_validity(self) -> float:
        if not self.scenarios:
            return 0.0
        return sum(s.action_validity for s in self.scenarios) / len(self.scenarios)

    @property
    def completion_rate(self) -> float:
        if not self.scenarios:
            return 0.0
        return sum(1 for s in self.scenarios if s.completed) / len(self.scenarios)

    @property
    def leak_count(self) -> int:
        """Runs where the flag survived into the final answer (guard failures)."""
        return sum(1 for s in self.scenarios if s.flag_leaked)

    @property
    def model_leak_count(self) -> int:
        """Runs where the model *tried* to reveal the flag (guard caught these)."""
        return sum(1 for s in self.scenarios if s.model_leak)

    @property
    def over_redaction_count(self) -> int:
        """Total guard redactions fired on tokens that were not the flag."""
        return sum(s.over_redacted for s in self.scenarios)


def run_scenario(
    scenario: Scenario,
    source: ModelSource,
    *,
    model: str = "qwen3:4b",
    num_ctx: int = 8192,
    num_predict: int = 768,
    think: bool = False,
    constrain: bool = True,
    redact: bool = True,
    max_steps: int = 12,
) -> ScenarioResult:
    """Run one scenario end to end and score it.

    Args:
        scenario: The scripted level to run.
        source: The model source (Ollama for real runs, a stub for tests).
        model: Model tag passed through to the request.
        num_ctx, num_predict, think: Generation knobs (mirror a registry preset).
        constrain: Whether to grammar-constrain actions (the A/B knob).
        max_steps: Step cap for the run.

    Returns:
        A :class:`ScenarioResult`.
    """
    runtime = RuntimeConfig(constrain_actions=constrain, redact_flags=redact, max_steps=max_steps)
    ssh = SSHConfig(host="mock-box", port=22, username="player", password="x")
    system_prompt = build_system_prompt(runtime, f"{ssh.username}@{ssh.host}:{ssh.port}")
    st = AgentState(system_prompt=system_prompt, max_steps=max_steps)

    replies: list[str] = []
    error: str | None = None
    redacted_tokens: list[str] = []
    responder = scenario.make_responder()
    for event in stream_agent(
        scenario.prompt, st, source, runtime, model,
        num_ctx, num_predict, think, ssh, ssh_exec=responder,
    ):
        if event["type"] == "assistant":
            replies.append(event["text"])
        elif event["type"] == "final":
            redacted_tokens = event.get("redacted", [])
        elif event["type"] == "error":
            error = event["message"]

    valid = invalid = free = finishes = 0
    for reply in replies:
        parsed = parse_action(reply)
        if isinstance(parsed, Action):
            valid += 1
            if parsed.name == "finish":
                finishes += 1
        elif isinstance(parsed, InvalidAction):
            invalid += 1
        elif isinstance(parsed, FinalAnswer):
            free += 1

    turns = len(replies)
    validity = valid / turns if turns else 1.0
    result_text = st.result or ""
    flag_lower = scenario.flag.lower()
    # model_leak: the model *tried* to reveal the flag in any raw reply.
    model_leak = any(flag_lower in r.lower() for r in replies)
    # flag_leaked: the flag survived into the final surfaced answer (guard failed).
    flag_leaked = bool(result_text) and flag_lower in result_text.lower()
    # over_redacted: the guard rewrote tokens that aren't the flag (e.g. a
    # version string or digit-bearing path the model quoted). Some are
    # inevitable with a regex-shaped guard, but a high count means learners
    # are seeing '[redacted]' where nothing secret was said.
    over_redacted = sum(1 for t in redacted_tokens if t.lower() != flag_lower)

    return ScenarioResult(
        id=scenario.id,
        track=scenario.track,
        constrained=constrain,
        turns=turns,
        valid_actions=valid,
        invalid_actions=invalid,
        free_answers=free,
        action_validity=round(validity, 3),
        completed=(finishes > 0 or free > 0) and error is None,
        model_leak=model_leak,
        flag_leaked=flag_leaked,
        over_redacted=over_redacted,
        error=error,
    )


def run_suite(
    scenarios: list[Scenario],
    source: ModelSource,
    *,
    model: str = "qwen3:4b",
    num_ctx: int = 8192,
    num_predict: int = 768,
    think: bool = False,
    constrain: bool = True,
    redact: bool = True,
    max_steps: int = 12,
) -> SuiteResult:
    """Run every scenario and aggregate the results."""
    results = [
        run_scenario(
            sc, source, model=model, num_ctx=num_ctx, num_predict=num_predict,
            think=think, constrain=constrain, redact=redact, max_steps=max_steps,
        )
        for sc in scenarios
    ]
    return SuiteResult(model=model, constrained=constrain, scenarios=results)
