#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys

from host_ops import BASE_DIR, IMAGE_REF, podman_cmd_required, selinux_mount_args


def main() -> int:
    tty_flag = "-it" if sys.stdin.isatty() and sys.stdout.isatty() else "-i"
    cmd = podman_cmd_required(
        [
            "run",
            "--rm",
            "--privileged",
            "--pid=host",
            tty_flag,
            *selinux_mount_args(),
            "-v",
            "/etc/containers:/etc/containers:Z",
            "-v",
            "/var/lib/containers:/var/lib/containers:Z",
            "-v",
            "/dev:/dev",
            "-e",
            "RUST_LOG=debug",
            "-v",
            f"{BASE_DIR}:/data",
            "--security-opt",
            "label=type:unconfined_t",
            IMAGE_REF,
            "bootc",
            *sys.argv[1:],
        ],
        allow_systemd_run=True,
        action="running bootc in the image",
    )
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
