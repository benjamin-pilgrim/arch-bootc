from __future__ import annotations

import os
import pathlib
import shutil
import subprocess


IMAGE_REF = "localhost/arch-bootc:local"
HOST_IMAGE_REF = "arch-bootc:latest"
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
BASE_DIR = SCRIPTS_DIR.parent
BOOTABLE = BASE_DIR / "bootable.img"
STAMP = BASE_DIR / "bootable.img.image-id"
BOOTABLE_SIZE = "40G"
BUILD_TMPDIR = pathlib.Path("/tmp/arch-bootc-build")
HOST_BUILD_TMPDIR = pathlib.Path("/var/tmp/arch-bootc-build")
BUILD_LOG = BASE_DIR / "build.log"
FILESYSTEM = "ext4"


def passwordless_sudo_available() -> bool:
    return shutil.which("sudo") is not None and subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
    ).returncode == 0


def root_prefix(*, allow_systemd_run: bool = False) -> list[str]:
    if os.getuid() == 0:
        return []
    if shutil.which("run0"):
        return ["run0"]
    if passwordless_sudo_available():
        return ["sudo"]
    if allow_systemd_run and shutil.which("systemd-run") and subprocess.run(
        ["systemd-run", "--uid=0", "--wait", "--collect", "true"],
        capture_output=True,
    ).returncode == 0:
        return ["systemd-run", "--uid=0", "--wait", "--collect"]
    return []


def can_run_as_root(*, allow_systemd_run: bool = False) -> bool:
    return os.getuid() == 0 or bool(root_prefix(allow_systemd_run=allow_systemd_run))


def root_cmd(args: list[str], *, allow_systemd_run: bool = False) -> list[str]:
    return [*root_prefix(allow_systemd_run=allow_systemd_run), *args]


def root_cmd_required(args: list[str], *, allow_systemd_run: bool = False, action: str = "this operation") -> list[str]:
    if not can_run_as_root(allow_systemd_run=allow_systemd_run):
        helpers = "run0, passwordless sudo"
        if allow_systemd_run:
            helpers += ", or systemd-run"
        raise SystemExit(f"{action} requires root access via {helpers}.")
    return root_cmd(args, allow_systemd_run=allow_systemd_run)


def root_cmd_with_env(args: list[str], env: dict[str, str], *, allow_systemd_run: bool = False) -> list[str]:
    assignments = [f"{key}={value}" for key, value in env.items()]
    return root_cmd(["env", *assignments, *args], allow_systemd_run=allow_systemd_run)


def podman_cmd(args: list[str], *, allow_systemd_run: bool = False) -> list[str]:
    return root_cmd(["podman", *args], allow_systemd_run=allow_systemd_run)


def podman_cmd_required(args: list[str], *, allow_systemd_run: bool = False, action: str = "podman") -> list[str]:
    return root_cmd_required(["podman", *args], allow_systemd_run=allow_systemd_run, action=action)


def script_path(name: str) -> pathlib.Path:
    return SCRIPTS_DIR / name


def selinux_mount_args() -> list[str]:
    if pathlib.Path("/sys/fs/selinux").is_dir():
        return ["-v", "/sys/fs/selinux:/sys/fs/selinux"]
    return []


def parse_iec_size(value: str) -> int:
    units = {
        "": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
    }
    normalized = value.strip().upper()
    suffix = normalized[-1] if normalized and normalized[-1].isalpha() else ""
    number = normalized[:-1] if suffix else normalized
    if suffix not in units:
        raise ValueError(f"unsupported size suffix in {value!r}")
    return int(number) * units[suffix]
