"""CLI: run the eval suite against Ollama across the model ladder.

Examples:
    python -m cei_labs_agent.eval                     # default model, constrained
    python -m cei_labs_agent.eval --compare           # constrained vs unconstrained A/B
    python -m cei_labs_agent.eval --models qwen3:1.7b,qwen3:4b --compare

The A/B is the point: on the weak tiers you should see action-validity jump
under constraint. Needs a running Ollama with the model(s) pulled.
"""

from __future__ import annotations

import argparse
import sys

from ..models import get_model
from ..model_source import OllamaModelSource, list_local_models, ollama_up
from .harness import SuiteResult, run_suite
from .scenarios import get_suite


def _preset_knobs(model: str) -> tuple[int, int, bool]:
    """Return (num_ctx, num_predict, think) from the model's default preset."""
    spec = get_model(model)
    if spec is None:
        return 8192, 768, False
    preset = next((p for p in spec.presets if p.name == spec.default_preset), spec.presets[0])
    return preset.num_ctx, preset.num_predict, preset.think


def _print_suite(res: SuiteResult) -> None:
    tag = "constrained" if res.constrained else "unconstrained"
    print(f"\n== {res.model}  [{tag}] ==")
    print(f"{'scenario':<14}{'validity':>10}{'valid/inv/free':>18}{'done':>7}{'leak(raw>final)':>17}")
    for s in res.scenarios:
        vif = f"{s.valid_actions}/{s.invalid_actions}/{s.free_answers}"
        # raw = the model tried to reveal the flag; final = it survived the guard.
        leak = f"{'tried' if s.model_leak else '-'}>{'LEAK' if s.flag_leaked else 'ok'}"
        print(
            f"{s.id:<14}{s.action_validity:>10.2f}{vif:>18}"
            f"{('yes' if s.completed else 'no'):>7}{leak:>17}"
            + (f"   ERROR: {s.error}" if s.error else "")
        )
    print(
        f"{'MEAN':<14}{res.mean_validity:>10.2f}{'':>18}"
        f"{f'{res.completion_rate:.0%}':>7}"
        f"{f'{res.model_leak_count}>{res.leak_count}':>17}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cei_labs_agent.eval")
    parser.add_argument("--models", default="qwen3:4b",
                        help="comma-separated Ollama tags to evaluate")
    parser.add_argument("--compare", action="store_true",
                        help="also run unconstrained and show the delta")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args(argv)

    if not ollama_up(args.host):
        print(f"Ollama is not reachable at {args.host}. Start it (`ollama serve`) and retry.",
              file=sys.stderr)
        return 2

    local = set(list_local_models(args.host))
    source = OllamaModelSource(host=args.host)
    suite = get_suite()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    for model in models:
        if model not in local:
            print(f"note: {model} is not pulled locally; Ollama will try to pull or error.",
                  file=sys.stderr)
        num_ctx, num_predict, think = _preset_knobs(model)
        con = run_suite(suite, source, model=model, num_ctx=num_ctx,
                        num_predict=num_predict, think=think, constrain=True,
                        max_steps=args.max_steps)
        _print_suite(con)
        if args.compare:
            unc = run_suite(suite, source, model=model, num_ctx=num_ctx,
                            num_predict=num_predict, think=think, constrain=False,
                            max_steps=args.max_steps)
            _print_suite(unc)
            delta = con.mean_validity - unc.mean_validity
            print(f"\n>> {model}: constrained lifts mean action-validity by "
                  f"{delta:+.2f} ({unc.mean_validity:.2f} -> {con.mean_validity:.2f})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
