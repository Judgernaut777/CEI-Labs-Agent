"""Plain-Python act -> tool -> act agent loop.

Drives an :class:`AgentState` by repeatedly asking a model source for a single
JSON action, executing it against the SSH / notes tools, and feeding the
observation back into history. Emits typed event dicts for streaming UIs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from .actions import (
    Action,
    FinalAnswer,
    InvalidAction,
    action_format_schema,
    parse_action,
)
from .config import RuntimeConfig, SSHConfig
from .model_source import GenerateRequest, ModelSource
from .state import AgentState
from .tools import notes as notes_tools
from .tools import ssh as ssh_tools


def stream_agent(
    user_message: str,
    st: AgentState,
    source: ModelSource,
    runtime: RuntimeConfig,
    model: str,
    num_ctx: int,
    num_predict: int,
    think: bool,
    ssh: SSHConfig | None,
    ssh_exec: Callable[..., str] | None = None,
) -> Iterator[dict]:
    """Run the agent loop, yielding typed events while mutating ``st``.

    Args:
        user_message: The user's request, appended once to history.
        st: Mutable agent state (history, step counter, result).
        source: Model source used to generate each turn.
        runtime: Runtime toggles (shell/notes gating, limits, max steps).
        model: Model tag passed to the generate request.
        num_ctx: Context window size for generation.
        num_predict: Max tokens to predict.
        think: Whether the model should emit a thinking block.
        ssh: SSH target for ``ssh_exec`` actions, or ``None``.
        ssh_exec: Optional override for the SSH executor, called as
            ``ssh_exec(ssh, command, max_chars, timeout) -> str``. Defaults to
            the real tool; the eval harness injects a scripted responder here so
            scenarios run without a live box.

    Yields:
        Event dicts with a ``type`` key: ``assistant``, ``action``,
        ``observation``, ``invalid``, ``final`` or ``error``.
    """
    run_ssh_exec = ssh_exec or ssh_tools.ssh_exec
    st.add("user", user_message)
    last_assistant_text: str = ""

    # Constrain each action turn to the action JSON schema, EXCEPT when the
    # preset enables thinking: a thinking model must emit free-form <think>
    # prose first, which a strict JSON grammar would forbid. So constrained
    # decoding applies to exactly the (think=False) presets -- which is every
    # small tier, the ones that actually need the reliability guarantee.
    action_format = action_format_schema() if (runtime.constrain_actions and not think) else None

    while st.step < runtime.max_steps and not st.done:
        req = GenerateRequest(
            messages=st.as_messages(),
            model=model,
            num_ctx=num_ctx,
            num_predict=num_predict,
            think=think,
            temperature=0.3,
            format=action_format,
        )
        try:
            reply = source.generate(req).text
        except Exception as exc:  # noqa: BLE001 - never let a failure escape the loop
            yield {"type": "error", "message": str(exc)}
            return

        last_assistant_text = reply
        st.add("assistant", reply)
        yield {"type": "assistant", "text": reply}

        parsed = parse_action(reply)

        if isinstance(parsed, FinalAnswer):
            st.result = parsed.text
            st.done = True
            yield {"type": "final", "text": parsed.text}
            break

        if isinstance(parsed, InvalidAction):
            reason = parsed.reason
            yield {"type": "invalid", "reason": reason}
            st.add("user", "OBSERVATION:\n" + "INVALID ACTION: " + reason)
            st.step += 1
            continue

        # parsed is an Action.
        name = parsed.name
        args = parsed.args

        if name == "finish":
            summary = args["summary"]
            st.result = summary
            st.done = True
            yield {"type": "final", "text": summary}
            break

        yield {"type": "action", "name": name, "args": args}

        if name == "ssh_exec":
            if ssh is None:
                obs = "ssh error: no target configured"
            else:
                obs = run_ssh_exec(
                    ssh,
                    args["command"],
                    runtime.observation_max_chars,
                    ssh.timeout,
                )
        elif not runtime.allow_notes:
            obs = "notes disabled"
        elif name == "read_notes":
            obs = notes_tools.read_notes(args["filename"])
        elif name == "write_notes":
            obs = notes_tools.write_notes(args["filename"], args["content"])
        else:  # list_notes
            obs = notes_tools.list_notes()

        st.add("user", "OBSERVATION:\n" + obs)
        yield {"type": "observation", "text": obs}
        st.step += 1

    if not st.done:
        st.done = True
        st.result = last_assistant_text
        yield {"type": "final", "text": last_assistant_text}


def run_agent(
    user_message: str,
    st: AgentState,
    source: ModelSource,
    runtime: RuntimeConfig,
    model: str,
    num_ctx: int,
    num_predict: int,
    think: bool,
    ssh: SSHConfig | None,
    ssh_exec: Callable[..., str] | None = None,
) -> AgentState:
    """Drain :func:`stream_agent` to completion and return the final state.

    Args:
        user_message: The user's request.
        st: Mutable agent state to drive.
        source: Model source used to generate each turn.
        runtime: Runtime toggles and limits.
        model: Model tag passed to the generate request.
        num_ctx: Context window size for generation.
        num_predict: Max tokens to predict.
        think: Whether the model should emit a thinking block.
        ssh: SSH target for ``ssh_exec`` actions, or ``None``.
        ssh_exec: Optional SSH executor override (see :func:`stream_agent`).

    Returns:
        The mutated :class:`AgentState` after the loop terminates.
    """
    for _ in stream_agent(
        user_message,
        st,
        source,
        runtime,
        model,
        num_ctx,
        num_predict,
        think,
        ssh,
        ssh_exec=ssh_exec,
    ):
        pass
    return st
