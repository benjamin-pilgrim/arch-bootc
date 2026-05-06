#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys

from host_ops import BASE_DIR, script_path


def parse_args() -> None:
    parser = argparse.ArgumentParser(description="Run the full local test pipeline.")
    parser.parse_args()


def main() -> int:
    parse_args()
    steps = [
        [sys.executable, str(script_path("build_image.py"))],
        [sys.executable, str(script_path("generate_vm_artifact.py"))],
        [sys.executable, "-m", "pytest", "-m", "container"],
        [sys.executable, str(script_path("run_vm_preset.py")), "sandbox-graphical"],
        [sys.executable, str(script_path("run_vm_preset.py")), "graphical"],
    ]
    for step in steps:
        subprocess.run(step, check=True, cwd=BASE_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
