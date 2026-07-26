"""Eval harness for the CEI Labs Agent.

Run with ``python -m cei_labs_agent.eval`` (see ``__main__``). The harness
scores the mechanical behaviours the constrained-decoding change targets --
action-validity rate and no-flag-leak -- across scripted scenarios that run
without a live box, so it works offline against a stub and, for real numbers,
against Ollama across the model ladder.
"""

from .harness import ScenarioResult, SuiteResult, run_scenario, run_suite
from .scenarios import Scenario, get_suite

__all__ = [
    "Scenario",
    "get_suite",
    "ScenarioResult",
    "SuiteResult",
    "run_scenario",
    "run_suite",
]
