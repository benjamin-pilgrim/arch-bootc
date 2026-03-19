from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from vm_smoke.config import env_flag
from vm_smoke.graphical import print_graphical_guest_diagnostics
from vm_smoke.ssh import base_ssh_cmd, print_sanitized_qemu_log_tail

if TYPE_CHECKING:
    from boot_vm_smoke import BootVmSmoke


def validate_environment(runner: BootVmSmoke) -> None:
    if shutil.which(runner.cfg.qemu_bin) is None:
        raise SystemExit(
            f"{runner.cfg.qemu_bin} is required for test-smoke-vm-local\n"
            "Install qemu-system-x86 (Ubuntu) or qemu-full/qemu-desktop (Arch) and retry."
        )
    if runner.cfg.vm_sandbox:
        if runner.cfg.qemu_accel != "kvm":
            raise SystemExit(
                f"Sandbox VM boots require KVM; refusing qemu accel '{runner.cfg.qemu_accel}'.\n"
                "This image currently does not boot reliably under TCG in sandbox mode.\n"
                "Use BOOTC_VM_QEMU_ACCEL=kvm and make /dev/kvm accessible, or run the non-sandbox VM flow."
            )
        if not (os.access("/dev/kvm", os.R_OK) and os.access("/dev/kvm", os.W_OK)):
            raise SystemExit(
                "Sandbox VM boots require read/write access to /dev/kvm.\n"
                "Current user cannot access /dev/kvm, so qemu would fall back to an unusable TCG path.\n"
                "Grant KVM access to the sandbox environment or run the non-sandbox VM flow."
            )
    if runner.cfg.qemu_display.startswith(("gtk", "sdl")):
        if runner.cfg.graphical_session_smoke and os.getuid() == 0 and not env_flag("BOOTC_VM_ALLOW_ROOT_GRAPHICS"):
            raise SystemExit(
                "Graphical VM smoke should be run without sudo.\n"
                "Root cannot usually access the current desktop display/socket authorization cleanly.\n"
                "Run 'mise run test-smoke-vm-graphical' as your user, or set BOOTC_VM_ALLOW_ROOT_GRAPHICS=1 if you are explicitly preserving display auth."
            )
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise SystemExit(
                f"Graphical QEMU display '{runner.cfg.qemu_display}' requires DISPLAY or WAYLAND_DISPLAY in the host environment.\n"
                "Set BOOTC_VM_QEMU_DISPLAY=none for non-graphical runs, or launch from a graphical host session."
            )
    if runner.cfg.vm_log_level not in {"quiet", "normal", "debug"}:
        raise SystemExit(f"Invalid BOOTC_VM_LOG_LEVEL='{runner.cfg.vm_log_level}' (expected: quiet|normal|debug)")
    if shutil.which("ss") is None:
        raise SystemExit("ss is required for VM port checks")
    port_check = runner.run_cmd(["ss", "-ltn", f"( sport = :{runner.cfg.ssh_port} )"], capture_output=True, check=False)
    if "LISTEN" in port_check.stdout:
        raise SystemExit(f"SSH forward port {runner.cfg.ssh_port} is already in use; set BOOTC_VM_SSH_PORT to another port.")


def ensure_image_and_bootable(runner: BootVmSmoke) -> None:
    if not runner.cfg.skip_image_checks:
        exists = runner.podman_cmd(["image", "exists", runner.cfg.image_ref], check=False)
        if exists.returncode != 0:
            runner.log(f"Image {runner.cfg.image_ref} not found; building it now...")
            env = os.environ.copy()
            env["BUILD_IMAGE_NAME"] = runner.cfg.image_name
            env["BUILD_IMAGE_TAG"] = runner.cfg.image_tag
            runner.run_cmd(["mise", "run", "build-log"], env=env)
        runner.image_id = runner.podman_image_id(runner.cfg.image_ref)
        verify = runner.podman_cmd(
            [
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                runner.cfg.image_ref,
                "-c",
                "command -v sshd >/dev/null 2>&1 && "
                "test -x /usr/lib/systemd/system-generators/systemd-ssh-generator && "
                "test -f /etc/systemd/network/20-wired.network && "
                "systemctl --root=/ is-enabled systemd-networkd.service >/dev/null && "
                "systemctl --root=/ is-enabled systemd-resolved.service >/dev/null",
            ],
            check=False,
        )
        if verify.returncode != 0:
            raise SystemExit(
                f"Image {runner.cfg.image_ref} is missing required VM networking or SSH prerequisites.\n"
                "Expected: sshd, systemd-ssh-generator, /etc/systemd/network/20-wired.network,\n"
                "and enabled systemd-networkd.service + systemd-resolved.service."
            )

    if not runner.cfg.skip_bootable_regen:
        regen = False
        reason = ""
        if not runner.cfg.bootable.exists():
            regen = True
            reason = f"Bootable image not found at {runner.cfg.bootable}"
        elif not runner.cfg.bootable_image_id_file.exists():
            regen = True
            reason = f"Bootable image stamp not found at {runner.cfg.bootable_image_id_file}"
        elif runner.cfg.bootable_image_id_file.read_text().strip() != runner.image_id:
            regen = True
            reason = f"Built image changed since {runner.cfg.bootable} was generated"
        if regen:
            runner.log(f"{reason}; generating bootable image now...")
            env = os.environ.copy()
            env["BUILD_IMAGE_NAME"] = runner.cfg.image_name
            env["BUILD_IMAGE_TAG"] = runner.cfg.image_tag
            runner.run_cmd(["mise", "run", "generate-bootable-image"], env=env)
            runner.cfg.bootable_image_id_file.write_text(f"{runner.image_id}\n")
    elif not runner.cfg.bootable.exists():
        raise SystemExit(
            f"Sandbox mode requires an existing bootable image at {runner.cfg.bootable}.\n"
            f"Generate it outside the sandbox first with: sudo BUILD_IMAGE_TAG={runner.cfg.image_tag} mise run generate-vm-artifact"
        )

    runner.cfg.bootable = runner.cfg.bootable.resolve()
    if runner.cfg.bootable_image_id_file.exists():
        runner.cfg.bootable_image_id_file = runner.cfg.bootable_image_id_file.resolve()
    if runner.cfg.vm_sandbox and runner.cfg.sandbox_require_artifact_stamp:
        if not runner.cfg.bootable_image_id_file.exists() or not runner.cfg.bootable_image_id_file.read_text().strip():
            raise SystemExit(
                f"Sandbox mode requires a non-empty artifact stamp at {runner.cfg.bootable_image_id_file}.\n"
                f"Generate it outside the sandbox first with: sudo BUILD_IMAGE_TAG={runner.cfg.image_tag} mise run generate-vm-artifact"
            )
        runner.debug("Using sandbox VM artifact:")
        runner.debug(f"  disk: {runner.cfg.bootable}")
        runner.debug(f"  stamp: {runner.cfg.bootable_image_id_file}")
        runner.debug(f"  image id: {runner.cfg.bootable_image_id_file.read_text().strip()}")


def run_interactive_mode(runner: BootVmSmoke) -> int:
    runner.log("VM is running.")
    runner.log(f"SSH: {shlex.join(base_ssh_cmd(runner))}")
    if runner.cfg.graphical_session_smoke:
        runner.log("Close the QEMU window or press Ctrl-C here to stop the VM.")
    assert runner.state.vm_proc is not None
    status = runner.state.vm_proc.wait()
    if status == 0:
        runner.state.boot_vm_success = True
    return status


def run_bats(runner: BootVmSmoke) -> int:
    env = os.environ.copy()
    env["BOOTC_VM_SSH_COMMAND"] = shlex.join(base_ssh_cmd(runner))
    env["BOOTC_VM_BOOT_TIMEOUT_S"] = str(runner.cfg.boot_timeout)
    env["BOOTC_VM_DIRECT_KERNEL_BOOT"] = runner.cfg.direct_kernel_boot
    env["BOOTC_VM_GRAPHICAL_SESSION_SMOKE"] = "1" if runner.cfg.graphical_session_smoke else "0"
    env["BOOTC_VM_HOMED_FIRSTBOOT_USER"] = runner.cfg.homed_firstboot_user
    env["BOOTC_VM_HOMED_FIRSTBOOT_UID"] = runner.cfg.homed_firstboot_uid
    bats = subprocess.Popen(["mise", "exec", "--", "bats", "tests/smoke/vm-bootc.bats"], env=env)
    assert runner.state.vm_proc is not None
    while bats.poll() is None:
        if runner.state.vm_proc.poll() is not None:
            print("mkosi/qemu exited before smoke tests completed")
            print_graphical_guest_diagnostics(runner)
            print_sanitized_qemu_log_tail(runner)
            bats.terminate()
            bats.wait(timeout=5)
            return 1
        try:
            text = runner.state.log_file.read_text(errors="replace")
        except FileNotFoundError:
            text = ""
        if re.search(r'Could not set up host forwarding rule|Address already in use|Could not access KVM kernel module|failed to initialize kvm|could not open disk image|Failed to get "write" lock', text):
            print("Detected fatal qemu error while smoke tests were running")
            print_graphical_guest_diagnostics(runner)
            print_sanitized_qemu_log_tail(runner)
            runner.state.vm_proc.terminate()
            bats.terminate()
            bats.wait(timeout=5)
            return 1
        time.sleep(2)
    status = bats.wait()
    if status != 0:
        print_graphical_guest_diagnostics(runner)
    else:
        runner.state.boot_vm_success = True
    return status


def ensure_vm_alive(runner: BootVmSmoke, message: str) -> None:
    if runner.state.vm_proc is not None and runner.state.vm_proc.poll() is not None:
        print(message)
        print_sanitized_qemu_log_tail(runner)
        raise SystemExit(1)


def cleanup(runner: BootVmSmoke) -> None:
    if getattr(runner, "_cleaned", False):
        return
    runner._cleaned = True
    if runner.state.log_tail_proc and runner.state.log_tail_proc.poll() is None:
        runner.state.log_tail_proc.terminate()
        try:
            runner.state.log_tail_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            runner.state.log_tail_proc.kill()
    if runner.state.vm_proc and runner.state.vm_proc.poll() is None:
        runner.state.vm_proc.terminate()
        try:
            runner.state.vm_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            runner.state.vm_proc.kill()
    if not runner.state.boot_vm_success:
        print(f"qemu vm log: {runner.state.log_file}")
        if runner.cfg.qemu_trace:
            print(f"qemu trace log: {runner.state.trace_file}")
        else:
            runner.state.trace_file.unlink(missing_ok=True)
    else:
        runner.state.trace_file.unlink(missing_ok=True)
        runner.state.log_file.unlink(missing_ok=True)
    for path in list(reversed(runner.state.temp_paths)):
        if path in {runner.state.log_file, runner.state.trace_file}:
            continue
        path.unlink(missing_ok=True)
    for directory in reversed(runner.state.temp_dirs):
        shutil.rmtree(directory, ignore_errors=True)
    if shutil.which("stty"):
        subprocess.run(["stty", "sane"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if sys.stdout.isatty() and os.access("/dev/tty", os.W_OK):
            with open("/dev/tty", "w", encoding="utf-8", errors="ignore") as tty:
                tty.write("\033[0m\033[?25h")
    except OSError:
        pass
