from __future__ import annotations

import textwrap

from .config import Config


def verbose_homed_diagnostics(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        echo '--- getent passwd ---'
        getent passwd {cfg.homed_firstboot_user} || true
        echo '--- loginctl user-status ---'
        loginctl user-status {cfg.homed_firstboot_user} 2>/dev/null || true
        echo '--- home image path ---'
        ls -ld /home/{cfg.homed_firstboot_user}.homedir 2>/dev/null || true
        echo '--- home blob dir ---'
        ls -ld /var/cache/systemd/home/{cfg.homed_firstboot_user} 2>/dev/null || true
        echo '--- homed service status ---'
        systemctl --no-pager --plain --full status systemd-homed.service 2>/dev/null || true
        echo '--- homed journal ---'
        journalctl -b -u systemd-homed.service --no-pager -n 80 2>/dev/null || true
        echo '--- tty/login journal ---'
        journalctl -b --no-pager -n 200 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|homed|home1' || true
        echo '--- seat status ---'
        loginctl seat-status seat0 2>/dev/null || true
        """
    )


def install_smoke_hypr_config(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        install -d -o {cfg.homed_firstboot_user} -g {cfg.homed_firstboot_user} -m 0755 {cfg.homed_firstboot_image_path}/.config/hypr/hyprland.conf.d
        install -d -o {cfg.homed_firstboot_user} -g {cfg.homed_firstboot_user} -m 0755 {cfg.homed_firstboot_image_path}/.local
        install -d -o {cfg.homed_firstboot_user} -g {cfg.homed_firstboot_user} -m 0755 {cfg.homed_firstboot_image_path}/.local/share
        install -d -o {cfg.homed_firstboot_user} -g {cfg.homed_firstboot_user} -m 0755 {cfg.homed_firstboot_image_path}/.local/state
rm -f {cfg.homed_firstboot_image_path}/.config/hypr/hyprland.conf.d/99-graphical-smoke.conf
        cat >/etc/profile.d/uwsm.sh <<'EOF'
if uwsm check may-start; then
    if [ "${{LOGNAME:-${{USER:-}}}}" = "{cfg.homed_firstboot_user}" ] && [ "${{XDG_VTNR:-}}" = "1" ]; then
        if uwsm start -e -D Hyprland hyprland.desktop >/tmp/uwsm-tty1.log 2>&1; then
            exit 0
        fi

        printf 'forced uwsm start failed for hyprland.desktop\n' >>/tmp/uwsm-tty1.log
        exec bash -l
    fi

    if uwsm select; then
        exec uwsm start default
    fi
fi
EOF
        """
    )


def enable_linger(cfg: Config) -> str:
    return f"set -eu\nloginctl enable-linger {cfg.homed_firstboot_user}"


def prepare_tty1_login(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        faillock --user {cfg.homed_firstboot_user} --reset >/dev/null 2>&1 || true
        systemctl restart getty@tty1.service >/dev/null 2>&1 || true
        systemctl restart serial-getty@ttyS0.service >/dev/null 2>&1 || true
        chvt 1 >/dev/null 2>&1 || true
        """
    )


def wait_for_homed_activation_readiness(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        start=$(date +%s)
        while true; do
          output=$(PASSWORD='{cfg.homed_firstboot_password}' homectl activate {cfg.homed_firstboot_user} 2>&1) && {{
            homectl deactivate {cfg.homed_firstboot_user} >/dev/null 2>&1 || true
            exit 0
          }}
          case "$output" in
            *"currently being used"*|*"operation on home"*)
              now=$(date +%s)
              if [ $((now - start)) -ge 60 ]; then
                printf '%s\n' "$output" >&2
                exit 1
              fi
              sleep 2
              ;;
            *)
              printf '%s\n' "$output" >&2
              exit 1
              ;;
          esac
        done
        """
    )


def reset_after_serial_attempt(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        faillock --user {cfg.homed_firstboot_user} --reset >/dev/null 2>&1 || true
        loginctl terminate-user {cfg.homed_firstboot_user} >/dev/null 2>&1 || true
        systemctl stop user@{cfg.homed_firstboot_uid}.service >/dev/null 2>&1 || true
        homectl deactivate {cfg.homed_firstboot_user} >/dev/null 2>&1 || true
        systemctl restart serial-getty@ttyS0.service >/dev/null 2>&1 || true
        """
    )


def serial_failure_diagnostics(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        echo '--- homed user ---'
        homectl inspect {cfg.homed_firstboot_user} --no-pager 2>/dev/null || true
        echo '--- tty/login journal ---'
        journalctl -b --no-pager -n 200 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|ttyS0|homed|home1' || true
        echo '--- serial getty status ---'
        systemctl status serial-getty@ttyS0.service --no-pager 2>/dev/null || true
        """
    )


def autologin_tty1_after_activation(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        install -d /run/systemd/system/getty@tty1.service.d
        cat >/run/systemd/system/getty@tty1.service.d/10-smoke-autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/usr/bin/agetty --autologin {cfg.homed_firstboot_user} --noreset --noclear --issue-file=/etc/issue:/etc/issue.d:/run/issue.d:/usr/lib/issue.d - linux
EOF
        systemctl daemon-reload
        systemctl restart getty@tty1.service
        chvt 1 >/dev/null 2>&1 || true
        sleep 1
        printf '\r\r' >/dev/tty1 || true
        """
    )


def wait_for_homed_login_activation(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        start=$(date +%s)
        while true; do
          if homectl inspect {cfg.homed_firstboot_user} --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
            exit 0
          fi
          now=$(date +%s)
          if [ $((now - start)) -ge 25 ]; then
            exit 1
          fi
          sleep 1
        done
        """
    )


def homed_login_failure_diagnostics(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        echo '--- homed user ---'
        homectl inspect {cfg.homed_firstboot_user} --no-pager 2>/dev/null || true
        echo '--- tty/login journal ---'
        journalctl -b --no-pager -n 200 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|homed|home1' || true
        echo '--- getty@tty1 status ---'
        systemctl status getty@tty1.service --no-pager 2>/dev/null || true
        """
    )


def graphical_guest_diagnostics(cfg: Config) -> str:
    return textwrap.dedent(
        f"""
        set -eu
        echo '--- homed user ---'
        homectl inspect {cfg.homed_firstboot_user} --no-pager 2>/dev/null || true
        echo '--- hyprland processes ---'
        ps -ef | grep -E '[H]yprland|[u]wsm|[a]getty .*tty1' || true
        if homectl inspect {cfg.homed_firstboot_user} --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
          echo '--- smoke user manager ---'
          runuser -u {cfg.homed_firstboot_user} -- env XDG_RUNTIME_DIR=/run/user/{cfg.homed_firstboot_uid} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{cfg.homed_firstboot_uid}/bus systemctl --user --no-pager --plain --full status graphical-session.target elephant.service walker.service 2>/dev/null || true
          echo '--- smoke user journal ---'
          runuser -u {cfg.homed_firstboot_user} -- env XDG_RUNTIME_DIR=/run/user/{cfg.homed_firstboot_uid} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{cfg.homed_firstboot_uid}/bus journalctl --user -b --no-pager -n 120 2>/dev/null || true
        fi
        echo '--- tty/login journal (post-attempt) ---'
        journalctl -b --no-pager -n 300 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|homed|home1' || true
        echo '--- pam login ---'
        sed -n '1,220p' /etc/pam.d/login 2>/dev/null || true
        echo '--- pam system-local-login ---'
        sed -n '1,220p' /etc/pam.d/system-local-login 2>/dev/null || true
        echo '--- getty@tty1 status ---'
        systemctl status getty@tty1.service --no-pager 2>/dev/null || true
        echo '--- uwsm smoke log ---'
        cat /tmp/uwsm-graphical-smoke.log 2>/dev/null || true
        echo '--- uwsm tty1 log ---'
        cat /tmp/uwsm-tty1.log 2>/dev/null || true
        """
    )
