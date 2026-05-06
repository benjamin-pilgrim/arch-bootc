#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from host_ops import BASE_DIR, BUILD_LOG, BUILD_TMPDIR, IMAGE_REF, root_cmd_with_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local arch-bootc image.")
    parser.add_argument("--clean", action="store_true", help="Disable podman layer cache.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    BUILD_TMPDIR.mkdir(parents=True, exist_ok=True)
    layers = "false" if args.clean else "true"
    env_prefix = f"TMPDIR={BUILD_TMPDIR}"
    cmd = root_cmd_with_env(
        [
            "podman",
            "build",
            "--network=host",
            f"--layers={layers}",
            "-t",
            IMAGE_REF,
            ".",
        ],
        {"TMPDIR": str(BUILD_TMPDIR)},
    )
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=BASE_DIR)
    assert proc.stdout is not None
    with BUILD_LOG.open("w") as log:
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
    status = proc.wait()
    if status != 0:
        print(f"{env_prefix} {' '.join(cmd)} failed with exit status {status}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
