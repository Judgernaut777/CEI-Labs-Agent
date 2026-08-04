"""Tests for the destructive-command guard (cei_labs_agent.guard)."""

from __future__ import annotations

from cei_labs_agent.guard import blocked_observation, check_command


# -- blocked shapes -----------------------------------------------------------

def test_rm_rf_root_blocked() -> None:
    assert check_command("rm -rf /") is not None
    assert check_command("rm -rf /*") is not None
    assert check_command("rm -fr / ") is not None


def test_mkfs_and_dd_device_blocked() -> None:
    assert check_command("mkfs.ext4 /dev/sda") is not None
    assert check_command("dd if=/dev/zero of=/dev/sda bs=1M") is not None


def test_fork_bomb_blocked() -> None:
    assert check_command(":(){ :|:& };:") is not None


def test_shutdown_reboot_blocked() -> None:
    assert check_command("shutdown now") is not None
    assert check_command("reboot") is not None
    assert check_command("init 0") is not None


def test_recursive_chmod_root_blocked() -> None:
    assert check_command("chmod -R 777 /") is not None


def test_account_and_firewall_changes_blocked() -> None:
    assert check_command("useradd evil") is not None
    assert check_command("passwd root") is not None
    assert check_command("iptables -F") is not None


def test_killing_sshd_blocked() -> None:
    assert check_command("pkill sshd") is not None
    assert check_command("killall ssh") is not None


def test_blocked_observation_mentions_reason_and_no_execution() -> None:
    obs = blocked_observation("rm -rf /", "recursive force-delete from the filesystem root")
    assert "BLOCKED" in obs
    assert "not executed" in obs
    assert "recursive force-delete" in obs


# -- legitimate wargame commands must pass ------------------------------------

def test_harmless_commands_allowed() -> None:
    allowed = [
        "ls -la",
        "cat /etc/bandit_pass/bandit1",
        "rm -rf /tmp/mywork",          # deleting own scratch dir is fine
        "find / -name 'bandit*' 2>/dev/null",
        "nc localhost 30000",
        "sshpass -p x ssh bandit1@localhost",
        "crontab -l",
        "grep -r 'password' .",
        "python3 -c 'print(1)'",
        "chmod +x ./script.sh",        # non-recursive, own file
        "kill 12345",                  # killing a stray process, not sshd
    ]
    for cmd in allowed:
        assert check_command(cmd) is None, f"false positive on: {cmd}"
