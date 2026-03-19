from __future__ import annotations

import os
import pathlib
import tempfile
from dataclasses import dataclass, field


def env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default) == "1"


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Config:
    vm_verbose: bool = field(default_factory=lambda: env_flag("BOOTC_VM_VERBOSE"))
    base_dir: pathlib.Path = field(default_factory=lambda: pathlib.Path(env_str("BUILD_BASE_DIR", ".")))
    bootable: pathlib.Path = field(init=False)
    bootable_image_id_file: pathlib.Path = field(init=False)
    boot_timeout: int = field(default_factory=lambda: int(env_str("BOOTC_VM_BOOT_TIMEOUT_S", "300")))
    image_name: str = field(default_factory=lambda: env_str("BUILD_IMAGE_NAME", "arch-bootc"))
    image_tag: str = field(default_factory=lambda: env_str("BUILD_IMAGE_TAG", "local"))
    qemu_bin: str = field(default_factory=lambda: env_str("QEMU_BIN", "qemu-system-x86_64"))
    vm_sandbox: bool = field(default_factory=lambda: env_flag("BOOTC_VM_SANDBOX"))
    qemu_accel: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_ACCEL"))
    qemu_cpu: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_CPU"))
    qemu_display: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_DISPLAY"))
    qemu_gpu: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_GPU"))
    ssh_port: int = field(default_factory=lambda: int(env_str("BOOTC_VM_SSH_PORT", "2222")))
    ssh_user: str = field(default_factory=lambda: env_str("BOOTC_VM_SSH_USER", "root"))
    qemu_mem: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_MEM", "4096"))
    qemu_smp: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_SMP", "4"))
    follow_qemu_log: bool = field(default_factory=lambda: env_flag("BOOTC_VM_FOLLOW_LOG", "1"))
    serial_kernel_log: bool = field(default_factory=lambda: env_flag("BOOTC_VM_SERIAL_KERNEL_LOG", "1"))
    vm_log_level: str = field(default_factory=lambda: env_str("BOOTC_VM_LOG_LEVEL", "quiet"))
    qemu_trace: bool = field(default_factory=lambda: env_flag("BOOTC_VM_QEMU_TRACE"))
    inject_loader_kargs_raw: str | None = field(default_factory=lambda: os.environ.get("BOOTC_VM_INJECT_LOADER_KARGS"))
    qemu_snapshot: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_SNAPSHOT"))
    qemu_overlay: str = field(default_factory=lambda: env_str("BOOTC_VM_QEMU_OVERLAY"))
    direct_kernel_boot: str = field(default_factory=lambda: env_str("BOOTC_VM_DIRECT_KERNEL_BOOT"))
    ssh_banner_timeout: int = field(init=False)
    wait_status_interval: int = field(default_factory=lambda: int(env_str("BOOTC_VM_WAIT_STATUS_INTERVAL_S", "10")))
    use_systemd_ssh_generator: bool = field(default_factory=lambda: env_flag("BOOTC_VM_USE_SYSTEMD_SSH_GENERATOR", "1"))
    systemd_ssh_listen: str = field(default_factory=lambda: env_str("BOOTC_VM_SYSTEMD_SSH_LISTEN", "0.0.0.0:22"))
    use_ssh_listen_credential: str = field(default_factory=lambda: env_str("BOOTC_VM_USE_SSH_LISTEN_CREDENTIAL"))
    graphical_session_smoke: bool = field(default_factory=lambda: env_flag("BOOTC_VM_GRAPHICAL_SESSION_SMOKE"))
    run_smoke_tests: bool = field(default_factory=lambda: env_flag("BOOTC_VM_RUN_TESTS", "1"))
    configure_homed_firstboot: bool = field(default_factory=lambda: env_flag("BOOTC_VM_CONFIGURE_HOMED_FIRSTBOOT", "1"))
    homed_firstboot_user: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_USER", "smoke"))
    homed_firstboot_real_name: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_REAL_NAME", "Smoke User"))
    homed_firstboot_uid: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_UID", "60001"))
    homed_firstboot_gid: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_GID", "60001"))
    homed_firstboot_groups: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_GROUPS", "wheel"))
    homed_firstboot_shell: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_SHELL", "/bin/bash"))
    homed_firstboot_storage: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_STORAGE", "directory"))
    homed_firstboot_password: str = field(default_factory=lambda: env_str("BOOTC_VM_HOMED_FIRSTBOOT_PASSWORD", "cinder742orbit9moss"))
    use_run0_podman: bool = field(default_factory=lambda: env_flag("BOOTC_PODMAN_USE_RUN0", "1"))
    skip_image_checks: bool = field(default_factory=lambda: env_flag("BOOTC_VM_SKIP_IMAGE_CHECKS"))
    skip_bootable_regen: bool = field(default_factory=lambda: env_flag("BOOTC_VM_SKIP_BOOTABLE_REGEN"))
    sandbox_require_artifact_stamp: bool = field(default_factory=lambda: env_flag("BOOTC_VM_SANDBOX_REQUIRE_ARTIFACT_STAMP", "1"))

    def __post_init__(self) -> None:
        self.bootable = pathlib.Path(env_str("BOOTABLE_IMAGE_PATH", str(self.base_dir / "bootable.img")))
        self.bootable_image_id_file = pathlib.Path(env_str("BOOTABLE_IMAGE_ID_FILE", f"{self.bootable}.image-id"))
        self.ssh_banner_timeout = int(env_str("BOOTC_VM_SSH_BANNER_TIMEOUT_S", str(self.boot_timeout)))

        if self.vm_sandbox:
            self.use_run0_podman = False
            self.skip_image_checks = True
            self.skip_bootable_regen = True
            if not self.direct_kernel_boot:
                self.direct_kernel_boot = "1"
            if not self.use_ssh_listen_credential:
                self.use_ssh_listen_credential = "1"
            if not self.qemu_accel:
                self.qemu_accel = "kvm"
            if not self.qemu_snapshot:
                self.qemu_snapshot = "0"
            if not self.qemu_overlay:
                self.qemu_overlay = "1"

        if not self.use_ssh_listen_credential:
            self.use_ssh_listen_credential = "1"
        if not self.qemu_accel:
            self.qemu_accel = "kvm:tcg"
        if not self.qemu_cpu:
            self.qemu_cpu = "host,-svm" if self.qemu_accel.startswith("kvm") else "max"
        if not self.qemu_display:
            self.qemu_display = "gtk,gl=off" if self.graphical_session_smoke else "none"
        if not self.qemu_gpu and self.graphical_session_smoke:
            self.qemu_gpu = "virtio-vga"
        if not self.qemu_snapshot:
            self.qemu_snapshot = "0"
        if not self.qemu_overlay:
            self.qemu_overlay = "1"
        if not self.direct_kernel_boot:
            self.direct_kernel_boot = "0"
        if self.vm_sandbox and self.inject_loader_kargs_raw is None:
            self.inject_loader_kargs_raw = "0"
        if self.inject_loader_kargs_raw is None:
            self.inject_loader_kargs_raw = "1"

    @property
    def inject_loader_kargs(self) -> bool:
        return self.inject_loader_kargs_raw == "1"

    @property
    def image_ref(self) -> str:
        return f"localhost/{self.image_name}:{self.image_tag}" if "/" not in self.image_name else f"{self.image_name}:{self.image_tag}"

    @property
    def qemu_serial_mode(self) -> str:
        return "socket" if self.graphical_session_smoke else "stdio"

    @property
    def homed_firstboot_image_path(self) -> str:
        return f"/home/{self.homed_firstboot_user}.homedir"


@dataclass
class RuntimeState:
    cfg: Config
    log_file: pathlib.Path = field(init=False)
    trace_file: pathlib.Path = field(init=False)
    bootable_runtime: pathlib.Path | None = None
    bootable_runtime_format: str = "raw"
    bootable_overlay: pathlib.Path | None = None
    ssh_key_dir: pathlib.Path | None = None
    ssh_private_key: pathlib.Path | None = None
    esp_image: pathlib.Path | None = None
    esp_extract_dir: pathlib.Path | None = None
    kernel_path: pathlib.Path | None = None
    initrd_path: pathlib.Path | None = None
    kernel_boot_append: str = ""
    firstboot_credential_dir: pathlib.Path | None = None
    ovmf_vars_runtime: pathlib.Path | None = None
    kernel_cmdline_file: pathlib.Path | None = None
    qemu_serial_socket: pathlib.Path | None = None
    graphical_bootstrap_log: pathlib.Path | None = None
    ssh_auth_reason_file: pathlib.Path | None = None
    vm_proc: object | None = None
    log_tail_proc: object | None = None
    temp_paths: list[pathlib.Path] = field(default_factory=list)
    temp_dirs: list[pathlib.Path] = field(default_factory=list)
    boot_vm_success: bool = False

    def __post_init__(self) -> None:
        self.log_file = pathlib.Path(tempfile.mkstemp(prefix="qemu-vm-smoke.", suffix=".log")[1])
        self.trace_file = pathlib.Path(tempfile.mkstemp(prefix="qemu-vm-trace.", suffix=".log")[1])
        self.temp_paths.extend([self.log_file, self.trace_file])
        self.bootable_runtime = self.cfg.bootable

    def make_temp_file(self, prefix: str, suffix: str = "", directory: pathlib.Path | None = None) -> pathlib.Path:
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(directory) if directory else None)
        os.close(fd)
        p = pathlib.Path(path)
        self.temp_paths.append(p)
        return p

    def make_temp_dir(self, prefix: str) -> pathlib.Path:
        p = pathlib.Path(tempfile.mkdtemp(prefix=prefix))
        self.temp_dirs.append(p)
        return p
