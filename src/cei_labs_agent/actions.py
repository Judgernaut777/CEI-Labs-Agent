"""Action parsing and schemas for the agent loop.

The model emits exactly one JSON action per turn. This module defines the known
actions, their argument schemas, and a robust parser that extracts the first
balanced JSON object from arbitrary model output.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, model_validator

KNOWN_ACTIONS: set[str] = {
    "ssh_exec",
    "read_notes",
    "write_notes",
    "list_notes",
    "finish",
}

ACTION_SCHEMAS: dict[str, dict] = {
    "ssh_exec": {
        "required": ["command"],
        "optional": [],
        "example": {"action": "ssh_exec", "command": "ls -la"},
        "desc": "Run a shell command over SSH on the configured target and observe its output.",
    },
    "read_notes": {
        "required": ["filename"],
        "optional": [],
        "example": {"action": "read_notes", "filename": "bandit.md"},
        "desc": "Read the contents of a saved notes file.",
    },
    "write_notes": {
        "required": ["filename", "content"],
        "optional": [],
        "example": {
            "action": "write_notes",
            "filename": "bandit.md",
            "content": "level0 password: ...",
        },
        "desc": "Write (overwrite) a notes file to remember progress between steps.",
    },
    "list_notes": {
        "required": [],
        "optional": [],
        "example": {"action": "list_notes"},
        "desc": "List the names of all saved notes files.",
    },
    "finish": {
        "required": ["summary"],
        "optional": [],
        "example": {
            "action": "finish",
            "summary": "a beginner-friendly explanation, never the raw flag verbatim",
        },
        "desc": "Conclude the task with a beginner-friendly summary; never blurt the raw flag verbatim.",
    },
}


def action_format_schema() -> dict:
    """Build a JSON schema for a single action, for constrained decoding.

    Passed to Ollama's ``format`` field (structured outputs) so the model is
    *grammar-constrained* to emit a valid JSON object whose ``action`` is one
    of :data:`KNOWN_ACTIONS`, with only known argument keys and string values.
    This deterministically removes the two most common small-model failure
    modes -- unparseable JSON and unknown actions -- rather than relying on
    :func:`parse_action` to recover from them after the fact.

    The schema is intentionally *flat* (an ``action`` enum plus every possible
    string argument as an optional property) rather than a per-action
    discriminated union: the flat form converts to a grammar cleanly on every
    llama.cpp/Ollama version, while the far rarer "right action, missing a
    required arg" case is still caught by :func:`parse_action` and fed back as
    an observation. Derived from :data:`ACTION_SCHEMAS` so new actions/args are
    picked up automatically.

    Returns:
        A JSON-schema dict suitable for Ollama's ``format`` parameter.
    """
    arg_names: list[str] = []
    for spec in ACTION_SCHEMAS.values():
        for key in list(spec.get("required", [])) + list(spec.get("optional", [])):
            if key not in arg_names:
                arg_names.append(key)
    properties: dict[str, dict] = {
        "action": {"type": "string", "enum": sorted(KNOWN_ACTIONS)}
    }
    for name in arg_names:
        properties[name] = {"type": "string"}
    return {
        "type": "object",
        "properties": properties,
        "required": ["action"],
        "additionalProperties": False,
    }


class Action(BaseModel):
    """A parsed, validated tool action.

    Attributes:
        name: The action name; must be a member of ``KNOWN_ACTIONS``.
        args: The action arguments, excluding the ``action`` key.
    """

    name: str
    args: dict

    @model_validator(mode="after")
    def _validate(self) -> "Action":
        """Ensure the action is known and required arguments are present."""
        if self.name not in KNOWN_ACTIONS:
            raise ValueError(f"unknown action: {self.name!r}")
        required = ACTION_SCHEMAS[self.name]["required"]
        missing = [key for key in required if key not in self.args]
        if missing:
            raise ValueError(
                f"missing required argument(s) for {self.name}: {', '.join(missing)}"
            )
        return self


class InvalidAction(BaseModel):
    """A malformed or unrecognised action.

    Attributes:
        reason: Human-readable explanation of why parsing failed.
        raw: The original untouched model text.
    """

    reason: str
    raw: str


class FinalAnswer(BaseModel):
    """A free-form final answer from the model (no JSON action present).

    Attributes:
        text: The stripped prose answer.
    """

    text: str


def _strip_code_fences(text: str) -> str:
    """Remove Markdown code-fence markers from text.

    Args:
        text: Raw text that may be wrapped in ``` fences.

    Returns:
        The text with fence lines removed.
    """
    lines = text.splitlines()
    cleaned: list[str] = [line for line in lines if not line.lstrip().startswith("```")]
    return "\n".join(cleaned)


def _extract_first_json_object(text: str) -> str | None:
    """Extract the first balanced ``{...}`` JSON object substring.

    Scans for a top-level object while respecting string literals and escape
    sequences so that braces inside strings do not confuse the matcher.

    Args:
        text: Arbitrary text possibly containing a JSON object.

    Returns:
        The matched substring including its braces, or ``None`` if none found.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def parse_action(text: str) -> Action | InvalidAction | FinalAnswer:
    """Parse a model reply into an action, invalid marker, or final answer.

    Behavior:
        - Strips code fences and extracts the first balanced ``{...}`` object,
          ignoring any surrounding prose.
        - Valid JSON object with a known action and all required args present
          yields an ``Action`` (``args`` excludes the ``action`` key).
        - A JSON object that is malformed, uses an unknown action, is missing a
          required argument, or is not an object yields an ``InvalidAction``.
        - No JSON object at all yields a ``FinalAnswer`` with the stripped prose.

    Args:
        text: The raw model reply.

    Returns:
        One of ``Action``, ``InvalidAction``, or ``FinalAnswer``.
    """
    candidate = _extract_first_json_object(text)
    if candidate is None:
        return FinalAnswer(text=_strip_code_fences(text).strip())

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return InvalidAction(reason="could not parse JSON action", raw=text)

    if not isinstance(data, dict):
        return InvalidAction(reason="action JSON is not an object", raw=text)

    name = data.get("action")
    if not isinstance(name, str) or name not in KNOWN_ACTIONS:
        return InvalidAction(reason=f"unknown action: {name!r}", raw=text)

    args = {key: value for key, value in data.items() if key != "action"}
    required = ACTION_SCHEMAS[name]["required"]
    missing = [key for key in required if key not in args]
    if missing:
        return InvalidAction(
            reason=f"missing required argument(s) for {name}: {', '.join(missing)}",
            raw=text,
        )

    return Action(name=name, args=args)
