from __future__ import annotations

import socket
import time
from typing import TYPE_CHECKING

from vm_smoke.guest import (
    autologin_tty1_after_activation,
    enable_linger,
    graphical_guest_diagnostics,
    homed_login_failure_diagnostics,
    install_smoke_hypr_config,
    prepare_tty1_login,
    reset_after_serial_attempt,
    serial_failure_diagnostics,
    verbose_homed_diagnostics,
    wait_for_homed_activation_readiness,
    wait_for_homed_login_activation,
)
from vm_smoke.ssh import print_sanitized_qemu_log_tail, ssh_run

if TYPE_CHECKING:
    from boot_vm_smoke import BootVmSmoke


def run_graphical_bootstrap_step(runner: BootVmSmoke, step_name: str, step_cmd: str) -> None:
    runner.debug(f"Graphical bootstrap: {step_name}...")
    assert runner.state.graphical_bootstrap_log is not None
    result = ssh_run(runner, step_cmd, timeout=20, check=False, capture_output=True)
    runner.state.graphical_bootstrap_log.write_text((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0:
        print(f"Graphical session bootstrap failed during '{step_name}' (exit {result.returncode}).")
        content = runner.state.graphical_bootstrap_log.read_text()
        if content.strip():
            print("Bootstrap output:")
            print(content, end="" if content.endswith("\n") else "\n")
        else:
            print("Bootstrap produced no stdout/stderr.")
        print_sanitized_qemu_log_tail(runner)
        raise SystemExit(1)


def serial_socket_login(runner: BootVmSmoke) -> None:
    sock_path = runner.state.qemu_serial_socket
    if sock_path is None:
        raise SystemExit("QEMU serial socket is not available for graphical session bootstrap.")
    deadline = time.time() + 30
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    while True:
        try:
            sock.connect(str(sock_path))
            break
        except OSError:
            if time.time() >= deadline:
                raise SystemExit("Timed out connecting to QEMU serial socket")
            time.sleep(0.2)
    buffer = bytearray()
    password_sent = False

    def recv_until(patterns: list[bytes], timeout_s: int, poke: bool = False) -> bytes:
        end = time.time() + timeout_s
        poked = False
        compiled = [(pattern, __import__("re").compile(pattern, __import__("re").I)) for pattern in patterns]
        while time.time() < end:
            for pattern, regex in compiled:
                if regex.search(buffer):
                    return pattern
            try:
                chunk = sock.recv(4096)
                if chunk:
                    buffer.extend(chunk)
                    continue
            except socket.timeout:
                pass
            if poke and not poked:
                sock.sendall(b"\n")
                poked = True
            time.sleep(0.1)
        labels = ", ".join(pattern.decode() for pattern in patterns)
        raise SystemExit(f"Timed out waiting for serial prompt: [{labels}]")

    recv_until([b"login:\\s*$", b"archlinux login:\\s*$"], 20, poke=True)
    sock.sendall(runner.cfg.homed_firstboot_user.encode("ascii") + b"\n")
    recv_until([b"password:\\s*$"], 10)
    sock.sendall(runner.cfg.homed_firstboot_password.encode("ascii") + b"\n")
    password_sent = True
    result = recv_until(
        [
            b"login incorrect",
            b"authentication failure",
            b"too many unsuccessful login attempts",
            b"last login",
            b"\\$\\s*$",
            b"#\\s*$",
            b"\\[.*@.*\\]\\$\\s*$",
            b"login:\\s*$",
            b"archlinux login:\\s*$",
        ],
        15,
    )
    transcript = buffer.decode("utf-8", "replace")
    if result in (b"login incorrect", b"authentication failure", b"too many unsuccessful login attempts"):
        raise SystemExit(f"Serial login was rejected\n--- serial transcript ---\n{transcript}")
    if password_sent and result in (b"login:\\s*$", b"archlinux login:\\s*$"):
        raise SystemExit(f"Serial login returned to login prompt before reaching a shell\n--- serial transcript ---\n{transcript}")
    sock.close()


def bootstrap_graphical_session(runner: BootVmSmoke) -> None:
    runner.log(f"Bootstrapping graphical session for homed user '{runner.cfg.homed_firstboot_user}'...")
    runner.state.graphical_bootstrap_log = runner.state.make_temp_file("qemu-vm-graphical-bootstrap.", ".log")
    if runner.cfg.vm_verbose:
        print("Graphical bootstrap: initial homed state...")
        result = ssh_run(runner, f"homectl inspect {runner.cfg.homed_firstboot_user} --no-pager 2>/dev/null || true", timeout=10, check=False, capture_output=True)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        print("Graphical bootstrap: homed account diagnostics...")
        result = ssh_run(runner, verbose_homed_diagnostics(runner.cfg), timeout=15, check=False, capture_output=True)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    exists = ssh_run(runner, f"getent passwd {runner.cfg.homed_firstboot_user} >/dev/null", timeout=10, check=False)
    if exists.returncode != 0:
        print(f"Expected homed user '{runner.cfg.homed_firstboot_user}' to exist after boot, but it was not present.")
        print("The graphical smoke path will not synthesize the user at runtime.")
        print("This indicates the firstboot homed provisioning path did not materialize the account.")
        print_sanitized_qemu_log_tail(runner)
        raise SystemExit(1)

    run_graphical_bootstrap_step(runner, "install smoke Hypr config", install_smoke_hypr_config(runner.cfg))
    run_graphical_bootstrap_step(runner, "enable linger", enable_linger(runner.cfg))
    run_graphical_bootstrap_step(runner, "prepare tty1 login", prepare_tty1_login(runner.cfg))
    run_graphical_bootstrap_step(runner, "wait for homed activation readiness", wait_for_homed_activation_readiness(runner.cfg))
    if runner.cfg.qemu_serial_mode != "socket" or runner.state.qemu_serial_socket is None:
        print("Graphical session bootstrap requires a QEMU serial socket.")
        print_sanitized_qemu_log_tail(runner)
        raise SystemExit(1)
    runner.debug("Graphical bootstrap: inject serial login via QEMU serial socket...")
    time.sleep(2)
    serial_login_ok = False
    for _ in range(3):
        try:
            serial_socket_login(runner)
            serial_login_ok = True
            break
        except SystemExit:
            ssh_run(runner, reset_after_serial_attempt(runner.cfg), timeout=10, check=False)
            time.sleep(3)
    if not serial_login_ok:
        print("Graphical session bootstrap failed during 'serial login injection'.")
        result = ssh_run(runner, serial_failure_diagnostics(runner.cfg), timeout=15, check=False, capture_output=True)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        print_sanitized_qemu_log_tail(runner)
        raise SystemExit(1)
    run_graphical_bootstrap_step(runner, "autologin smoke on tty1 after homed activation", autologin_tty1_after_activation(runner.cfg))
    runner.debug("Graphical bootstrap: wait for homed login activation...")
    result = ssh_run(runner, wait_for_homed_login_activation(runner.cfg), timeout=30, check=False, capture_output=True)
    if result.returncode != 0:
        print(f"Graphical session bootstrap failed during 'wait for homed login activation' (exit {result.returncode}).")
        result = ssh_run(runner, homed_login_failure_diagnostics(runner.cfg), timeout=15, check=False, capture_output=True)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        print_sanitized_qemu_log_tail(runner)
        raise SystemExit(1)
    if runner.state.graphical_bootstrap_log:
        runner.state.graphical_bootstrap_log.unlink(missing_ok=True)


def print_graphical_guest_diagnostics(runner: BootVmSmoke) -> None:
    if not runner.cfg.graphical_session_smoke:
        return
    try:
        result = ssh_run(runner, graphical_guest_diagnostics(runner.cfg), timeout=15, check=False, capture_output=True)
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    except Exception:
        pass
