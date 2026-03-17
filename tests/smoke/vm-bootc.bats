#!/usr/bin/env bats

setup() {
  if [ -n "${BOOTC_VM_SSH_COMMAND:-}" ]; then
    # shellcheck disable=SC2206
    VM_SSH_COMMAND=( ${BOOTC_VM_SSH_COMMAND} )
    VM_SSH_MODE="command"
    return 0
  fi

  if [ -z "${BOOTC_VM_SSH:-}" ]; then
    skip "Set BOOTC_VM_SSH or BOOTC_VM_SSH_COMMAND to enable VM smoke checks"
  fi

  VM_SSH_MODE="destination"
}

wait_for_ssh() {
  local timeout_s="${BOOTC_VM_BOOT_TIMEOUT_S:-300}"
  local start now
  start="$(date +%s)"

  while true; do
    if vm_ssh true >/dev/null 2>&1; then
      return 0
    fi

    now="$(date +%s)"
    if [ $((now - start)) -ge "$timeout_s" ]; then
      return 1
    fi

    sleep 2
  done
}

vm_ssh() {
  local cmd_timeout="${BOOTC_VM_SSH_CMD_TIMEOUT_S:-20}"
  if [ "$VM_SSH_MODE" = "command" ]; then
    timeout "${cmd_timeout}s" "${VM_SSH_COMMAND[@]}" "$@"
    return
  fi

  local ssh_opts=(
    -o BatchMode=yes
    -o ConnectTimeout=5
    -o StrictHostKeyChecking=accept-new
    -o GSSAPIAuthentication=no
    -o KbdInteractiveAuthentication=no
    -o PasswordAuthentication=no
    -o NumberOfPasswordPrompts=0
  )
  if [ -n "${BOOTC_VM_SSH_EXTRA_OPTS:-}" ]; then
    # shellcheck disable=SC2206
    local extra_opts=( ${BOOTC_VM_SSH_EXTRA_OPTS} )
    ssh_opts+=( "${extra_opts[@]}" )
  fi
  timeout "${cmd_timeout}s" ssh "${ssh_opts[@]}" $BOOTC_VM_SSH "$@"
}

vm_systemd_run() {
  local script="$1"
  local unit="arch-bootc-smoke-$(date +%s%N)"
  local root_prefix="${BOOTC_VM_ROOT_PREFIX:-}"
  local escaped
  escaped="$(printf '%q' "$script")"

  if [ -n "$root_prefix" ]; then
    vm_ssh "$root_prefix systemd-run --unit \"$unit\" --wait --collect --quiet /usr/bin/bash -lc $escaped"
  else
    vm_ssh "systemd-run --unit \"$unit\" --wait --collect --quiet /usr/bin/bash -lc $escaped"
  fi
}

@test "vm becomes reachable over SSH" {
  run wait_for_ssh
  [ "$status" -eq 0 ]
}

@test "systemd is operational and can execute transient units" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_ssh 'state="$(systemctl is-system-running || true)"; [ "$state" = "running" ] || [ "$state" = "degraded" ]'
  [ "$status" -eq 0 ]

  run vm_systemd_run 'echo systemd-integration-ok >/dev/null'
  [ "$status" -eq 0 ]
}

@test "bootc commands are functional in guest" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_systemd_run 'bootc status >/dev/null'
  [ "$status" -eq 0 ]

  run vm_systemd_run 'bootc upgrade --check >/dev/null'
  [ "$status" -eq 0 ]
}

@test "hypr system configuration exists and matches expected layering" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_systemd_run '
    set -eu
    test -f /usr/lib/environment.d/95-hyprland-config.conf
    grep -Fx "HYPRLAND_CONFIG=/usr/share/hypr/hyprland.conf" /usr/lib/environment.d/95-hyprland-config.conf
    test -f /usr/share/hypr/hyprland.conf
    grep -Fx "source = /usr/share/hypr/override.d/*.conf" /usr/share/hypr/hyprland.conf
    grep -Fx "source = \$XDG_CONFIG_HOME/hypr/hyprland.conf" /usr/share/hypr/hyprland.conf
    test -f /usr/share/hypr/override.d/00-default.conf
  '
  [ "$status" -eq 0 ]
}

@test "hypr user bootstrap script is present and idempotent" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_systemd_run '
    set -eu
    test -f /etc/profile.d/hypr-user-dropins.sh

    old_home="$HOME"
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
    export HOME="$old_home"
  '
  [ "$status" -eq 0 ]
}

@test "hypr runtime dependencies are installed" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_systemd_run 'command -v Hyprland >/dev/null && command -v uwsm >/dev/null && command -v hyprctl >/dev/null'
  [ "$status" -eq 0 ]
}
