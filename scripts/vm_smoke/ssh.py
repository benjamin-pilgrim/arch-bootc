from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boot_vm_smoke import BootVmSmoke


def wait_for_ssh_banner(runner: BootVmSmoke) -> None:
    if shutil.which("ssh-keyscan") is None:
        raise SystemExit("ssh-keyscan is required for vm SSH readiness checks (install openssh-client).")
    runner.log(f"Waiting for SSH banner on 127.0.0.1:{runner.cfg.ssh_port} (timeout: {runner.cfg.ssh_banner_timeout}s)...")
    start = time.time()
    last_status = start
    while True:
        result = runner.run_cmd(["ssh-keyscan", "-T", "2", "-p", str(runner.cfg.ssh_port), "127.0.0.1"], check=False, capture_output=True)
        if result.returncode == 0:
            runner.log(f"SSH banner is available on 127.0.0.1:{runner.cfg.ssh_port}")
            return
        runner.ensure_vm_alive("qemu exited before SSH banner became available")
        now = time.time()
        if now - start >= runner.cfg.ssh_banner_timeout:
            runner.log(f"Timed out waiting for SSH banner on 127.0.0.1:{runner.cfg.ssh_port}")
            print_sanitized_qemu_log_tail(runner)
            raise SystemExit(1)
        if runner.cfg.wait_status_interval > 0 and now - last_status >= runner.cfg.wait_status_interval:
            runner.debug(f"Still waiting for SSH banner on 127.0.0.1:{runner.cfg.ssh_port}...")
            last_status = now
        time.sleep(2)


def base_ssh_cmd(runner: BootVmSmoke) -> list[str]:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "NumberOfPasswordPrompts=0",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "GSSAPIAuthentication=no",
        "-o",
        "LogLevel=ERROR",
    ]
    cmd.extend(runner.ssh_extra_opts)
    cmd.extend(["-p", str(runner.cfg.ssh_port), f"{runner.cfg.ssh_user}@127.0.0.1"])
    return cmd


def wait_for_ssh_auth(runner: BootVmSmoke) -> None:
    if runner.state.ssh_private_key:
        runner.ssh_extra_opts = [
            "-i",
            str(runner.state.ssh_private_key),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "StrictHostKeyChecking=no",
        ]
    runner.log("Waiting for SSH authentication to succeed...")
    start = time.time()
    last_status = start
    reason_file = runner.state.make_temp_file("qemu-vm-ssh-auth.")
    runner.state.ssh_auth_reason_file = reason_file
    while True:
        with open(reason_file, "w", encoding="utf-8") as fh:
            result = subprocess.run(base_ssh_cmd(runner) + ["true"], stdout=subprocess.DEVNULL, stderr=fh, text=True, timeout=5)
        if result.returncode == 0:
            runner.log(f"SSH authentication is available on 127.0.0.1:{runner.cfg.ssh_port}")
            return
        reason = re.sub(r"\s+", " ", reason_file.read_text()).strip()
        if "System is booting up" in reason or "Please wait until boot process completes" in reason:
            reason = "guest boot is not complete yet (pam_nologin)"
        elif "Permission denied (publickey" in reason:
            reason = "SSH public key was rejected"
        elif "Connection refused" in reason:
            reason = "SSH daemon is not accepting authenticated sessions yet"
        elif "Host key verification failed" in reason:
            reason = "SSH host key verification failed"
        elif "Connection timed out" in reason or "Operation timed out" in reason:
            reason = "SSH connection timed out"
        elif not reason:
            reason = "no SSH error text captured"
        runner.ensure_vm_alive("qemu exited before SSH authentication became available")
        now = time.time()
        if now - start >= runner.cfg.ssh_banner_timeout:
            runner.log(f"Timed out waiting for SSH authentication on 127.0.0.1:{runner.cfg.ssh_port}")
            runner.log(f"Last SSH authentication blocker: {reason}")
            if reason == "guest boot is not complete yet (pam_nologin)":
                print_boot_blocker_log(runner)
            print_sanitized_qemu_log_tail(runner)
            raise SystemExit(1)
        if runner.cfg.wait_status_interval > 0 and now - last_status >= runner.cfg.wait_status_interval:
            runner.debug(f"Still waiting for SSH authentication on 127.0.0.1:{runner.cfg.ssh_port}... ({reason})")
            last_status = now
        time.sleep(2)


def ssh_run(
    runner: BootVmSmoke,
    remote_cmd: str,
    *,
    timeout: int = 20,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return runner.run_cmd(base_ssh_cmd(runner) + [remote_cmd], timeout=timeout, check=check, capture_output=capture_output)


def print_boot_blocker_log(runner: BootVmSmoke) -> None:
    try:
        lines = runner.state.log_file.read_text(errors="replace").splitlines()
    except FileNotFoundError:
        return
    matches = [
        line
        for line in lines
        if re.search(r"systemd-firstboot|systemd-homed-firstboot|firstboot|homed|failed|timed out|dependency failed|sshd|systemd-ssh-generator", line, re.I)
    ]
    if matches:
        print("--- boot blocker log ---")
        for line in matches[-120:]:
            print(line)


def sanitize_log_text(runner: BootVmSmoke, text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1bP.*?\x1b\\", "", text, flags=re.S)
    text = re.sub(r"\x1b\].*?(?:\x07|\x1b\\)", "", text, flags=re.S)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return text.replace("\r", "")


def print_sanitized_qemu_log_tail(runner: BootVmSmoke) -> None:
    if runner.cfg.graphical_session_smoke:
        print(f"qemu vm log: {runner.state.log_file}")
        return
    try:
        text = runner.state.log_file.read_text(errors="replace")
    except FileNotFoundError:
        return
    lines = [line for line in sanitize_log_text(runner, text).splitlines() if line.strip()]
    for line in lines[-200:]:
        print(line)
