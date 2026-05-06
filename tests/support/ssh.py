from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass


@dataclass
class SshGuest:
    ssh_command: list[str]
    boot_timeout: int = 300
    command_timeout: int = 20
    direct_kernel_boot: str = "0"
    graphical_session_smoke: bool = False
    homed_user: str = "smoke"
    homed_uid: str = "60001"
    root_prefix: str = ""

    def run(
        self,
        script: str,
        *,
        check: bool = True,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [*self.ssh_command, script],
            capture_output=True,
            text=True,
            timeout=timeout or self.command_timeout,
            check=False,
        )
        if check:
            assert result.returncode == 0, command_failure(result)
        return result

    def wait_for_ssh(self) -> None:
        deadline = time.monotonic() + self.boot_timeout
        last_result: subprocess.CompletedProcess[str] | None = None
        while time.monotonic() < deadline:
            try:
                last_result = self.run("true", check=False, timeout=5)
            except subprocess.TimeoutExpired:
                last_result = None
            if last_result is not None and last_result.returncode == 0:
                return
            time.sleep(2)
        detail = command_failure(last_result) if last_result is not None else "SSH command timed out repeatedly."
        raise AssertionError(f"guest did not become reachable over SSH within {self.boot_timeout}s\n{detail}")

    def systemd_run(self, script: str) -> subprocess.CompletedProcess[str]:
        unit = f"arch-bootc-smoke-{time.time_ns()}"
        prefix = f"{self.root_prefix} " if self.root_prefix else ""
        return self.run(
            f"{prefix}systemd-run "
            f"--unit {shlex.quote(unit)} "
            "--wait --collect --quiet "
            f"/usr/bin/bash -lc {shlex.quote(script)}"
        )

    def root_run(self, script: str, *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        if not self.root_prefix:
            return self.run(script, timeout=timeout)
        return self.run(f"{self.root_prefix} /usr/bin/bash -lc {shlex.quote(script)}", timeout=timeout)

    def root_wait_until(
        self,
        script: str,
        *,
        timeout: int | None = None,
        interval: int = 2,
    ) -> subprocess.CompletedProcess[str]:
        if not self.root_prefix:
            return self.wait_until(script, timeout=timeout, interval=interval)
        return self.wait_until(
            f"{self.root_prefix} /usr/bin/bash -lc {shlex.quote(script)}",
            timeout=timeout,
            interval=interval,
        )

    def wait_until(self, script: str, *, timeout: int | None = None, interval: int = 2) -> subprocess.CompletedProcess[str]:
        deadline = time.monotonic() + (timeout or self.boot_timeout)
        last_result: subprocess.CompletedProcess[str] | None = None
        while time.monotonic() < deadline:
            last_result = self.run(script, check=False)
            if last_result.returncode == 0:
                return last_result
            time.sleep(interval)
        detail = command_failure(last_result) if last_result is not None else "command was never attempted"
        raise AssertionError(f"condition did not become true within {timeout or self.boot_timeout}s\n{detail}")


def command_failure(result: subprocess.CompletedProcess[str] | None) -> str:
    if result is None:
        return "no command result"
    return (
        f"command failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
