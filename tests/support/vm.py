from __future__ import annotations

import shlex
from contextlib import contextmanager
from typing import Iterator

import pytest

from boot_vm_smoke import BootVmSmoke
from run_vm_preset import config_for
from tests.support.ssh import SshGuest
from vm_smoke.config import Config
from vm_smoke.ssh import base_ssh_cmd


def existing_guest(pytestconfig: pytest.Config) -> SshGuest | None:
    ssh_command = pytestconfig.getoption("--bootc-vm-ssh-command")
    if not ssh_command:
        return None
    command = shlex.split(ssh_command)

    return SshGuest(
        command,
        boot_timeout=pytestconfig.getoption("--bootc-vm-boot-timeout"),
        command_timeout=pytestconfig.getoption("--bootc-vm-command-timeout"),
        direct_kernel_boot=pytestconfig.getoption("--bootc-vm-direct-kernel-boot"),
        graphical_session_smoke=pytestconfig.getoption("--bootc-vm-graphical"),
        homed_user=pytestconfig.getoption("--bootc-vm-homed-user"),
        homed_uid=pytestconfig.getoption("--bootc-vm-homed-uid"),
        root_prefix=pytestconfig.getoption("--bootc-vm-root-prefix") or "",
    )


@contextmanager
def qemu_guest(pytestconfig: pytest.Config) -> Iterator[SshGuest]:
    preset = pytestconfig.getoption("--bootc-vm-preset")
    cfg = config_for(preset) if preset else Config()
    runner = BootVmSmoke(cfg)
    try:
        runner.prepare_and_start()
        yield SshGuest(
            base_ssh_cmd(runner),
            boot_timeout=cfg.boot_timeout,
            command_timeout=20,
            direct_kernel_boot=cfg.direct_kernel_boot,
            graphical_session_smoke=cfg.graphical_session_smoke,
            homed_user=cfg.homed_firstboot_user,
            homed_uid=cfg.homed_firstboot_uid,
        )
    finally:
        if not pytestconfig.getoption("--bootc-vm-keep"):
            runner.cleanup()
