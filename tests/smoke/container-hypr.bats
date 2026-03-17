#!/usr/bin/env bats

setup() {
  : "${IMAGE_UNDER_TEST:?IMAGE_UNDER_TEST must be set, e.g. arch-bootc:latest}"
}

@test "hypr config files are present in image" {
  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /usr/lib/environment.d/95-hyprland-config.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /usr/share/hypr/override.d/00-default.conf
  [ "$status" -eq 0 ]
}

@test "hypr entrypoint layering is correct" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -lc "grep -F 'source = /usr/share/hypr/override.d/*.conf' /usr/share/hypr/hyprland.conf"
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -lc "grep -F 'source = \$XDG_CONFIG_HOME/hypr/hyprland.conf' /usr/share/hypr/hyprland.conf"
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
