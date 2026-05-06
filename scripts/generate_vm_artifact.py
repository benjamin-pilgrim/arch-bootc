#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from host_ops import BASE_DIR, BOOTABLE, IMAGE_REF, STAMP, podman_cmd, script_path


def parse_args() -> None:
    parser = argparse.ArgumentParser(description="Build or refresh the local VM artifact.")
    parser.parse_args()


def run_podman(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(podman_cmd(args), check=check, capture_output=True, text=True)


def podman_image_id(ref: str) -> str:
    result = run_podman(["image", "inspect", "--format", "json", ref])
    data = json.loads(result.stdout)
    obj = data[0] if isinstance(data, list) else data
    return str(obj.get("Id", ""))


def main() -> int:
    parse_args()
    exists = run_podman(["image", "exists", IMAGE_REF], check=False)
    if exists.returncode != 0:
        print(f"Image {IMAGE_REF} not found; building it now...", flush=True)
        subprocess.run([sys.executable, str(script_path("build_image.py"))], check=True, cwd=BASE_DIR)

    image_id = podman_image_id(IMAGE_REF)
    if not image_id:
        print(f"Failed to determine image ID for {IMAGE_REF}", file=sys.stderr)
        return 1

    current_stamp = STAMP.read_text().strip() if STAMP.exists() else ""
    if not BOOTABLE.exists() or current_stamp != image_id:
        subprocess.run([sys.executable, str(script_path("generate_bootable_image.py"))], check=True, cwd=BASE_DIR)
        STAMP.write_text(f"{image_id}\n")

    print("VM artifact ready:")
    print(f"  image: {IMAGE_REF}")
    print(f"  image id: {image_id}")
    print(f"  disk: {BOOTABLE}")
    print(f"  stamp: {STAMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
