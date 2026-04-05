from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import textwrap
from typing import TYPE_CHECKING

from vm_smoke.config import env_str

if TYPE_CHECKING:
    from boot_vm_smoke import BootVmSmoke


def strip_managed_kargs(runner: BootVmSmoke, value: str) -> str:
    patterns = [
        r"(^| )quiet($| )",
        r"(^| )console=ttyS0[^ ]*",
        r"(^| )console=tty0($| )",
        r"(^| )earlycon=[^ ]+",
        r"(^| )ignore_loglevel($| )",
        r"(^| )loglevel=[^ ]+",
        r"(^| )printk\.time=[^ ]+",
        r"(^| )rd\.systemd\.show_status=[^ ]+",
        r"(^| )systemd\.show_status=[^ ]+",
        r"(^| )systemd\.log_level=[^ ]+",
        r"(^| )systemd\.log_target=[^ ]+",
        r"(^| )rd\.debug($| )",
        r"(^| )rd\.udev\.log_level=[^ ]+",
        r"(^| )udev\.log_level=[^ ]+",
        r"(^| )systemd\.ssh_auto=[^ ]+",
        r"(^| )systemd\.ssh_listen=[^ ]+",
    ]
    result = value
    for pattern in patterns:
        result = re.sub(pattern, " ", result)
    return re.sub(r"\s+", " ", result).strip()


def default_kernel_cmdline(runner: BootVmSmoke) -> str:
    if runner.cfg.vm_log_level == "quiet":
        return "quiet console=ttyS0,115200 console=tty0 loglevel=3 rd.systemd.show_status=0 systemd.show_status=0 rd.udev.log_level=3 udev.log_level=3 systemd.log_level=notice"
    if runner.cfg.vm_log_level == "normal":
        return "console=ttyS0,115200 console=tty0 loglevel=4 rd.systemd.show_status=auto systemd.show_status=auto rd.udev.log_level=4 udev.log_level=4 systemd.log_level=info"
    return "console=ttyS0,115200 console=tty0 earlycon=uart,io,0x3f8,115200 ignore_loglevel loglevel=8 printk.time=1 rd.systemd.show_status=1 systemd.log_level=debug systemd.log_target=console rd.debug"


def effective_kernel_cmdline(runner: BootVmSmoke) -> str:
    cmdline = env_str("BOOTC_VM_KERNEL_CMDLINE", default_kernel_cmdline(runner))
    if not runner.cfg.serial_kernel_log:
        cmdline = re.sub(r"(^| )console=ttyS0[^ ]*", " ", cmdline)
        cmdline = re.sub(r"(^| )earlycon=[^ ]+", " ", cmdline)
        cmdline = re.sub(r"\s+", " ", cmdline).strip()
    if runner.cfg.use_systemd_ssh_generator:
        cmdline = f"{cmdline} systemd.ssh_auto=1"
        if runner.cfg.use_ssh_listen_credential != "1":
            cmdline = f"{cmdline} systemd.ssh_listen={runner.cfg.systemd_ssh_listen}"
    return cmdline.strip()


def prepare_qemu_runtime(runner: BootVmSmoke) -> None:
    if runner.cfg.inject_loader_kargs:
        if runner.cfg.vm_sandbox:
            raise SystemExit(
                "Sandbox mode cannot patch loader kernel args.\n"
                "Set BOOTC_VM_INJECT_LOADER_KARGS=0 and rely on fw_cfg kernel cmdline injection."
            )
        inject_loader_kargs(runner)

    if runner.cfg.qemu_overlay == "1":
        if shutil.which("qemu-img") is None:
            raise SystemExit("qemu-img is required for BOOTC_VM_QEMU_OVERLAY=1")
        overlay = runner.state.make_temp_file("qemu-vm-overlay.", ".qcow2")
        overlay.unlink(missing_ok=True)
        runner.run_cmd(["qemu-img", "create", "-f", "qcow2", "-F", "raw", "-b", str(runner.cfg.bootable), str(overlay)], capture_output=True)
        runner.state.bootable_overlay = overlay
        runner.state.bootable_runtime = overlay
        runner.state.bootable_runtime_format = "qcow2"
    else:
        runner.state.bootable_runtime = runner.cfg.bootable

    if runner.cfg.direct_kernel_boot == "1":
        prepare_direct_kernel_boot(runner)


def inject_loader_kargs(runner: BootVmSmoke) -> None:
    run_as_root: list[str] = [] if os.getuid() == 0 else ["sudo"]
    loopdev_proc = subprocess.run(
        [*run_as_root, "losetup", "-fP", "--show", str(runner.cfg.bootable)],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    loopdev = loopdev_proc.stdout.strip()
    esp_mount = runner.state.make_temp_dir("esp-mount.")
    try:
        runner.run_cmd([*run_as_root, "mount", f"{loopdev}p2", str(esp_mount)])
        for entry in sorted((esp_mount / "loader" / "entries").glob("*.conf")):
            lines = entry.read_text().splitlines()
            current_opts = ""
            for line in lines:
                if line.startswith("options "):
                    current_opts = line[len("options "):]
                    break
            base_opts = strip_managed_kargs(runner, current_opts)
            new_opts = base_opts
            effective = effective_kernel_cmdline(runner)
            if effective:
                new_opts = f"{new_opts} {effective}".strip() if new_opts else effective
            replaced = False
            new_lines: list[str] = []
            for line in lines:
                if line.startswith("options "):
                    new_lines.append(f"options {new_opts}")
                    replaced = True
                else:
                    new_lines.append(line)
            if not replaced:
                new_lines.append(f"options {new_opts}")
            temp = runner.state.make_temp_file("loader-entry.", ".conf")
            temp.write_text("\n".join(new_lines) + "\n")
            runner.run_cmd([*run_as_root, "cp", str(temp), str(entry)])
    finally:
        runner.run_cmd([*run_as_root, "umount", str(esp_mount)], check=False)
        runner.run_cmd([*run_as_root, "losetup", "-d", loopdev], check=False)
        shutil.rmtree(esp_mount, ignore_errors=True)


def prepare_direct_kernel_boot(runner: BootVmSmoke) -> None:
    if shutil.which("sfdisk") is None:
        raise SystemExit("sfdisk is required for BOOTC_VM_DIRECT_KERNEL_BOOT=1")
    if shutil.which("7z") is None:
        raise SystemExit("7z is required for BOOTC_VM_DIRECT_KERNEL_BOOT=1")
    esp_image = runner.state.make_temp_file("qemu-vm-esp.", ".img")
    esp_extract_dir = runner.state.make_temp_dir("qemu-vm-esp.")
    runner.state.esp_image = esp_image
    runner.state.esp_extract_dir = esp_extract_dir
    python_code = textwrap.dedent(
        """
        import json, subprocess, sys
        bootable, esp_image = sys.argv[1:3]
        data = json.loads(subprocess.check_output(["sfdisk", "-J", bootable], text=True))
        parts = data["partitiontable"]["partitions"]
        if len(parts) < 2:
            raise SystemExit(f"expected at least 2 partitions in {bootable}")
        esp = parts[1]
        start = int(esp["start"])
        size = int(esp["size"])
        subprocess.check_call([
            "dd", f"if={bootable}", f"of={esp_image}", "bs=512", f"skip={start}", f"count={size}", "status=none"
        ])
        """
    )
    runner.run_cmd(["python3", "-c", python_code, str(runner.cfg.bootable), str(esp_image)])
    runner.run_cmd(["7z", "x", "-y", str(esp_image), "loader/*", "EFI/Linux/*", f"-o{esp_extract_dir}"], capture_output=True)
    entries = sorted((esp_extract_dir / "loader" / "entries").glob("*"))
    if not entries:
        raise SystemExit(f"Failed to extract a loader entry from {runner.cfg.bootable}")
    loader_entry = entries[0]
    kernel_rel = ""
    initrd_rel = ""
    base_opts = ""
    for line in loader_entry.read_text().splitlines():
        if line.startswith("linux "):
            kernel_rel = line.split(" ", 1)[1]
        elif line.startswith("initrd "):
            initrd_rel = line.split(" ", 1)[1]
        elif line.startswith("options "):
            base_opts = line.split(" ", 1)[1]
    kernel_path = pathlib.Path(str(esp_extract_dir) + kernel_rel)
    initrd_path = pathlib.Path(str(esp_extract_dir) + initrd_rel)
    if not kernel_path.exists() or not initrd_path.exists():
        raise SystemExit(f"Failed to extract kernel/initrd from {runner.cfg.bootable}")
    runner.state.kernel_path = kernel_path
    runner.state.initrd_path = initrd_path
    append = strip_managed_kargs(runner, base_opts)
    effective = effective_kernel_cmdline(runner)
    if effective:
        append = f"{append} {effective}".strip() if append else effective
    runner.state.kernel_boot_append = append


def find_ovmf_pair(runner: BootVmSmoke) -> tuple[str, str] | None:
    pairs = [
        ("/usr/share/OVMF/OVMF_CODE.fd", "/usr/share/OVMF/OVMF_VARS.fd"),
        ("/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/OVMF/OVMF_VARS_4M.fd"),
        ("/usr/share/edk2/ovmf/OVMF_CODE.fd", "/usr/share/edk2/ovmf/OVMF_VARS.fd"),
        ("/usr/share/edk2-ovmf/x64/OVMF_CODE.fd", "/usr/share/edk2-ovmf/x64/OVMF_VARS.fd"),
    ]
    for code, vars_ in pairs:
        if pathlib.Path(code).exists() and pathlib.Path(vars_).exists():
            return code, vars_
    return None


def build_qemu_command(runner: BootVmSmoke) -> list[str]:
    cmd = [
        runner.cfg.qemu_bin,
        "-machine",
        f"q35,accel={runner.cfg.qemu_accel}",
        "-cpu",
        runner.cfg.qemu_cpu,
        "-m",
        runner.cfg.qemu_mem,
        "-smp",
        runner.cfg.qemu_smp,
        "-display",
        runner.cfg.qemu_display,
        "-object",
        "rng-random,id=rng0,filename=/dev/urandom",
        "-device",
        "virtio-rng-pci,rng=rng0",
        "-netdev",
        f"user,id=net0,hostfwd=tcp::{runner.cfg.ssh_port}-:22",
        "-device",
        "virtio-net-pci,netdev=net0,bootindex=2",
        "-drive",
        f"if=none,id=bootdisk,file={runner.state.bootable_runtime},format={runner.state.bootable_runtime_format}",
        "-device",
        "ich9-ahci,id=ahci",
        "-device",
        "ide-hd,drive=bootdisk,bus=ahci.0,bootindex=1",
        "-monitor",
        "none",
    ]
    if runner.cfg.qemu_serial_mode == "socket":
        runner.state.qemu_serial_socket = pathlib.Path(tempfile.mktemp(prefix="qemu-serial.", suffix=".sock"))
        cmd.extend([
            "-chardev",
            f"socket,id=serial0,path={runner.state.qemu_serial_socket},server=on,wait=off,logfile={runner.state.log_file},logappend=on",
            "-serial",
            "chardev:serial0",
        ])
    else:
        cmd.extend(["-serial", "stdio"])
    if runner.cfg.graphical_session_smoke:
        cmd.extend(["-device", runner.cfg.qemu_gpu, "-device", "usb-ehci,id=ehci", "-device", "usb-tablet,bus=ehci.0"])
    if runner.cfg.direct_kernel_boot != "1":
        cmd.extend(["-boot", "order=c"])
    if runner.cfg.qemu_snapshot == "1":
        cmd.append("-snapshot")
    if runner.cfg.use_systemd_ssh_generator:
        if shutil.which("ssh-keygen") is None:
            raise SystemExit("ssh-keygen is required for systemd-ssh-generator VM access (install openssh-client).")
        runner.state.ssh_key_dir = pathlib.Path(tempfile.mkdtemp(prefix="qemu-vm-key."))
        runner.state.temp_dirs.append(runner.state.ssh_key_dir)
        runner.state.ssh_private_key = runner.state.ssh_key_dir / "id_ed25519"
        runner.run_cmd(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "arch-bootc-vm-smoke", "-f", str(runner.state.ssh_private_key)])
        cmd.extend(["-fw_cfg", f"name=opt/io.systemd.credentials/ssh.authorized_keys.root,file={runner.state.ssh_private_key}.pub"])
    if runner.cfg.direct_kernel_boot == "1" or runner.cfg.configure_homed_firstboot:
        runner.state.firstboot_credential_dir = pathlib.Path(tempfile.mkdtemp(prefix="qemu-vm-firstboot."))
        runner.state.temp_dirs.append(runner.state.firstboot_credential_dir)
        tz = runner.state.firstboot_credential_dir / "firstboot.timezone"
        loc = runner.state.firstboot_credential_dir / "firstboot.locale"
        keymap = runner.state.firstboot_credential_dir / "firstboot.keymap"
        tz.write_text(f"{env_str('BOOTC_VM_FIRSTBOOT_TIMEZONE', 'UTC')}\n")
        loc.write_text(f"{env_str('BOOTC_VM_FIRSTBOOT_LOCALE', 'C.UTF-8')}\n")
        keymap.write_text(f"{env_str('BOOTC_VM_FIRSTBOOT_KEYMAP', 'us')}\n")
        cmd.extend([
            "-fw_cfg", f"name=opt/io.systemd.credentials/firstboot.timezone,file={tz}",
            "-fw_cfg", f"name=opt/io.systemd.credentials/firstboot.locale,file={loc}",
            "-fw_cfg", f"name=opt/io.systemd.credentials/firstboot.keymap,file={keymap}",
        ])
    if runner.cfg.use_systemd_ssh_generator and runner.cfg.use_ssh_listen_credential == "1":
        if runner.state.firstboot_credential_dir is None:
            runner.state.firstboot_credential_dir = pathlib.Path(tempfile.mkdtemp(prefix="qemu-vm-firstboot."))
            runner.state.temp_dirs.append(runner.state.firstboot_credential_dir)
        ssh_listen = runner.state.firstboot_credential_dir / "ssh.listen"
        ssh_listen.write_text(f"{runner.cfg.systemd_ssh_listen}\n")
        cmd.extend(["-fw_cfg", f"name=opt/io.systemd.credentials/ssh.listen,file={ssh_listen}"])
    if runner.cfg.configure_homed_firstboot:
        if shutil.which("openssl") is None:
            raise SystemExit("openssl is required for BOOTC_VM_CONFIGURE_HOMED_FIRSTBOOT=1")
        if runner.state.firstboot_credential_dir is None:
            runner.state.firstboot_credential_dir = pathlib.Path(tempfile.mkdtemp(prefix="qemu-vm-firstboot."))
            runner.state.temp_dirs.append(runner.state.firstboot_credential_dir)
        identity_file = runner.state.firstboot_credential_dir / f"home.create.{runner.cfg.homed_firstboot_user}"
        password_hash = runner.run_cmd(
            ["openssl", "passwd", "-6", "-salt", "codexsmoke", runner.cfg.homed_firstboot_password],
            capture_output=True,
        ).stdout.strip()
        groups = [g for g in runner.cfg.homed_firstboot_groups.split(",") if g]
        identity = {
            "userName": runner.cfg.homed_firstboot_user,
            "realName": runner.cfg.homed_firstboot_real_name,
            "homeDirectory": f"/home/{runner.cfg.homed_firstboot_user}",
            "imagePath": runner.cfg.homed_firstboot_image_path,
            "shell": runner.cfg.homed_firstboot_shell,
            "uid": int(runner.cfg.homed_firstboot_uid),
            "gid": int(runner.cfg.homed_firstboot_gid),
            "memberOf": groups,
            "storage": runner.cfg.homed_firstboot_storage,
            "enforcePasswordPolicy": False,
            "privileged": {"hashedPassword": [password_hash]},
            "secret": {"password": [runner.cfg.homed_firstboot_password]},
        }
        identity_file.write_text(json.dumps(identity, indent=2) + "\n")
        cmd.extend(["-fw_cfg", f"name=opt/io.systemd.credentials/home.create.{runner.cfg.homed_firstboot_user},file={identity_file}"])
    if runner.cfg.direct_kernel_boot == "1":
        cmd.extend(["-kernel", str(runner.state.kernel_path), "-initrd", str(runner.state.initrd_path), "-append", runner.state.kernel_boot_append])
    if runner.cfg.direct_kernel_boot != "1":
        pair = find_ovmf_pair(runner)
        if pair:
            ovmf_vars_runtime = runner.state.make_temp_file("OVMF_VARS.", ".fd")
            shutil.copyfile(pair[1], ovmf_vars_runtime)
            runner.state.ovmf_vars_runtime = ovmf_vars_runtime
            cmd.extend([
                "-drive", f"if=pflash,format=raw,readonly=on,file={pair[0]}",
                "-drive", f"if=pflash,format=raw,file={ovmf_vars_runtime}",
            ])
    if runner.cfg.direct_kernel_boot != "1" and runner.cfg.serial_kernel_log and not runner.cfg.inject_loader_kargs:
        kernel_cmdline_file = runner.state.make_temp_file("qemu-kcmdline.")
        kernel_cmdline_file.write_text(effective_kernel_cmdline(runner) + "\n")
        runner.state.kernel_cmdline_file = kernel_cmdline_file
        cmd.extend(["-fw_cfg", f"name=opt/org.systemd.stub.kernel-cmdline,file={kernel_cmdline_file}"])
    if runner.cfg.qemu_trace:
        cmd.extend(["-d", "guest_errors,cpu_reset", "-D", str(runner.state.trace_file), "-no-reboot"])
    return cmd


def start_vm(runner: BootVmSmoke) -> None:
    cmd = build_qemu_command(runner)
    stdout = open(runner.state.log_file, "a", encoding="utf-8")
    stderr = subprocess.STDOUT
    stdin = subprocess.DEVNULL if runner.cfg.qemu_serial_mode in {"socket", "stdio"} else None
    preexec_fn = os.setsid if shutil.which("setsid") else None
    runner.state.vm_proc = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr, text=True, preexec_fn=preexec_fn)
    if runner.cfg.follow_qemu_log:
        runner.state.log_tail_proc = subprocess.Popen(
            [
                "bash",
                "-lc",
                f"tail -n +1 -F {runner.state.log_file!s} | "
                "perl -ne 'BEGIN { $| = 1 } s/\\e\\[[0-9;?]*[ -\\/]*[@-~]//g; s/\\eP.*?\\e\\\\//g; s/\\e\\].*?(?:\\a|\\e\\\\)//g; s/\\r//g; print if /\\S/' | sed -u 's/^/[qemu] /'",
            ],
            text=True,
        )
