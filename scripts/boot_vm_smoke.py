#!/usr/bin/env python3
from __future__ import annotations

import atexit
import json
import os
import shutil
import signal
import subprocess

from vm_smoke.config import Config, RuntimeState
from vm_smoke.graphical import bootstrap_graphical_session
from vm_smoke.qemu import prepare_qemu_runtime, start_vm
from vm_smoke.runtime import cleanup, ensure_image_and_bootable, ensure_vm_alive, run_bats, run_interactive_mode, validate_environment
from vm_smoke.ssh import wait_for_ssh_auth, wait_for_ssh_banner


class BootVmSmoke:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.state = RuntimeState(cfg)
        self.ssh_extra_opts: list[str] = []
        self.image_id = ""
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:  # type: ignore[no-untyped-def]
        self.cleanup()
        raise SystemExit(128 + signum)

    def log(self, message: str) -> None:
        print(message, flush=True)

    def debug(self, message: str) -> None:
        if self.cfg.vm_verbose:
            print(message, flush=True)

    def run(self) -> int:
        validate_environment(self)
        ensure_image_and_bootable(self)
        prepare_qemu_runtime(self)
        start_vm(self)
        wait_for_ssh_banner(self)
        wait_for_ssh_auth(self)
        if self.cfg.graphical_session_smoke:
            bootstrap_graphical_session(self)
        if not self.cfg.run_smoke_tests:
            return run_interactive_mode(self)
        return run_bats(self)

    def run_cmd(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        capture_output: bool = False,
        text: bool = True,
        input_text: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=text,
            input=input_text,
            timeout=timeout,
            env=env,
        )

    def podman_cmd(self, args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        cmd = ["podman", *args]
        if self.cfg.use_run0_podman and os.getuid() != 0:
            if shutil.which("run0"):
                cmd = ["run0", *cmd]
            elif shutil.which("sudo"):
                cmd = ["sudo", *cmd]
        return self.run_cmd(cmd, **kwargs)

    def podman_image_id(self, image_ref: str) -> str:
        result = self.podman_cmd(["image", "inspect", "--format", "json", image_ref], capture_output=True)
        data = json.loads(result.stdout)
        obj = data[0] if isinstance(data, list) else data
        return str(obj.get("Id", ""))

    def ensure_vm_alive(self, message: str) -> None:
        ensure_vm_alive(self, message)

    def cleanup(self) -> None:
        cleanup(self)


def main() -> int:
    runner = BootVmSmoke(Config())
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
