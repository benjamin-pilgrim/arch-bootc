from __future__ import annotations

import pytest

from tests.support.podman import PodmanImage

pytestmark = pytest.mark.container


def test_hypr_required_files_exist(container: PodmanImage) -> None:
    container.shell(
        """
        test -f /usr/lib/environment.d/95-hyprland-config.conf
        test -f /usr/lib/systemd/system/arch-bootc-sync-x11-keymap.service
        test -f /usr/share/hypr/hyprland.conf
        test -f /usr/share/hypr/override.d/00-default.conf
        test -f /usr/share/hypr/override.d/10-desktop.conf
        test -x /usr/libexec/sync-x11-keymap-from-vconsole.sh
        test -f /usr/share/hypr/hyprlock.conf
        test -f /usr/share/hypr/hyprpaper.conf
        test -f /usr/share/hypr/xdph.conf
        test -x /usr/share/hypr/scripts/terminal-from-active
        test -f /usr/share/backgrounds/arch-bootc/wallpaper.png
        test -f /etc/profile.d/hypr-user-dropins.sh
        test -f /etc/skel/.config/hypr/hyprland.conf.d/00-default.conf
        """
    )


def test_x11_keyboard_sync_converts_vc_keymap_when_x11_layout_is_unset(container: PodmanImage) -> None:
    container.shell(
        r"""
        set -eu
        bindir="$(mktemp -d)"
        state="$(mktemp)"
        log="$(mktemp)"
        printf unset >"$state"
        cat >"$bindir/localectl" <<'EOF'
#!/bin/sh
set -eu
state="${LOCALCTL_STATE:?}"
log="${LOCALCTL_LOG:?}"
case "$1" in
  status)
    if [ "$(cat "$state")" = "unset" ]; then
      cat <<'STATUS'
System Locale: LANG=C.UTF-8
VC Keymap: uk
X11 Layout: (unset)
STATUS
    else
      cat <<'STATUS'
System Locale: LANG=C.UTF-8
VC Keymap: uk
X11 Layout: gb
X11 Model: pc105
STATUS
    fi
    ;;
  set-keymap)
    printf "%s\n" "$*" >>"$log"
    printf set >"$state"
    ;;
  *)
    exit 1
    ;;
esac
EOF
        chmod +x "$bindir/localectl"
        LOCALCTL_STATE="$state" LOCALCTL_LOG="$log" PATH="$bindir:$PATH" /usr/libexec/sync-x11-keymap-from-vconsole.sh
        grep -Fx "set-keymap uk" "$log"
        grep -Fx "    kb_layout = gb" /run/hypr/override.d/20-system-keyboard.conf
        grep -Fx "    kb_model = pc105" /run/hypr/override.d/20-system-keyboard.conf
        """
    )


def test_x11_keyboard_sync_recreates_runtime_drop_in_dir(container: PodmanImage) -> None:
    container.shell(
        r"""
        set -eu
        bindir="$(mktemp -d)"
        state="$(mktemp)"
        log="$(mktemp)"
        printf unset >"$state"
        cat >"$bindir/localectl" <<'EOF'
#!/bin/sh
set -eu
state="${LOCALCTL_STATE:?}"
log="${LOCALCTL_LOG:?}"
case "$1" in
  status)
    if [ "$(cat "$state")" = "unset" ]; then
      cat <<'STATUS'
System Locale: LANG=C.UTF-8
VC Keymap: uk
X11 Layout: (unset)
STATUS
    else
      cat <<'STATUS'
System Locale: LANG=C.UTF-8
VC Keymap: uk
X11 Layout: gb
X11 Model: pc105
STATUS
    fi
    ;;
  set-keymap)
    printf "%s\n" "$*" >>"$log"
    rm -rf /run/hypr
    printf set >"$state"
    ;;
  *)
    exit 1
    ;;
esac
EOF
        chmod +x "$bindir/localectl"
        LOCALCTL_STATE="$state" LOCALCTL_LOG="$log" PATH="$bindir:$PATH" /usr/libexec/sync-x11-keymap-from-vconsole.sh
        grep -Fx "set-keymap uk" "$log"
        test -f /run/hypr/override.d/00-default.conf
        grep -Fx "    kb_layout = gb" /run/hypr/override.d/20-system-keyboard.conf
        grep -Fx "    kb_model = pc105" /run/hypr/override.d/20-system-keyboard.conf
        """
    )


def test_x11_keyboard_sync_leaves_runtime_sentinel_without_keyboard_data(container: PodmanImage) -> None:
    container.shell(
        r"""
        set -eu
        bindir="$(mktemp -d)"
        cat >"$bindir/localectl" <<'EOF'
#!/bin/sh
cat <<'STATUS'
System Locale: LANG=C.UTF-8
VC Keymap: (unset)
X11 Layout: (unset)
STATUS
EOF
        chmod +x "$bindir/localectl"
        rm -f /etc/X11/xorg.conf.d/00-keyboard.conf
        PATH="$bindir:$PATH" /usr/libexec/sync-x11-keymap-from-vconsole.sh
        test -f /run/hypr/override.d/00-default.conf
        test ! -e /run/hypr/override.d/20-system-keyboard.conf
        """
    )


def test_account_databases_are_internally_consistent(container: PodmanImage) -> None:
    container.shell(
        """
        set -eu
        pwck -r || [ "$?" -eq 2 ]
        grpck -r || [ "$?" -eq 2 ]
        ! getent passwd makepkg >/dev/null
        ! getent group makepkg >/dev/null
        ! grep -q "^makepkg:" /etc/shadow
        if [ -e /etc/gshadow ]; then
          ! grep -q "^makepkg:" /etc/gshadow
        fi
        """
    )


def test_desktop_override_references_system_config_paths(container: PodmanImage) -> None:
    container.shell(
        """
        grep -F "hyprpaper --config /usr/share/hypr/hyprpaper.conf" /usr/share/hypr/override.d/10-desktop.conf
        grep -F "hyprlock --config /usr/share/hypr/hyprlock.conf" /usr/share/hypr/override.d/10-desktop.conf
        grep -F "preload = /usr/share/backgrounds/arch-bootc/wallpaper.png" /usr/share/hypr/hyprpaper.conf
        grep -F "path = /usr/share/backgrounds/arch-bootc/wallpaper.png" /usr/share/hypr/hyprlock.conf
        """
    )


def test_hypr_env_file_points_to_system_entrypoint(container: PodmanImage) -> None:
    container.grep(
        [
            "-Fx",
            "HYPRLAND_CONFIG=/usr/share/hypr/hyprland.conf",
            "/usr/lib/environment.d/95-hyprland-config.conf",
        ]
    )


def test_hyprland_conf_sources_overrides_and_user_config(container: PodmanImage) -> None:
    container.grep(["-Eq", r"^source = /usr/share/hypr/override\.d/\*\.conf$", "/usr/share/hypr/hyprland.conf"])
    container.grep(["-Eq", r"^source = /run/hypr/override\.d/\*\.conf$", "/usr/share/hypr/hyprland.conf"])
    container.grep(["-F", "source = $HOME/.config/hypr/hyprland.conf", "/usr/share/hypr/hyprland.conf"])


def test_bootstrap_script_is_idempotent(container: PodmanImage) -> None:
    container.shell(
        r"""
        set -eu
        tmp_home="$(mktemp -d)"
        export HOME="$tmp_home"
        unset XDG_CONFIG_HOME
        . /etc/profile.d/hypr-user-dropins.sh
        . /etc/profile.d/hypr-user-dropins.sh
        test -f "$tmp_home/.config/hypr/hyprland.conf"
        test -f "$tmp_home/.config/hypr/hyprland.conf.d/00-default.conf"
        count="$(grep -c "hyprland.conf.d/\*\.conf" "$tmp_home/.config/hypr/hyprland.conf")"
        test "$count" -eq 1
        """
    )


def test_networkmanager_enabled_and_networkd_disabled(container: PodmanImage) -> None:
    container.shell(
        """
        command -v nm-applet >/dev/null
        systemctl --root=/ is-enabled NetworkManager.service >/dev/null
        test -L /etc/systemd/system/multi-user.target.wants/NetworkManager.service
        systemctl --root=/ is-enabled arch-bootc-sync-x11-keymap.service >/dev/null
        test -L /etc/systemd/system/multi-user.target.wants/arch-bootc-sync-x11-keymap.service
        ! systemctl --root=/ is-enabled systemd-networkd.service >/dev/null
        test ! -L /etc/systemd/system/multi-user.target.wants/systemd-networkd.service
        """
    )


def test_python3_validity_is_not_boot_enabled(container: PodmanImage) -> None:
    container.shell(
        """
        ! systemctl --root=/ is-enabled python3-validity.service >/dev/null
        test ! -L /etc/systemd/system/multi-user.target.wants/python3-validity.service
        """
    )
