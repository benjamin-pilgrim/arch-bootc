#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys

from host_ops import BASE_DIR
from boot_vm_smoke import run_config
from vm_smoke.config import Config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a predefined local VM workflow.")
    parser.add_argument(
        "preset",
        choices=("sandbox", "graphical", "sandbox-graphical", "run-graphical"),
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra arguments passed to pytest.")
    return parser.parse_args()


def config_for(preset: str) -> Config:
    if preset == "sandbox":
        return Config(
            vm_sandbox=True,
            inject_loader_kargs_raw="0",
            skip_image_checks=True,
            skip_bootable_regen=True,
            sandbox_require_artifact_stamp=True,
        )
    if preset == "graphical":
        return Config(
            graphical_session_smoke=True,
            inject_loader_kargs_raw="0",
            follow_qemu_log=False,
            skip_image_checks=True,
            skip_bootable_regen=True,
        )
    if preset == "sandbox-graphical":
        return Config(
            vm_sandbox=True,
            graphical_session_smoke=True,
            inject_loader_kargs_raw="0",
            follow_qemu_log=False,
            skip_image_checks=True,
            skip_bootable_regen=True,
            sandbox_require_artifact_stamp=True,
        )
    if preset == "run-graphical":
        return Config(
            graphical_session_smoke=True,
            run_smoke_tests=False,
            inject_loader_kargs_raw="0",
            follow_qemu_log=False,
            skip_image_checks=True,
            skip_bootable_regen=True,
        )
    raise AssertionError(f"unhandled preset: {preset}")


def main() -> int:
    args = parse_args()
    if args.preset == "run-graphical":
        return run_config(config_for(args.preset))
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/vm",
            "--bootc-vm",
            "--bootc-vm-preset",
            args.preset,
            *args.pytest_args,
        ],
        cwd=BASE_DIR,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
