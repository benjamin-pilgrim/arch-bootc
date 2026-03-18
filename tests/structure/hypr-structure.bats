#!/usr/bin/env bats

setup() {
  : "${IMAGE_UNDER_TEST:?IMAGE_UNDER_TEST must be set, e.g. arch-bootc:latest}"
}

@test "hypr structure files exist" {
  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /usr/lib/environment.d/95-hyprland-config.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /usr/share/hypr/override.d/00-default.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /etc/profile.d/hypr-user-dropins.sh
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /etc/skel/.config/hypr/hyprland.conf.d/00-default.conf
  [ "$status" -eq 0 ]
}

@test "hypr env file points to system entrypoint" {
  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -Eq \
    '^HYPRLAND_CONFIG=/usr/share/hypr/hyprland\.conf$' \
    /usr/lib/environment.d/95-hyprland-config.conf
  [ "$status" -eq 0 ]
}

@test "hypr system entrypoint sources override and user config" {
  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -Eq \
    '^source = /usr/share/hypr/override\.d/\*\.conf$' \
    /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -F \
    'source = $XDG_CONFIG_HOME/hypr/hyprland.conf' \
    /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]
}

@test "bootstrap script includes user dropin source line" {
  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -F \
    'source = $XDG_CONFIG_HOME/hypr/hyprland.conf.d/*.conf' \
    /etc/profile.d/hypr-user-dropins.sh
  [ "$status" -eq 0 ]
}

@test "systemd-networkd is enabled in the image" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c \
    'systemctl --root=/ is-enabled systemd-networkd.service >/dev/null && \
     systemctl --root=/ is-enabled systemd-resolved.service >/dev/null'
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint test "$IMAGE_UNDER_TEST" -f /etc/systemd/network/20-wired.network
  [ "$status" -eq 0 ]
}
