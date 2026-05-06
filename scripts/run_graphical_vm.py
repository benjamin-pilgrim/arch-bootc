#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys

from host_ops import BASE_DIR, script_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the image, refresh the artifact, and boot the graphical VM.")
    parser.add_argument("vm_args", nargs=argparse.REMAINDER, help="Extra arguments passed to the VM preset runner.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    subprocess.run([sys.executable, str(script_path("build_image.py"))], check=True, cwd=BASE_DIR)
    subprocess.run([sys.executable, str(script_path("generate_vm_artifact.py"))], check=True, cwd=BASE_DIR)
    return subprocess.run([sys.executable, str(script_path("run_vm_preset.py")), "run-graphical", *args.vm_args], cwd=BASE_DIR).returncode


if __name__ == "__main__":
    raise SystemExit(main())
