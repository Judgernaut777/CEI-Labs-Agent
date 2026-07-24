"""SSH command execution tool.

Runs a single command over SSH and returns combined stdout+stderr. This
function is designed to be safe to call from the agent loop: it never
raises and always closes the client, returning any failure as an
``"ssh error: ..."`` string instead.
"""

from __future__ import annotations

import paramiko

from ..config import SSHConfig


def ssh_exec(
    ssh: SSHConfig,
    command: str,
    max_chars: int = 4000,
    timeout: int = 15,
) -> str:
    """Execute ``command`` over SSH and return combined output.

    Args:
        ssh: Connection settings (host, port, username, password, timeout).
        command: The shell command to run on the remote host.
        max_chars: Maximum characters of output to return before truncating.
        timeout: Connection/exec timeout in seconds.

    Returns:
        Combined stdout+stderr, truncated to ``max_chars`` with a
        ``"\\n...[truncated]"`` marker appended when truncation occurs. On
        any error, a string beginning with ``"ssh error: "``.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ssh.host,
            port=ssh.port,
            username=ssh.username,
            password=ssh.password,
            timeout=timeout,
        )
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out_bytes = stdout.read()
        err_bytes = stderr.read()
        out_text = out_bytes.decode("utf-8", errors="replace")
        err_text = err_bytes.decode("utf-8", errors="replace")
        combined = out_text + err_text
    except Exception as exc:  # noqa: BLE001 - never propagate to the agent loop
        return f"ssh error: {exc}"
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - closing must never raise
            pass

    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n...[truncated]"
    return combined
