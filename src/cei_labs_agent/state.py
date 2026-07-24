"""Conversation state for the plain-Python agent loop."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single chat message.

    Attributes:
        role: One of ``system``, ``user``, or ``assistant``.
        content: The message text.
    """

    role: str
    content: str


class AgentState(BaseModel):
    """Mutable state carried across steps of the agent loop.

    Attributes:
        system_prompt: The system prompt prepended to every model call.
        history: Ordered non-system messages exchanged so far.
        max_steps: Maximum number of tool steps before forced completion.
        step: The current step counter.
        done: Whether the loop has finished.
        result: The final result text once done, else ``None``.
    """

    system_prompt: str
    history: list[Message] = Field(default_factory=list)
    max_steps: int = 20
    step: int = 0
    done: bool = False
    result: str | None = None

    def add(self, role: str, content: str) -> None:
        """Append a message to the history.

        Args:
            role: The message role (``system``, ``user``, or ``assistant``).
            content: The message content.
        """
        self.history.append(Message(role=role, content=content))

    def as_messages(self) -> list[dict]:
        """Render the state as an Ollama-style messages list.

        Returns:
            The system prompt followed by each history message as
            ``{"role": ..., "content": ...}`` dicts.
        """
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        messages.extend({"role": m.role, "content": m.content} for m in self.history)
        return messages
