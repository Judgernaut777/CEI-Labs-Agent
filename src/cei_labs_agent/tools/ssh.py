"""SSH command execution tool.

Two ways to run a command over SSH, both designed to be safe to call from the
agent loop: they never raise and always return any failure as an
``"ssh error: ..."`` string instead.

- :func:`ssh_exec` — one-shot: opens a fresh connection per call, runs one
  command, closes. Used by the "test connection" endpoint, where you want an
  isolated check rather than touching shared session state.
- :func:`session_exec` — persistent: keeps ONE connection (with an
  interactive shell) open per target and reuses it across the agent loop's
  turns. This fixes two real problems the one-shot version had:

  1. **Latency.** Every turn paid a full TCP + auth handshake. On the slow
     laptop CPUs this agent targets, that was often the slowest part of a
     step.
  2. **Lost session state.** A fresh connection per command meant ``cd``,
     exported variables, and ``su``/``ssh`` chains did not carry over between
     steps, which confused learners ("I cd'd into the directory, why am I
     back home?").

Host-key policy: TOFU (trust on first use). The first connection to a target
records the server's key fingerprint under the config directory; later
connections must present the same key or the call fails with a clear error.
For throwaway event boxes ``AutoAddPolicy``-style acceptance would be
tempting, but this is a *security education* tool — silently accepting any
host key teaches exactly the wrong habit on tracks (like Natas) that are
literally about not trusting things blindly. First-seen keys are logged so an
operator can eyeball them.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading

import paramiko

from ..config import SSHConfig, config_dir

logger = logging.getLogger(__name__)

# Marker printed after each command so we know where its output ends. The exit
# status is embedded (``__CEI_END_0__``) so a hanging command can't be faked
# out by output that merely contains the marker text.
_END_RE = re.compile(r"\r?\n?__CEI_END_(\d+)__\s*$")


def known_hosts_path():
    """Return the TOFU known-hosts file path (created on demand, not here)."""
    return config_dir() / "known_hosts.json"


def _fingerprint(client: paramiko.SSHClient) -> str | None:
    """Return the connected server's host-key fingerprint, or None.

    The fingerprint is the base64 of the raw key blob — stable, printable, and
    comparable. None when no transport is available (e.g. in tests with a
    fake client), in which case TOFU is skipped rather than faked.
    """
    try:
        transport = client.get_transport()
        if transport is None:
            return None
        key = transport.get_remote_server_key()
        return base64.b64encode(key.asbytes()).decode("ascii")
    except Exception:  # noqa: BLE001 - never let key inspection break the call
        logger.debug("could not read remote host key", exc_info=True)
        return None


def _host_id(ssh: SSHConfig) -> str:
    """Stable identifier for a target in the TOFU store."""
    return f"{ssh.username}@{ssh.host}:{ssh.port}"


def verify_host_key(ssh: SSHConfig, fingerprint: str) -> str | None:
    """Check ``fingerprint`` against the TOFU store for this target.

    First sight of a target records the fingerprint and returns None (allowed).
    A later connection with a *different* fingerprint returns an error string.
    """
    path = known_hosts_path()
    try:
        known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (ValueError, OSError):
        logger.warning("known-hosts file unreadable, starting fresh", exc_info=True)
        known = {}

    host = _host_id(ssh)
    recorded = known.get(host)
    if recorded is None:
        known[host] = fingerprint
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(known, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("could not persist host key for %s", host, exc_info=True)
        logger.info("TOFU: recorded new host key for %s: %s", host, fingerprint[:24])
        return None
    if recorded != fingerprint:
        logger.error("HOST KEY CHANGED for %s (was %s..., now %s...)",
                     host, recorded[:16], fingerprint[:16])
        return (
            f"ssh error: host key for {_host_id(ssh)} CHANGED since first "
            "connection — refusing to connect (possible MITM, or the box was "
            "rebuilt). Delete the entry in known_hosts.json if this rebuild "
            "was expected."
        )
    return None


def ssh_exec(
    ssh: SSHConfig,
    command: str,
    max_chars: int = 4000,
    timeout: int = 15,
) -> str:
    """Execute ``command`` over a one-shot SSH connection and return output.

    Args:
        ssh: Connection settings (host, port, username, password, timeout).
        command: The shell command to run on the remote host.
        max_chars: Maximum characters of output to return before truncating.
        timeout: Connection/exec timeout in seconds.

    Returns:
        Combined stdout+stderr, truncated to ``max_chars`` with a
        ``"\n...[truncated]"`` marker appended when truncation occurs. On
        any error, a string beginning with ``"ssh error: "``.
    """
    client = paramiko.SSHClient()
    # NOTE: we accept the first host key we see, but TOFU-check it below so a
    # *changed* key is caught. See module docstring for the rationale.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ssh.host,
            port=ssh.port,
            username=ssh.username,
            password=ssh.password,
            timeout=timeout,
        )
        fp = _fingerprint(client)
        if fp is not None:
            err = verify_host_key(ssh, fp)
            if err is not None:
                return err
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out_bytes = stdout.read()
        err_bytes = stderr.read()
        out_text = out_bytes.decode("utf-8", errors="replace")
        err_text = err_bytes.decode("utf-8", errors="replace")
        combined = out_text + err_text
    except Exception as exc:  # noqa: BLE001 - never propagate to the agent loop
        logger.warning("ssh_exec to %s failed: %s", _host_id(ssh), exc, exc_info=True)
        return f"ssh error: {exc}"
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - closing must never raise
            logger.debug("error closing one-shot ssh client", exc_info=True)

    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n...[truncated]"
    return combined


class SSHSession:
    """A persistent SSH shell for one target, reused across agent turns.

    Keeps a single paramiko client with an interactive shell channel. Commands
    are written to the shell followed by a marker echo; output is read until
    the marker (with the exit status embedded) comes back. Because it is one
    shell, ``cd``, exported variables, and nested ``ssh``/``su`` sessions
    persist between commands — matching what a human at a terminal expects.

    Thread-safe: a per-session lock serialises concurrent exec calls (the web
    server can stream multiple chats against the same box).
    """

    def __init__(self, ssh: SSHConfig) -> None:
        self._ssh = ssh
        self._client: paramiko.SSHClient | None = None
        self._chan = None
        self._lock = threading.Lock()

    # -- connection management ------------------------------------------------

    def _connect(self) -> str | None:
        """(Re)open the client and shell. Returns an error string or None."""
        self.close()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self._ssh.host,
                port=self._ssh.port,
                username=self._ssh.username,
                password=self._ssh.password,
                timeout=self._ssh.timeout,
            )
            fp = _fingerprint(client)
            if fp is not None:
                err = verify_host_key(self._ssh, fp)
                if err is not None:
                    try:
                        client.close()
                    except Exception:  # noqa: BLE001
                        pass
                    return err
            chan = client.invoke_shell(term="dumb", width=200, height=50)
            chan.settimeout(self._ssh.timeout)
            # Suppress terminal echo so command text isn't mirrored back into
            # the output we return, then drain the banner/prompt.
            chan.send("stty -echo 2>/dev/null; export PS1=''\n")
            self._read_until_end(chan, drain_only=True)
            self._client = client
            self._chan = chan
            logger.info("ssh session opened to %s", _host_id(self._ssh))
            return None
        except Exception as exc:  # noqa: BLE001 - surface as string, never raise
            logger.warning("ssh session connect to %s failed: %s",
                           _host_id(self._ssh), exc, exc_info=True)
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            return f"ssh error: {exc}"

    def _read_until_end(self, chan, drain_only: bool = False) -> tuple[str, int | None]:
        """Read channel output until the end-marker or timeout.

        Returns:
            ``(text_before_marker, exit_code_or_None)``. On timeout, whatever
            was read so far and None.
        """
        buf = b""
        while True:
            try:
                chunk = chan.recv(4096)
            except Exception:  # noqa: BLE001 - timeout or transport failure
                break
            if not chunk:  # channel closed by remote
                break
            buf += chunk
            text = buf.decode("utf-8", errors="replace")
            m = _END_RE.search(text)
            if m:
                return text[: m.start()], int(m.group(1))
        text = buf.decode("utf-8", errors="replace")
        if drain_only:
            return text, 0
        return text, None

    # -- public API -----------------------------------------------------------

    def exec(self, command: str, max_chars: int = 4000, timeout: int | None = None) -> str:
        """Run ``command`` in the persistent shell and return its output.

        Reconnects once transparently if the transport died between turns.
        Never raises; failures come back as ``"ssh error: ..."`` strings.
        """
        with self._lock:
            if self._chan is None:
                err = self._connect()
                if err is not None:
                    return err
            result = self._exec_once(command, max_chars)
            if result.startswith("ssh error: transport"):
                # One reconnect retry for dead-transport style failures only —
                # retrying a *command* failure would double-run it.
                logger.info("transport lost to %s; reconnecting", _host_id(self._ssh))
                err = self._connect()
                if err is not None:
                    return err
                result = self._exec_once(command, max_chars)
            return result

    def _exec_once(self, command: str, max_chars: int) -> str:
        chan = self._chan
        try:
            chan.settimeout(self._ssh.timeout)
            chan.send(command + "; printf '\\n__CEI_END_%s__\\n' $?\n")
            out, code = self._read_until_end(chan)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ssh session exec failed on %s: %s",
                           _host_id(self._ssh), exc, exc_info=True)
            return f"ssh error: transport: {exc}"
        if code is None:
            return out.strip() + "\n...[timed out — command still running or connection lost]"
        out = out.strip()
        if len(out) > max_chars:
            out = out[:max_chars] + "\n...[truncated]"
        return out

    def close(self) -> None:
        """Close the shell and client, swallowing (but logging) all errors."""
        for obj, label in ((self._chan, "channel"), (self._client, "client")):
            if obj is not None:
                try:
                    obj.close()
                except Exception:  # noqa: BLE001 - closing must never raise
                    logger.debug("error closing ssh %s", label, exc_info=True)
        self._chan = None
        self._client = None


# -- shared session cache ------------------------------------------------------

_sessions: dict[str, SSHSession] = {}
_sessions_lock = threading.Lock()


def session_exec(
    ssh: SSHConfig,
    command: str,
    max_chars: int = 4000,
    timeout: int = 15,
) -> str:
    """Execute ``command`` on the shared persistent session for ``ssh``.

    Same call signature and failure contract as :func:`ssh_exec`, so it is a
    drop-in for the agent loop; one session is kept per unique
    ``user@host:port`` target and reused across turns and chat messages.
    """
    key = _host_id(ssh)
    with _sessions_lock:
        session = _sessions.get(key)
        if session is None:
            session = SSHSession(ssh)
            _sessions[key] = session
    return session.exec(command, max_chars=max_chars, timeout=timeout)


def close_sessions() -> None:
    """Close every cached session (called on server shutdown / tests)."""
    with _sessions_lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session in sessions:
        session.close()
