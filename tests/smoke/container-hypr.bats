#!/usr/bin/env bats

setup() {
  : "${IMAGE_UNDER_TEST:?IMAGE_UNDER_TEST must be set, e.g. arch-bootc:local}"
}

@test "hypr required files exist" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c '
    test -f /usr/lib/environment.d/95-hyprland-config.conf &&
    test -f /usr/lib/systemd/system/arch-bootc-sync-x11-keymap.service &&
    test -f /usr/share/hypr/hyprland.conf &&
    test -f /usr/share/hypr/override.d/00-default.conf &&
    test -f /usr/share/hypr/override.d/10-desktop.conf &&
    test -x /usr/libexec/sync-x11-keymap-from-vconsole.sh &&
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

@test "x11 keyboard sync converts vc keymap when x11 layout is unset" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -lc '
    set -eu
    bindir="$(mktemp -d)"
    state="$(mktemp)"
    log="$(mktemp)"
    printf unset >"$state"
    cat >"$bindir/localectl" <<'\''EOF'\''
#!/bin/sh
set -eu
state="${LOCALCTL_STATE:?}"
log="${LOCALCTL_LOG:?}"
case "$1" in
  status)
    if [ "$(cat "$state")" = "unset" ]; then
      cat <<'\''STATUS'\''
System Locale: LANG=C.UTF-8
VC Keymap: uk
X11 Layout: (unset)
STATUS
    else
      cat <<'\''STATUS'\''
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
  '
  [ "$status" -eq 0 ]
}

@test "x11 keyboard sync leaves a runtime sentinel even without keyboard data" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -lc '
    set -eu
    bindir="$(mktemp -d)"
    cat >"$bindir/localectl" <<'\''EOF'\''
#!/bin/sh
cat <<'\''STATUS'\''
System Locale: LANG=C.UTF-8
VC Keymap: (unset)
X11 Layout: (unset)
STATUS
EOF
    chmod +x "$bindir/localectl"
    PATH="$bindir:$PATH" /usr/libexec/sync-x11-keymap-from-vconsole.sh
    test -f /run/hypr/override.d/00-default.conf
    test ! -e /run/hypr/override.d/20-system-keyboard.conf
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

  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -Eq \
    '^source = /run/hypr/override\.d/\*\.conf$' \
    /usr/share/hypr/hyprland.conf
  [ "$status" -eq 0 ]

  run podman run --rm --entrypoint grep "$IMAGE_UNDER_TEST" -F \
    'source = $HOME/.config/hypr/hyprland.conf' \
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

@test "NetworkManager is enabled and networkd is disabled" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c '
    command -v nm-applet >/dev/null &&
    systemctl --root=/ is-enabled NetworkManager.service >/dev/null &&
    test -L /etc/systemd/system/multi-user.target.wants/NetworkManager.service &&
    systemctl --root=/ is-enabled arch-bootc-sync-x11-keymap.service >/dev/null &&
    test -L /etc/systemd/system/multi-user.target.wants/arch-bootc-sync-x11-keymap.service &&
    ! systemctl --root=/ is-enabled systemd-networkd.service >/dev/null &&
    test ! -L /etc/systemd/system/multi-user.target.wants/systemd-networkd.service
  '
  [ "$status" -eq 0 ]
}

@test "python3-validity is not boot-enabled" {
  run podman run --rm --entrypoint sh "$IMAGE_UNDER_TEST" -c '
    ! systemctl --root=/ is-enabled python3-validity.service >/dev/null &&
    test ! -L /etc/systemd/system/multi-user.target.wants/python3-validity.service
  '
  [ "$status" -eq 0 ]
}
