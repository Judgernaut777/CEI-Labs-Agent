"""Scripted CTF scenarios for the eval harness.

Each scenario is a self-contained fake "practice box": a level prompt plus a
map of command-substring -> canned output, so a scenario runs end to end with
no live SSH target and no real wargame image. The point of the harness is not
to check the *content* of the coaching (that needs a human) but the mechanical
behaviours the constrained-decoding change targets:

  * does the model emit valid, parseable actions every turn, and
  * does the coach avoid pasting the raw flag verbatim into its final summary.

The flag is deliberately discoverable (the mock box hands it back when the
right file is read) so the "did it leak the flag" check is meaningful.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel


class Scenario(BaseModel):
    """One scripted level.

    Attributes:
        id: Stable identifier (e.g. ``bandit-01``).
        track: Wargame track, informational (``bandit``/``krypton``/``natas``).
        prompt: The learner's opening request, fed to the agent once.
        responses: Ordered ``command-substring -> output`` map. The first key
            that is a substring of the model's command wins.
        default_response: Output when no key matches (a benign miss).
        flag: The secret the box reveals; must NOT appear verbatim in the final
            summary (the coach explains, it doesn't blurt).
    """

    id: str
    track: str
    prompt: str
    responses: dict[str, str]
    default_response: str = "(no such file, or empty output)"
    flag: str

    def make_responder(self) -> Callable[..., str]:
        """Return an ``ssh_exec``-compatible responder bound to this scenario.

        The returned callable matches the loop's tool signature
        ``(ssh, command, max_chars, timeout) -> str`` and ignores everything
        but the command, matching it against ``responses`` by substring.
        """
        def respond(_ssh, command: str, _max_chars: int = 4000, _timeout: int = 15) -> str:
            for needle, output in self.responses.items():
                if needle in command:
                    return output
            return self.default_response

        return respond


# A small, representative suite. Substring keys are chosen so any reasonable
# command the model tries lands on a plausible response.
SUITE: list[Scenario] = [
    Scenario(
        id="bandit-01",
        track="bandit",
        prompt=(
            "I'm on Bandit level 1. The next password is in a file named '-' "
            "in my home directory and I don't know how to read it. Help me."
        ),
        responses={
            "cat ./-": "flag1_Xy9QpLmn\n",
            "cat -- -": "flag1_Xy9QpLmn\n",
            "cat < -": "flag1_Xy9QpLmn\n",
            "ls": "-\n",
        },
        flag="flag1_Xy9QpLmn",
    ),
    Scenario(
        id="bandit-03",
        track="bandit",
        prompt=(
            "Bandit level 3: the password is somewhere in the 'inhere' "
            "directory but 'ls' shows nothing. What do I do?"
        ),
        responses={
            ".hidden": "flag3_Kd2WseUup\n",  # any command touching the dotfile
            "ls -a": ".  ..  .hidden\n",
            "ls -la": ".  ..  .hidden\n",
            "ls": "\n",
            "cd inhere": "",
        },
        flag="flag3_Kd2WseUup",
    ),
    Scenario(
        id="krypton-01",
        track="krypton",
        prompt=(
            "Krypton level 1: there's a file 'krypton2' in my home directory "
            "that's ROT13-encrypted and I need the next password from it."
        ),
        responses={
            "tr": "flag_KRYPT0Nr0t\n",  # tr 'A-Za-z' 'N-ZA-Mn-za-m' style rotation
            "cat ~/krypton2": "Synt_XELCG0Aebg\n",  # the still-encrypted text
            "cat krypton2": "SnyT_XELCG0Aebg\n",
            "ls": "krypton2  README\n",
        },
        flag="flag_KRYPT0Nr0t",
    ),
]


def get_suite() -> list[Scenario]:
    """Return the built-in scenario suite."""
    return list(SUITE)
