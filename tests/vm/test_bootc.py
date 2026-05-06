from __future__ import annotations

import shlex

import pytest

from tests.support.ssh import SshGuest

pytestmark = pytest.mark.vm


def test_vm_becomes_reachable_over_ssh(vm_guest: SshGuest) -> None:
    vm_guest.wait_for_ssh()


def test_systemd_operational_and_can_execute_transient_units(vm_guest: SshGuest) -> None:
    vm_guest.run('state="$(systemctl is-system-running || true)"; [ "$state" = "running" ]')
    vm_guest.systemd_run("echo systemd-integration-ok >/dev/null")


def test_bootc_status_is_functional_in_guest(vm_guest: SshGuest) -> None:
    if vm_guest.direct_kernel_boot == "1":
        pytest.skip("bootc guest checks require the normal EFI/systemd-boot path")
    vm_guest.systemd_run("bootc status >/dev/null")


def test_bootc_online_upgrade_check_is_functional_when_required(
    vm_guest: SshGuest,
    pytestconfig: pytest.Config,
) -> None:
    if vm_guest.direct_kernel_boot == "1":
        pytest.skip("bootc guest checks require the normal EFI/systemd-boot path")
    if not pytestconfig.getoption("--bootc-vm-require-online-upgrade-check"):
        pytest.skip("online upgrade checks require a reachable bootc update source from inside the guest")
    vm_guest.systemd_run("bootc upgrade --check >/dev/null")


def test_hypr_system_configuration_exists_and_matches_expected_layering(vm_guest: SshGuest) -> None:
    vm_guest.systemd_run(
        r"""
        set -eu
        test -f /usr/lib/environment.d/95-hyprland-config.conf
        grep -Fx "HYPRLAND_CONFIG=/usr/share/hypr/hyprland.conf" /usr/lib/environment.d/95-hyprland-config.conf
        test -f /usr/lib/systemd/system/arch-bootc-sync-x11-keymap.service
        test -f /usr/share/hypr/hyprland.conf
        grep -Fx "source = /usr/share/hypr/override.d/*.conf" /usr/share/hypr/hyprland.conf
        grep -Fx "source = /run/hypr/override.d/*.conf" /usr/share/hypr/hyprland.conf
        grep -Fx "source = $HOME/.config/hypr/hyprland.conf" /usr/share/hypr/hyprland.conf
        test -f /usr/share/hypr/override.d/00-default.conf
        test -f /usr/share/hypr/override.d/10-desktop.conf
        test -f /usr/share/hypr/hyprlock.conf
        test -f /usr/share/hypr/hyprpaper.conf
        test -x /usr/libexec/sync-x11-keymap-from-vconsole.sh
        test -x /usr/share/hypr/scripts/terminal-from-active
        test -f /usr/share/backgrounds/arch-bootc/wallpaper.png
        """
    )


def test_hypr_user_bootstrap_script_is_present_and_idempotent(vm_guest: SshGuest) -> None:
    vm_guest.systemd_run(
        r"""
        set -eu
        test -f /etc/profile.d/hypr-user-dropins.sh
        old_home="${HOME:-}"
        tmp_home="$(mktemp -d)"
        export HOME="$tmp_home"
        unset XDG_CONFIG_HOME
        . /etc/profile.d/hypr-user-dropins.sh
        . /etc/profile.d/hypr-user-dropins.sh
        test -f "$tmp_home/.config/hypr/hyprland.conf"
        test -f "$tmp_home/.config/hypr/hyprland.conf.d/00-default.conf"
        count="$(grep -c "hyprland.conf.d/\*\.conf" "$tmp_home/.config/hypr/hyprland.conf")"
        test "$count" -eq 1
        rm -rf "$tmp_home"
        if [ -n "$old_home" ]; then
          export HOME="$old_home"
        else
          unset HOME
        fi
        """
    )


def test_hypr_runtime_dependencies_are_installed(vm_guest: SshGuest) -> None:
    vm_guest.systemd_run("command -v Hyprland >/dev/null && command -v uwsm >/dev/null && command -v hyprctl >/dev/null")


def test_systemd_has_no_failed_units_after_boot(vm_guest: SshGuest, pytestconfig: pytest.Config) -> None:
    assert_no_failed_units(vm_guest, pytestconfig)


def assert_no_failed_units(guest: SshGuest, pytestconfig: pytest.Config) -> None:
    system_allow_re = pytestconfig.getoption("--bootc-vm-allow-failed-system-units")
    user_allow_re = pytestconfig.getoption("--bootc-vm-allow-failed-user-units")
    graphical = "1" if guest.graphical_session_smoke else "0"
    guest.root_run(
        f"""
        set -eu
        smoke_user={shlex.quote(guest.homed_user)}
        smoke_uid={shlex.quote(guest.homed_uid)}
        system_allow_re={shlex.quote(system_allow_re)}
        user_allow_re={shlex.quote(user_allow_re)}

        echo '--- failed system units ---'
        failed_system=$(systemctl list-units --failed --no-legend --plain --no-pager 2>/dev/null || true)
        filtered_system=$(printf '%s\n' "$failed_system" | sed '/^$/d' | grep -Ev "$system_allow_re" || true)
        if [ -n "$filtered_system" ]; then
          printf '%s\n' "$filtered_system"
          echo '--- failed system unit status ---'
          printf '%s\n' "$filtered_system" | awk '{{print $1}}' | while read -r unit; do
            [ -n "$unit" ] || continue
            systemctl status --no-pager --full "$unit" 2>/dev/null || true
            echo "--- journalctl -u $unit ---"
            journalctl -b -u "$unit" --no-pager -n 80 2>/dev/null || true
          done
          exit 1
        fi
        echo 'none'

        if [ "{graphical}" = "1" ]; then
          echo '--- failed smoke user units ---'
          failed_user=$(
            runuser -u "$smoke_user" -- env \
              XDG_RUNTIME_DIR="/run/user/$smoke_uid" \
              DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$smoke_uid/bus" \
              systemctl --user list-units --failed --no-legend --plain --no-pager 2>/dev/null || true
          )
          filtered_user=$(printf '%s\n' "$failed_user" | sed '/^$/d' | grep -Ev "$user_allow_re" || true)
          if [ -n "$filtered_user" ]; then
            printf '%s\n' "$filtered_user"
            echo '--- failed smoke user unit status ---'
            printf '%s\n' "$filtered_user" | awk '{{print $1}}' | while read -r unit; do
              [ -n "$unit" ] || continue
              runuser -u "$smoke_user" -- env \
                XDG_RUNTIME_DIR="/run/user/$smoke_uid" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$smoke_uid/bus" \
                systemctl --user status --no-pager --full "$unit" 2>/dev/null || true
              echo "--- journalctl --user -u $unit ---"
              runuser -u "$smoke_user" -- env \
                XDG_RUNTIME_DIR="/run/user/$smoke_uid" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$smoke_uid/bus" \
                journalctl --user -b -u "$unit" --no-pager -n 80 2>/dev/null || true
            done
            exit 1
          fi
          echo 'none'
        fi
        """,
        timeout=60,
    )
