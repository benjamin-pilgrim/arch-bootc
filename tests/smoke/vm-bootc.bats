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
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o GSSAPIAuthentication=no
    -o KbdInteractiveAuthentication=no
    -o PasswordAuthentication=no
    -o NumberOfPasswordPrompts=0
    -o LogLevel=ERROR
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

assert_no_failed_units() {
  local smoke_user="${BOOTC_VM_HOMED_FIRSTBOOT_USER:-smoke}"
  local smoke_uid="${BOOTC_VM_HOMED_FIRSTBOOT_UID:-60001}"
  local system_allow_re="${BOOTC_VM_ALLOWED_FAILED_SYSTEM_UNITS_RE:-^$}"
  local user_allow_re="${BOOTC_VM_ALLOWED_FAILED_USER_UNITS_RE:-^$}"

  vm_ssh "
    set -eu
    echo '--- failed system units ---'
    failed_system=\$(systemctl list-units --failed --no-legend --plain --no-pager 2>/dev/null || true)
    filtered_system=\$(printf '%s\n' \"\$failed_system\" | sed '/^$/d' | grep -Ev '${system_allow_re}' || true)
    if [ -n \"\$filtered_system\" ]; then
      printf '%s\n' \"\$filtered_system\"
      echo '--- failed system unit status ---'
      printf '%s\n' \"\$filtered_system\" | awk '{print \$1}' | while read -r unit; do
        [ -n \"\$unit\" ] || continue
        systemctl status --no-pager --full \"\$unit\" 2>/dev/null || true
        echo \"--- journalctl -u \$unit ---\"
        journalctl -b -u \"\$unit\" --no-pager -n 80 2>/dev/null || true
      done
      exit 1
    fi
    echo 'none'

    if [ \"${BOOTC_VM_GRAPHICAL_SESSION_SMOKE:-0}\" = \"1\" ]; then
      echo '--- failed smoke user units ---'
      failed_user=\$(
        runuser -u ${smoke_user} -- env \
          XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
          DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
          systemctl --user list-units --failed --no-legend --plain --no-pager 2>/dev/null || true
      )
      filtered_user=\$(printf '%s\n' \"\$failed_user\" | sed '/^$/d' | grep -Ev '${user_allow_re}' || true)
      if [ -n \"\$filtered_user\" ]; then
        printf '%s\n' \"\$filtered_user\"
        echo '--- failed smoke user unit status ---'
        printf '%s\n' \"\$filtered_user\" | awk '{print \$1}' | while read -r unit; do
          [ -n \"\$unit\" ] || continue
          runuser -u ${smoke_user} -- env \
            XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
            DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
            systemctl --user status --no-pager --full \"\$unit\" 2>/dev/null || true
          echo \"--- journalctl --user -u \$unit ---\"
          runuser -u ${smoke_user} -- env \
            XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
            DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
            journalctl --user -b -u \"\$unit\" --no-pager -n 80 2>/dev/null || true
        done
        exit 1
      fi
      echo 'none'
    fi
  "
}

wait_for_graphical_session() {
  local timeout_s="${BOOTC_VM_BOOT_TIMEOUT_S:-300}"
  local start now
  local smoke_user="${BOOTC_VM_HOMED_FIRSTBOOT_USER:-smoke}"
  local smoke_uid="${BOOTC_VM_HOMED_FIRSTBOOT_UID:-60001}"
  local last_status_at
  local status_file
  start="$(date +%s)"
  last_status_at="$start"
  status_file="$(mktemp)"
  trap 'rm -f "$status_file"' RETURN

  while true; do
    if vm_ssh "
      set -eu
      homed=inactive
      bus=missing
      hypr=missing
      target=unknown
      if homectl inspect ${smoke_user} --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
        homed=active
      fi
      if test -S /run/user/${smoke_uid}/bus; then
        bus=present
      fi
      if pgrep -u ${smoke_uid} Hyprland >/dev/null 2>&1; then
        hypr=running
      fi
      if [ "\$homed" = active ] && runuser -u ${smoke_user} -- env \
        XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
        DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
        systemctl --user is-active graphical-session.target >/dev/null 2>&1; then
        target=active
      fi
      printf 'homed=%s bus=%s hypr=%s target=%s\n' \"\$homed\" \"\$bus\" \"\$hypr\" \"\$target\"
      test \"\$homed\" = active
      test \"\$bus\" = present
      test \"\$hypr\" = running
    " >"$status_file" 2>/dev/null; then
      return 0
    fi

    now="$(date +%s)"
    if [ $((now - last_status_at)) -ge 10 ] && [ -s "$status_file" ]; then
      echo "Still waiting for graphical session: $(tr '\n' ' ' <"$status_file" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')" >&3
      last_status_at="$now"
    fi
    if [ $((now - start)) -ge "$timeout_s" ]; then
      echo "Graphical session did not become ready for user '${smoke_user}'."
      if [ -s "$status_file" ]; then
        echo "Last observed session state: $(tr '\n' ' ' <"$status_file" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
      fi
      vm_ssh "
        set -eu
        echo '--- homed user ---'
        homectl inspect ${smoke_user} --no-pager 2>/dev/null || true
        echo '--- hyprland processes ---'
        ps -ef | grep -E '[H]yprland|[u]wsm|[a]getty .*tty1' || true
        echo '--- smoke user manager ---'
        if homectl inspect ${smoke_user} --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
          runuser -u ${smoke_user} -- env \
            XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
            DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
            systemctl --user --no-pager --plain --full status graphical-session.target elephant.service walker.service 2>/dev/null || true
        else
          echo 'homed user is inactive; skipping user-manager status to avoid triggering activation attempts'
        fi
        echo '--- smoke user journal ---'
        if homectl inspect ${smoke_user} --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
          runuser -u ${smoke_user} -- env \
            XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
            DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
            journalctl --user -b --no-pager -n 120 2>/dev/null || true
        else
          echo 'homed user is inactive; skipping user journal to avoid triggering activation attempts'
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
      " >&3 2>&3 || true
      return 1
    fi

    sleep 2
  done
}

assert_graphical_home_ready() {
  local smoke_user="${BOOTC_VM_HOMED_FIRSTBOOT_USER:-smoke}"
  local smoke_uid="${BOOTC_VM_HOMED_FIRSTBOOT_UID:-60001}"

  vm_ssh "
    set -eu
    echo '--- smoke passwd entry ---'
    getent passwd ${smoke_user} || true
    echo '--- smoke homed state ---'
    homectl inspect ${smoke_user} --no-pager 2>/dev/null || true
    echo '--- smoke home path ---'
    ls -ld /home/${smoke_user} /home/${smoke_user}/.local /home/${smoke_user}/.local/share 2>/dev/null || true
    echo '--- smoke mount ---'
    mount | grep -F '/home/${smoke_user}' || true
    echo '--- smoke write probe ---'
    runuser -u ${smoke_user} -- env \
      HOME=/home/${smoke_user} \
      XDG_RUNTIME_DIR=/run/user/${smoke_uid} \
      DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${smoke_uid}/bus \
      bash -lc '
        set -eu
        test \"\$HOME\" = /home/${smoke_user}
        install -d -m 700 \"\$HOME/.local/share\"
        probe=\"\$HOME/.local/share/.arch-bootc-smoke-write-test\"
        : >\"\$probe\"
        test -f \"\$probe\"
        rm -f \"\$probe\"
      '
  "
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
  if [ "${BOOTC_VM_DIRECT_KERNEL_BOOT:-0}" = "1" ]; then
    skip "bootc guest checks require the normal EFI/systemd-boot path"
  fi

  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_systemd_run 'bootc status >/dev/null'
  [ "$status" -eq 0 ]

  if [ "${BOOTC_VM_REQUIRE_ONLINE_UPGRADE_CHECK:-0}" = "1" ]; then
    run vm_systemd_run 'bootc upgrade --check >/dev/null'
    [ "$status" -eq 0 ]
  else
    skip "online upgrade checks require a reachable bootc update source from inside the guest"
  fi
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
  '
  [ "$status" -eq 0 ]
}

@test "hypr runtime dependencies are installed" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run vm_systemd_run 'command -v Hyprland >/dev/null && command -v uwsm >/dev/null && command -v hyprctl >/dev/null'
  [ "$status" -eq 0 ]
}

@test "systemd has no failed units after boot" {
  run wait_for_ssh
  [ "$status" -eq 0 ]

  run assert_no_failed_units
  if [ "$status" -ne 0 ] && [ -n "${output:-}" ]; then
    printf '%s\n' "$output" >&3
  fi
  [ "$status" -eq 0 ]
}

@test "graphical smoke home is mounted and writable" {
  if [ "${BOOTC_VM_GRAPHICAL_SESSION_SMOKE:-0}" != "1" ]; then
    skip "graphical session smoke is only enabled for graphical VM runs"
  fi

  run wait_for_ssh
  [ "$status" -eq 0 ]

  run wait_for_graphical_session
  [ "$status" -eq 0 ]

  run assert_graphical_home_ready
  if [ "$status" -ne 0 ] && [ -n "${output:-}" ]; then
    printf '%s\n' "$output" >&3
  fi
  [ "$status" -eq 0 ]
}

@test "uwsm can launch a graphical Hyprland session" {
  if [ "${BOOTC_VM_GRAPHICAL_SESSION_SMOKE:-0}" != "1" ]; then
    skip "graphical session smoke is only enabled for graphical VM runs"
  fi

  run wait_for_ssh
  [ "$status" -eq 0 ]

  run wait_for_graphical_session
  [ "$status" -eq 0 ]
}
