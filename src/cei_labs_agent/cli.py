"""Command-line entry point that launches the local web UI.

Starts the FastAPI app under uvicorn, prints a friendly warning when Ollama is
not reachable (without blocking startup), and opens the default browser to the
UI shortly after the server comes up.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from .config import load_config
from .model_source import ollama_up
from .server import create_app

__all__ = ["main"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional explicit argument list (defaults to ``sys.argv``).

    Returns:
        The parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="ctf-agent",
        description="CEI Labs Agent — a local CTF training-wheels AI teammate.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind the web server to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to serve the web UI on (default: 8765).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser window automatically.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Launch the CEI Labs Agent web UI.

    Warns (but keeps going) if Ollama is unreachable, opens the browser unless
    suppressed, and runs the server until interrupted.
    """
    args = _parse_args()

    cfg = load_config()
    if not ollama_up(cfg.ollama_host):
        print(
            "[!] Ollama does not appear to be running at "
            f"{cfg.ollama_host}.\n"
            "    The UI will still start, but you'll need Ollama up before the "
            "agent can think.\n"
            "    Install/start it from https://ollama.com and then reload the "
            "page.\n"
        )

    url = f"http://{args.host}:{args.port}"
    print(f"[*] CEI Labs Agent is starting at {url}")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
