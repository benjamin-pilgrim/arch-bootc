#!/usr/bin/env bats

setup() {
  : "${IMAGE_UNDER_TEST:?IMAGE_UNDER_TEST must be set, e.g. arch-bootc:latest}"
}

@test "hypr required files exist" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c '
    test -f /usr/lib/environment.d/95-hyprland-config.conf &&
    test -f /usr/share/hypr/hyprland.conf &&
    test -f /usr/share/hypr/override.d/00-default.conf &&
    test -f /usr/share/hypr/override.d/10-desktop.conf &&
    test -f /usr/share/hypr/hyprlock.conf &&
    test -f /usr/share/hypr/hyprpaper.conf &&
    test -f /usr/share/hypr/xdph.conf &&
    test -x /usr/share/hypr/scripts/terminal-from-active &&
    test -f /usr/share/backgrounds/arch-bootc/wallpaper.png &&
    test -f /etc/profile.d/hypr-user-dropins.sh &&
    test -f /etc/skel/.config/hypr/hyprland.conf.d/00-default.conf
  '
  [ "$status" -eq 0 ]
}

@test "desktop override references system config paths" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c '
    grep -F "hyprpaper --config /usr/share/hypr/hyprpaper.conf" /usr/share/hypr/override.d/10-desktop.conf &&
    grep -F "hyprlock --config /usr/share/hypr/hyprlock.conf" /usr/share/hypr/override.d/10-desktop.conf &&
    grep -F "preload = /usr/share/backgrounds/arch-bootc/wallpaper.png" /usr/share/hypr/hyprpaper.conf &&
    grep -F "path = /usr/share/backgrounds/arch-bootc/wallpaper.png" /usr/share/hypr/hyprlock.conf
  '
  [ "$status" -eq 0 ]
}

@test "hypr env file points to system entrypoint" {
  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -Fx \
    'HYPRLAND_CONFIG=/usr/share/hypr/hyprland.conf' \
    /usr/lib/environment.d/95-hyprland-config.conf
  [ "$status" -eq 0 ]
}

@test "hyprland.conf sources overrides and user config" {
  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -Eq \
    '^source = /usr/share/hypr/override\.d/\*\.conf$' \
    /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -F \
    'source = $XDG_CONFIG_HOME/hypr/hyprland.conf' \
    /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]
}

@test "bootstrap script is idempotent" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -lc '
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
  '
  [ "$status" -eq 0 ]
}

@test "systemd-networkd is enabled" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c '
    systemctl --root=/ is-enabled systemd-networkd.service >/dev/null &&
    systemctl --root=/ is-enabled systemd-resolved.service >/dev/null &&
    test -f /etc/systemd/network/20-wired.network
  '
  [ "$status" -eq 0 ]
}
