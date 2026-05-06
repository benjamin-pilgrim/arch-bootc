from __future__ import annotations

import pytest

from tests.support.ssh import SshGuest

pytestmark = [pytest.mark.vm, pytest.mark.graphical]


def test_graphical_smoke_home_is_mounted_and_writable(vm_guest: SshGuest) -> None:
    if not vm_guest.graphical_session_smoke:
        pytest.skip("graphical session smoke is only enabled for graphical VM runs")
    wait_for_graphical_session(vm_guest)
    assert_graphical_home_ready(vm_guest)


def test_uwsm_can_launch_a_graphical_hyprland_session(vm_guest: SshGuest) -> None:
    if not vm_guest.graphical_session_smoke:
        pytest.skip("graphical session smoke is only enabled for graphical VM runs")
    wait_for_graphical_session(vm_guest)


def wait_for_graphical_session(guest: SshGuest) -> None:
    smoke_user = guest.homed_user
    smoke_uid = guest.homed_uid
    guest.root_wait_until(
        f"""
        set -eu
        homed=inactive
        bus=missing
        hypr=missing
        target=unknown
        if homectl inspect {smoke_user} --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
          homed=active
        fi
        if test -S /run/user/{smoke_uid}/bus; then
          bus=present
        fi
        if pgrep -u {smoke_uid} Hyprland >/dev/null 2>&1; then
          hypr=running
        fi
        if [ "$homed" = active ] && runuser -u {smoke_user} -- env \
          XDG_RUNTIME_DIR=/run/user/{smoke_uid} \
          DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{smoke_uid}/bus \
          systemctl --user is-active graphical-session.target >/dev/null 2>&1; then
          target=active
        fi
        printf 'homed=%s bus=%s hypr=%s target=%s\n' "$homed" "$bus" "$hypr" "$target"
        test "$homed" = active
        test "$bus" = present
        test "$hypr" = running
        """,
        timeout=guest.boot_timeout,
    )


def assert_graphical_home_ready(guest: SshGuest) -> None:
    smoke_user = guest.homed_user
    smoke_uid = guest.homed_uid
    guest.root_run(
        f"""
        set -eu
        echo '--- smoke passwd entry ---'
        getent passwd {smoke_user} || true
        echo '--- smoke homed state ---'
        homectl inspect {smoke_user} --no-pager 2>/dev/null || true
        echo '--- smoke home path ---'
        ls -ld /home/{smoke_user} /home/{smoke_user}/.local /home/{smoke_user}/.local/share 2>/dev/null || true
        echo '--- smoke mount ---'
        mount | grep -F '/home/{smoke_user}' || true
        echo '--- smoke write probe ---'
        runuser -u {smoke_user} -- env \
          HOME=/home/{smoke_user} \
          XDG_RUNTIME_DIR=/run/user/{smoke_uid} \
          DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{smoke_uid}/bus \
          bash -lc '
            set -eu
            test "$HOME" = /home/{smoke_user}
            install -d -m 700 "$HOME/.local/share"
            probe="$HOME/.local/share/.arch-bootc-smoke-write-test"
            : >"$probe"
            test -f "$probe"
            rm -f "$probe"
          '
        """,
        timeout=60,
    )
