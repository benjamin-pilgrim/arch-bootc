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
        test -f /usr/share/hypr/hypridle.conf
        test -f /usr/share/hypr/hyprpaper.conf
        test -f /usr/share/hypr/xdph.conf
        test -x /usr/share/hypr/scripts/terminal-from-active
        test -x /usr/share/hypr/scripts/browser-tab-to-chrome-app
        command -v lsof >/dev/null
        command -v wtype >/dev/null
        test -f /usr/share/backgrounds/arch-bootc/wallpaper.png
        test -f /etc/profile.d/hypr-user-dropins.sh
        test -f /etc/skel/.config/hypr/hyprland.conf.d/00-default.conf
        """
    )


def test_starship_prompt_is_system_managed(container: PodmanImage) -> None:
    container.shell(
        """
        set -eu
        command -v starship >/dev/null
        test -f /etc/starship.toml
        test -f /etc/profile.d/starship.sh
        grep -Fx "palette = 'gruvbox_dark'" /etc/starship.toml
        grep -Fx 'Arch = "󰣇 "' /etc/starship.toml
        unset STARSHIP_CONFIG
        . /etc/profile.d/starship.sh
        test "$STARSHIP_CONFIG" = /etc/starship.toml
        """
    )


def test_ssh_client_config_is_system_managed(container: PodmanImage) -> None:
    container.shell(
        """
        set -eu
        command -v ssh >/dev/null
        command -v aws >/dev/null
        command -v session-manager-plugin >/dev/null
        test -f /etc/ssh/ssh_config.d/10-arch-bootc.conf
        grep -Fx "Host *" /etc/ssh/ssh_config.d/10-arch-bootc.conf
        grep -Fx "    IdentityAgent ~/.1password/agent.sock" /etc/ssh/ssh_config.d/10-arch-bootc.conf
        grep -Fx "Host i-*" /etc/ssh/ssh_config.d/10-arch-bootc.conf
        grep -F "aws ec2-instance-connect send-ssh-public-key --instance-id %h" /etc/ssh/ssh_config.d/10-arch-bootc.conf
        grep -Fx "Host mi-*" /etc/ssh/ssh_config.d/10-arch-bootc.conf
        grep -F "aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters 'portNumber=%p'" /etc/ssh/ssh_config.d/10-arch-bootc.conf
        ssh -F /etc/ssh/ssh_config -G i-0123456789abcdef0 >/tmp/ssh-i.out
        grep -E "^identityagent .*/\\.1password/agent\\.sock$" /tmp/ssh-i.out
        grep -F 'proxycommand sh -c "aws ec2-instance-connect send-ssh-public-key --instance-id' /tmp/ssh-i.out
        ssh -F /etc/ssh/ssh_config -G mi-0123456789abcdef0 >/tmp/ssh-mi.out
        grep -E "^identityagent .*/\\.1password/agent\\.sock$" /tmp/ssh-mi.out
        grep -F 'proxycommand sh -c "aws ssm start-session --target' /tmp/ssh-mi.out
        """
    )


def test_waybar_ai_statusbar_support_is_system_managed(container: PodmanImage) -> None:
    container.shell(
        """
        set -eu
        test -f /usr/share/waybar/arch-bootc/config.jsonc
        test -f /usr/share/waybar/arch-bootc/conf.d/00-default.jsonc
        test -f /usr/share/waybar/arch-bootc/conf.d/10-waybar-ai-usage.jsonc
        test -f /usr/share/waybar/arch-bootc/style.css
        test -f /usr/lib/systemd/user/waybar.service.d/10-arch-bootc.conf
        test -f /usr/lib/systemd/user-preset/50-bp.preset
        test -x /usr/libexec/arch-bootc-waybar-ai-usage.py
        test -x /usr/libexec/arch-bootc-codex-usage
        test -x /usr/libexec/arch-bootc-claude-usage
        grep -Fx "enable waybar.service" /usr/lib/systemd/user-preset/50-bp.preset
        systemctl --root=/ --global is-enabled waybar.service >/dev/null
        grep -Fx "ExecStart=" /usr/lib/systemd/user/waybar.service.d/10-arch-bootc.conf
        grep -Fx "ExecStart=/usr/bin/waybar --config /usr/share/waybar/arch-bootc/config.jsonc --style /usr/share/waybar/arch-bootc/style.css" /usr/lib/systemd/user/waybar.service.d/10-arch-bootc.conf
        grep -F '"~/.config/waybar/conf.d/*.jsonc"' /usr/share/waybar/arch-bootc/config.jsonc
        grep -F '"/usr/share/waybar/arch-bootc/conf.d/*.jsonc"' /usr/share/waybar/arch-bootc/config.jsonc
        grep -F '"modules-right": ["custom/codex-usage", "custom/claude-usage"' /usr/share/waybar/arch-bootc/conf.d/00-default.jsonc
        grep -F '"/usr/libexec/arch-bootc-codex-usage"' /usr/share/waybar/arch-bootc/conf.d/10-waybar-ai-usage.jsonc
        grep -F '"/usr/libexec/arch-bootc-claude-usage"' /usr/share/waybar/arch-bootc/conf.d/10-waybar-ai-usage.jsonc
        """
    )


def test_hypridle_is_system_managed(container: PodmanImage) -> None:
    container.shell(
        """
        set -eu
        test -f /usr/share/hypr/hypridle.conf
        test -f /usr/lib/systemd/user/hypridle.service.d/10-arch-bootc.conf
        test -f /usr/lib/systemd/user-preset/50-bp.preset
        grep -Fx "enable hypridle.service" /usr/lib/systemd/user-preset/50-bp.preset
        systemctl --root=/ --global is-enabled hypridle.service >/dev/null
        grep -Fx "ExecStart=" /usr/lib/systemd/user/hypridle.service.d/10-arch-bootc.conf
        grep -Fx "ExecStart=/usr/bin/hypridle --config /usr/share/hypr/hypridle.conf" /usr/lib/systemd/user/hypridle.service.d/10-arch-bootc.conf
        grep -Fx "    lock_cmd = pidof hyprlock || hyprlock" /usr/share/hypr/hypridle.conf
        grep -Fx "    before_sleep_cmd = loginctl lock-session" /usr/share/hypr/hypridle.conf
        grep -Fx "    timeout = 300" /usr/share/hypr/hypridle.conf
        grep -Fx "    timeout = 330" /usr/share/hypr/hypridle.conf
        """
    )


def test_claude_statusline_rate_limit_recorder_is_managed(container: PodmanImage) -> None:
    container.shell(
        """
        set -eu
        test -f /etc/claude-code/managed-settings.json
        test -x /usr/libexec/arch-bootc-claude-statusline-rate-limits.py
        grep -F '"/usr/libexec/arch-bootc-claude-statusline-rate-limits.py"' /etc/claude-code/managed-settings.json
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
        grep -F "/usr/share/hypr/scripts/terminal-from-active fork-codex" /usr/share/hypr/override.d/10-desktop.conf
        grep -F "/usr/share/hypr/scripts/terminal-from-active new-codex" /usr/share/hypr/override.d/10-desktop.conf
        grep -F "/usr/share/hypr/scripts/browser-tab-to-chrome-app" /usr/share/hypr/override.d/10-desktop.conf
        grep -F "wpctl set-mute @DEFAULT_AUDIO_SINK@ 0; wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+" /usr/share/hypr/override.d/10-desktop.conf
        grep -F "wpctl set-mute @DEFAULT_AUDIO_SINK@ 0; wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-" /usr/share/hypr/override.d/10-desktop.conf
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
