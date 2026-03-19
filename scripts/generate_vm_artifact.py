#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def image_ref(image_name: str, image_tag: str) -> str:
    return f"localhost/{image_name}:{image_tag}" if "/" not in image_name else f"{image_name}:{image_tag}"


def podman_image_id(ref: str) -> str:
    result = subprocess.run(["podman", "image", "inspect", "--format", "json", ref], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    obj = data[0] if isinstance(data, list) else data
    return str(obj.get("Id", ""))


def main() -> int:
    base_dir = pathlib.Path(env_str("BUILD_BASE_DIR", "."))
    bootable = pathlib.Path(env_str("BOOTABLE_IMAGE_PATH", str(base_dir / "bootable.img")))
    bootable_image_id_file = pathlib.Path(env_str("BOOTABLE_IMAGE_ID_FILE", f"{bootable}.image-id"))
    image_name = env_str("BUILD_IMAGE_NAME", "arch-bootc")
    image_tag = env_str("BUILD_IMAGE_TAG", "local")
    ref = image_ref(image_name, image_tag)

    exists = subprocess.run(["podman", "image", "exists", ref], check=False)
    if exists.returncode != 0:
        print(f"Image {ref} not found; building it now...", flush=True)
        env = os.environ.copy()
        env["BUILD_IMAGE_NAME"] = image_name
        env["BUILD_IMAGE_TAG"] = image_tag
        subprocess.run(["mise", "run", "build-log"], check=True, env=env)

    image_id = podman_image_id(ref)
    if not image_id:
        print(f"Failed to determine image ID for {ref}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["BUILD_IMAGE_NAME"] = image_name
    env["BUILD_IMAGE_TAG"] = image_tag
    env["BUILD_BASE_DIR"] = str(base_dir)
    env["BOOTABLE_IMAGE_PATH"] = str(bootable)
    subprocess.run(["mise", "run", "generate-bootable-image"], check=True, env=env)
    bootable_image_id_file.write_text(f"{image_id}\n")

    print("VM artifact ready:")
    print(f"  image: {ref}")
    print(f"  image id: {image_id}")
    print(f"  disk: {bootable}")
    print(f"  stamp: {bootable_image_id_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
