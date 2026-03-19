#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    use_run0 = os.environ.get("BOOTC_PODMAN_USE_RUN0", "1") == "1"
    wrapper_dir: pathlib.Path | None = None
    env = os.environ.copy()
    if use_run0 and os.getuid() != 0:
        podman_exec = None
        if shutil.which("run0"):
            podman_exec = "run0 podman \"$@\""
        elif shutil.which("sudo"):
            podman_exec = "sudo podman \"$@\""
        if podman_exec:
            wrapper_dir = pathlib.Path(tempfile.mkdtemp(prefix="podman-wrapper."))
            wrapper = wrapper_dir / "podman"
            wrapper.write_text(f"#!/bin/sh\nexec {podman_exec}\n")
            wrapper.chmod(0o755)
            env["PATH"] = f"{wrapper_dir}:{env['PATH']}"
    try:
        proc = subprocess.run(sys.argv[1:], env=env)
        return proc.returncode
    finally:
        if wrapper_dir is not None:
            shutil.rmtree(wrapper_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
