#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess

from host_ops import (
    BASE_DIR,
    BOOTABLE,
    BOOTABLE_SIZE,
    FILESYSTEM,
    IMAGE_REF,
    parse_iec_size,
    podman_cmd_required,
    selinux_mount_args,
)


def parse_args() -> None:
    parser = argparse.ArgumentParser(description="Install the built image to bootable.img.")
    parser.parse_args()


def ensure_bootable_image() -> None:
    wanted = parse_iec_size(BOOTABLE_SIZE)
    current = BOOTABLE.stat().st_size if BOOTABLE.exists() else 0
    if current >= wanted:
        return
    if BOOTABLE.exists():
        BOOTABLE.unlink()
    with BOOTABLE.open("wb") as image:
        image.truncate(wanted)


def main() -> int:
    parse_args()
    ensure_bootable_image()
    install_cmd = podman_cmd_required(
        [
            "run",
            "--rm",
            "--privileged",
            "--pid=host",
            "-i",
            *selinux_mount_args(),
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
            "install",
            "to-disk",
            "--composefs-backend",
            "--via-loopback",
            f"/data/{BOOTABLE.name}",
            "--filesystem",
            FILESYSTEM,
            "--wipe",
            "--bootloader",
            "systemd",
        ],
        allow_systemd_run=True,
        action="generating the bootable image",
    )
    subprocess.run(install_cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
