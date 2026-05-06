#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile

from host_ops import BASE_DIR, HOST_BUILD_TMPDIR, HOST_IMAGE_REF, can_run_as_root, root_cmd, root_cmd_with_env


def parse_args() -> None:
    parser = argparse.ArgumentParser(description="Build the image, switch the host with bootc, and reboot.")
    parser.parse_args()


def read_image_id(path: pathlib.Path) -> str:
    raw = path.read_text().strip()
    return raw.removeprefix("sha256:")


def main() -> int:
    parse_args()
    if not can_run_as_root(allow_systemd_run=True):
        print("host:upgrade requires root access via run0, passwordless sudo, or systemd-run.")
        return 1

    HOST_BUILD_TMPDIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False) as iid:
        iidfile = pathlib.Path(iid.name)
    try:
        subprocess.run(
            root_cmd_with_env(
                [
                    "podman",
                    "build",
                    "--network=host",
                    "--layers=true",
                    "--iidfile",
                    str(iidfile),
                    "-t",
                    HOST_IMAGE_REF,
                    ".",
                ],
                {"TMPDIR": str(HOST_BUILD_TMPDIR)},
                allow_systemd_run=True,
            ),
            check=True,
            cwd=BASE_DIR,
        )
        image_id = read_image_id(iidfile)
        print(f"Built image: {image_id}", flush=True)
        subprocess.run(
            root_cmd(["bootc", "switch", "--transport", "containers-storage", image_id], allow_systemd_run=True),
            check=True,
        )
        subprocess.run(root_cmd(["reboot"], allow_systemd_run=True), check=True)
        return 0
    finally:
        iidfile.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
