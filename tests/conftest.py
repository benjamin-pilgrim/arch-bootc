from __future__ import annotations

import pathlib
import sys

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from host_ops import IMAGE_REF  # noqa: E402
from tests.support.podman import PodmanImage  # noqa: E402
from tests.support.vm import existing_guest, qemu_guest  # noqa: E402


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("arch-bootc")
    group.addoption("--bootc-vm", action="store_true", help="Boot a local qemu VM for VM tests.")
    group.addoption(
        "--bootc-vm-preset",
        choices=("sandbox", "graphical", "sandbox-graphical"),
        help="Use a predefined local qemu VM configuration.",
    )
    group.addoption("--bootc-vm-ssh-command", help="SSH command used to reach an already booted guest.")
    group.addoption("--bootc-vm-root-prefix", help="Prefix for privileged commands on an existing non-root guest.")
    group.addoption("--bootc-vm-keep", action="store_true", help="Keep qemu running after pytest exits.")
    group.addoption("--bootc-vm-graphical", action="store_true", help="Expect graphical guest smoke state.")
    group.addoption("--bootc-vm-boot-timeout", type=int, default=300, help="Maximum time to wait for the guest to boot.")
    group.addoption("--bootc-vm-command-timeout", type=int, default=20, help="Per-command SSH timeout for guest checks.")
    group.addoption("--bootc-vm-direct-kernel-boot", default="0", help="Whether the guest booted via direct kernel boot.")
    group.addoption("--bootc-vm-homed-user", default="smoke", help="First-boot homed user name.")
    group.addoption("--bootc-vm-homed-uid", default="60001", help="First-boot homed UID.")
    group.addoption("--bootc-vm-allow-failed-system-units", default="^$", help="Regex of system units allowed to fail.")
    group.addoption("--bootc-vm-allow-failed-user-units", default="^$", help="Regex of user units allowed to fail.")
    group.addoption(
        "--bootc-vm-require-online-upgrade-check",
        action="store_true",
        help="Run bootc upgrade --check inside the guest.",
    )


@pytest.fixture(scope="session")
def image_ref() -> str:
    return IMAGE_REF


@pytest.fixture(scope="session")
def container(image_ref: str) -> PodmanImage:
    return PodmanImage(image_ref)


@pytest.fixture(scope="session")
def vm_guest(pytestconfig: pytest.Config):
    if pytestconfig.getoption("--bootc-vm"):
        with qemu_guest(pytestconfig) as guest:
            yield guest
        return

    guest = existing_guest(pytestconfig)
    if guest is None:
        pytest.skip("VM tests require --bootc-vm or --bootc-vm-ssh-command.")
    guest.wait_for_ssh()
    yield guest
