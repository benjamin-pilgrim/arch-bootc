#!/usr/bin/env bash

set -eu
vm_verbose="${BOOTC_VM_VERBOSE:-0}"
base_dir="${BUILD_BASE_DIR:-.}"
bootable="${BOOTABLE_IMAGE_PATH:-$base_dir/bootable.img}"
bootable_image_id_file="${BOOTABLE_IMAGE_ID_FILE:-$bootable.image-id}"
boot_timeout="${BOOTC_VM_BOOT_TIMEOUT_S:-300}"
image_name="${BUILD_IMAGE_NAME:-arch-bootc}"
image_tag="${BUILD_IMAGE_TAG:-local}"
qemu_bin="${QEMU_BIN:-qemu-system-x86_64}"
vm_sandbox="${BOOTC_VM_SANDBOX:-0}"
qemu_accel="${BOOTC_VM_QEMU_ACCEL:-}"
qemu_cpu="${BOOTC_VM_QEMU_CPU:-}"
qemu_display="${BOOTC_VM_QEMU_DISPLAY:-}"
qemu_gpu="${BOOTC_VM_QEMU_GPU:-}"
ssh_port="${BOOTC_VM_SSH_PORT:-2222}"
ssh_user="${BOOTC_VM_SSH_USER:-root}"
qemu_mem="${BOOTC_VM_QEMU_MEM:-4096}"
qemu_smp="${BOOTC_VM_QEMU_SMP:-4}"
follow_qemu_log="${BOOTC_VM_FOLLOW_LOG:-1}"
serial_kernel_log="${BOOTC_VM_SERIAL_KERNEL_LOG:-1}"
vm_log_level="${BOOTC_VM_LOG_LEVEL:-quiet}"
qemu_trace="${BOOTC_VM_QEMU_TRACE:-0}"
inject_loader_kargs="${BOOTC_VM_INJECT_LOADER_KARGS:-1}"
qemu_snapshot="${BOOTC_VM_QEMU_SNAPSHOT:-}"
qemu_overlay="${BOOTC_VM_QEMU_OVERLAY:-}"
direct_kernel_boot="${BOOTC_VM_DIRECT_KERNEL_BOOT:-}"
ssh_banner_timeout="${BOOTC_VM_SSH_BANNER_TIMEOUT_S:-$boot_timeout}"
wait_status_interval="${BOOTC_VM_WAIT_STATUS_INTERVAL_S:-10}"
use_systemd_ssh_generator="${BOOTC_VM_USE_SYSTEMD_SSH_GENERATOR:-1}"
systemd_ssh_listen="${BOOTC_VM_SYSTEMD_SSH_LISTEN:-0.0.0.0:22}"
use_ssh_listen_credential="${BOOTC_VM_USE_SSH_LISTEN_CREDENTIAL:-}"
graphical_session_smoke="${BOOTC_VM_GRAPHICAL_SESSION_SMOKE:-0}"
run_smoke_tests="${BOOTC_VM_RUN_TESTS:-1}"
configure_homed_firstboot="${BOOTC_VM_CONFIGURE_HOMED_FIRSTBOOT:-1}"
homed_firstboot_user="${BOOTC_VM_HOMED_FIRSTBOOT_USER:-smoke}"
homed_firstboot_real_name="${BOOTC_VM_HOMED_FIRSTBOOT_REAL_NAME:-Smoke User}"
homed_firstboot_uid="${BOOTC_VM_HOMED_FIRSTBOOT_UID:-60001}"
homed_firstboot_gid="${BOOTC_VM_HOMED_FIRSTBOOT_GID:-60001}"
homed_firstboot_groups="${BOOTC_VM_HOMED_FIRSTBOOT_GROUPS:-wheel}"
homed_firstboot_shell="${BOOTC_VM_HOMED_FIRSTBOOT_SHELL:-/bin/bash}"
homed_firstboot_storage="${BOOTC_VM_HOMED_FIRSTBOOT_STORAGE:-directory}"
homed_firstboot_password="${BOOTC_VM_HOMED_FIRSTBOOT_PASSWORD:-cinder742orbit9moss}"
homed_firstboot_image_path="/home/$homed_firstboot_user.homedir"
use_run0_podman="${BOOTC_PODMAN_USE_RUN0:-1}"
skip_image_checks="${BOOTC_VM_SKIP_IMAGE_CHECKS:-0}"
skip_bootable_regen="${BOOTC_VM_SKIP_BOOTABLE_REGEN:-0}"
sandbox_require_artifact_stamp="${BOOTC_VM_SANDBOX_REQUIRE_ARTIFACT_STAMP:-1}"
qemu_serial_mode="stdio"
log() {
  printf '%s\n' "$*"
}
debug() {
  if [ "$vm_verbose" = "1" ]; then
    printf '%s\n' "$*"
  fi
}
podman_image_id() {
  podman_cmd image inspect --format json "$1" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); obj=data[0] if isinstance(data,list) else data; print(obj.get("Id",""))'
}
podman_cmd() {
  if [ "$use_run0_podman" = "1" ] && [ "$(id -u)" -ne 0 ]; then
    if command -v run0 >/dev/null 2>&1; then
      run0 podman "$@"
      return
    fi
    if command -v sudo >/dev/null 2>&1; then
      sudo podman "$@"
      return
    fi
  fi
  podman "$@"
}
if [ "$vm_sandbox" = "1" ]; then
  use_run0_podman=0
  skip_image_checks=1
  skip_bootable_regen=1
  if [ -z "$direct_kernel_boot" ]; then
    direct_kernel_boot="1"
  fi
  if [ -z "$use_ssh_listen_credential" ]; then
    use_ssh_listen_credential="1"
  fi
  if [ -z "$qemu_accel" ]; then
    qemu_accel="kvm"
  fi
  if [ -z "$qemu_snapshot" ]; then
    qemu_snapshot="0"
  fi
  if [ -z "$qemu_overlay" ]; then
    qemu_overlay="1"
  fi
fi
if [ -z "$use_ssh_listen_credential" ]; then
  use_ssh_listen_credential="1"
fi
if [ -z "$qemu_accel" ]; then
  qemu_accel="kvm:tcg"
fi
if [ -z "$qemu_cpu" ]; then
  case "$qemu_accel" in
    kvm|kvm:*)
      qemu_cpu="host,-svm"
      ;;
    *)
      qemu_cpu="max"
      ;;
  esac
fi
if [ -z "$qemu_display" ]; then
  if [ "$graphical_session_smoke" = "1" ]; then
    qemu_display="gtk,gl=off"
  else
    qemu_display="none"
  fi
fi
if [ -z "$qemu_gpu" ] && [ "$graphical_session_smoke" = "1" ]; then
  qemu_gpu="virtio-vga"
fi
if [ "$graphical_session_smoke" = "1" ]; then
  qemu_serial_mode="socket"
fi
if [ -z "$qemu_snapshot" ]; then
  qemu_snapshot="0"
fi
if [ -z "$qemu_overlay" ]; then
  qemu_overlay="1"
fi
if [ -z "$direct_kernel_boot" ]; then
  direct_kernel_boot="0"
fi

if [ "$vm_sandbox" = "1" ]; then
  if [ "$qemu_accel" != "kvm" ]; then
    echo "Sandbox VM boots require KVM; refusing qemu accel '$qemu_accel'."
    echo "This image currently does not boot reliably under TCG in sandbox mode."
    echo "Use BOOTC_VM_QEMU_ACCEL=kvm and make /dev/kvm accessible, or run the non-sandbox VM flow."
    exit 1
  fi
  if [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then
    echo "Sandbox VM boots require read/write access to /dev/kvm."
    echo "Current user cannot access /dev/kvm, so qemu would fall back to an unusable TCG path."
    echo "Grant KVM access to the sandbox environment or run the non-sandbox VM flow."
    exit 1
  fi
fi
case "$qemu_display" in
  gtk*|sdl*)
    if [ "$graphical_session_smoke" = "1" ] && [ "$(id -u)" -eq 0 ] && [ "${BOOTC_VM_ALLOW_ROOT_GRAPHICS:-0}" != "1" ]; then
      echo "Graphical VM smoke should be run without sudo."
      echo "Root cannot usually access the current desktop display/socket authorization cleanly."
      echo "Run 'mise run test-smoke-vm-graphical' as your user, or set BOOTC_VM_ALLOW_ROOT_GRAPHICS=1 if you are explicitly preserving display auth."
      exit 1
    fi
    if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
      echo "Graphical QEMU display '$qemu_display' requires DISPLAY or WAYLAND_DISPLAY in the host environment."
      echo "Set BOOTC_VM_QEMU_DISPLAY=none for non-graphical runs, or launch from a graphical host session."
      exit 1
    fi
    ;;
esac
if [ "$vm_sandbox" = "1" ] && [ "${BOOTC_VM_INJECT_LOADER_KARGS+x}" != x ]; then
  inject_loader_kargs=0
fi
case "$vm_log_level" in
  quiet)
    default_kernel_cmdline='quiet console=ttyS0,115200 console=tty0 loglevel=3 rd.systemd.show_status=0 systemd.show_status=0 rd.udev.log_level=3 udev.log_level=3 systemd.log_level=notice'
    ;;
  normal)
    default_kernel_cmdline='console=ttyS0,115200 console=tty0 loglevel=4 rd.systemd.show_status=auto systemd.show_status=auto rd.udev.log_level=4 udev.log_level=4 systemd.log_level=info'
    ;;
  debug)
    default_kernel_cmdline='console=ttyS0,115200 console=tty0 earlycon=uart,io,0x3f8,115200 ignore_loglevel loglevel=8 printk.time=1 rd.systemd.show_status=1 systemd.log_level=debug systemd.log_target=console rd.debug'
    ;;
  *)
    echo "Invalid BOOTC_VM_LOG_LEVEL='$vm_log_level' (expected: quiet|normal|debug)"
    exit 1
    ;;
esac
vm_kernel_cmdline="${BOOTC_VM_KERNEL_CMDLINE:-$default_kernel_cmdline}"
effective_kernel_cmdline="$vm_kernel_cmdline"
if [ "$serial_kernel_log" != "1" ]; then
  effective_kernel_cmdline="$(printf '%s\n' "$effective_kernel_cmdline" | sed -E 's/(^| )console=ttyS0[^ ]*//g; s/(^| )earlycon=[^ ]+//g; s/[[:space:]]+/ /g; s/^ //; s/ $//')"
fi
if [ "$use_systemd_ssh_generator" = "1" ]; then
  effective_kernel_cmdline="$effective_kernel_cmdline systemd.ssh_auto=1"
  if [ "$use_ssh_listen_credential" != "1" ]; then
    effective_kernel_cmdline="$effective_kernel_cmdline systemd.ssh_listen=$systemd_ssh_listen"
  fi
fi
strip_managed_kargs() {
  printf '%s\n' "$1" | sed -E '
    s/(^| )quiet($| )/ /g;
    s/(^| )console=ttyS0[^ ]*//g;
    s/(^| )console=tty0($| )/ /g;
    s/(^| )earlycon=[^ ]+//g;
    s/(^| )ignore_loglevel($| )/ /g;
    s/(^| )loglevel=[^ ]+//g;
    s/(^| )printk\.time=[^ ]+//g;
    s/(^| )rd\.systemd\.show_status=[^ ]+//g;
    s/(^| )systemd\.show_status=[^ ]+//g;
    s/(^| )systemd\.log_level=[^ ]+//g;
    s/(^| )systemd\.log_target=[^ ]+//g;
    s/(^| )rd\.debug($| )/ /g;
    s/(^| )rd\.udev\.log_level=[^ ]+//g;
    s/(^| )udev\.log_level=[^ ]+//g;
    s/(^| )systemd\.ssh_auto=[^ ]+//g;
    s/(^| )systemd\.ssh_listen=[^ ]+//g;
    s/[[:space:]]+/ /g;
    s/^ //;
    s/ $//
  '
}
print_sanitized_qemu_log_tail() {
  if [ "${graphical_session_smoke:-0}" = "1" ]; then
    echo "qemu vm log: $log_file"
    return 0
  fi
  tail -n 200 "$log_file" 2>/dev/null \
    | perl -ne 'BEGIN { $| = 1 } s/\e\[[0-9;?]*[ -\/]*[@-~]//g; s/\eP.*?\e\\\\//g; s/\e\].*?(?:\a|\e\\\\)//g; s/[\x00-\x08\x0b-\x1f\x7f]//g; s/\r//g; print if /\S/' \
    || true
}
if [ "${image_name#*/}" = "$image_name" ]; then
  image_ref="localhost/$image_name:$image_tag"
else
  image_ref="$image_name:$image_tag"
fi

if ! command -v "$qemu_bin" >/dev/null 2>&1; then
  echo "$qemu_bin is required for test-smoke-vm-local"
  echo "Install qemu-system-x86 (Ubuntu) or qemu-full/qemu-desktop (Arch) and retry."
  exit 1
fi

image_id=""
if [ "$skip_image_checks" != "1" ]; then
  if ! podman_cmd image exists "$image_ref"; then
    echo "Image $image_ref not found; building it now..."
    BUILD_IMAGE_NAME="$image_name" BUILD_IMAGE_TAG="$image_tag" mise run build-log
  fi

  image_id="$(podman_image_id "$image_ref")"

  if ! podman_cmd run --rm --entrypoint sh "$image_ref" -c '
    command -v sshd >/dev/null 2>&1 &&
    test -x /usr/lib/systemd/system-generators/systemd-ssh-generator &&
    test -f /etc/systemd/network/20-wired.network &&
    systemctl --root=/ is-enabled systemd-networkd.service >/dev/null &&
    systemctl --root=/ is-enabled systemd-resolved.service >/dev/null
  '; then
    echo "Image $image_ref is missing required VM networking or SSH prerequisites."
    echo "Expected: sshd, systemd-ssh-generator, /etc/systemd/network/20-wired.network,"
    echo "and enabled systemd-networkd.service + systemd-resolved.service."
    exit 1
  fi
fi

if [ "$skip_bootable_regen" != "1" ]; then
  regen_bootable=0
  regen_reason=""
  if [ ! -f "$bootable" ]; then
    regen_bootable=1
    regen_reason="Bootable image not found at $bootable"
  elif [ ! -f "$bootable_image_id_file" ]; then
    regen_bootable=1
    regen_reason="Bootable image stamp not found at $bootable_image_id_file"
  elif [ "$(cat "$bootable_image_id_file")" != "$image_id" ]; then
    regen_bootable=1
    regen_reason="Built image changed since $bootable was generated"
  fi

  if [ "$regen_bootable" = "1" ]; then
    echo "$regen_reason; generating bootable image now..."
    BUILD_IMAGE_NAME="$image_name" BUILD_IMAGE_TAG="$image_tag" mise run generate-bootable-image
    printf '%s\n' "$image_id" >"$bootable_image_id_file"
  fi
elif [ ! -f "$bootable" ]; then
  echo "Sandbox mode requires an existing bootable image at $bootable."
  echo "Generate it outside the sandbox first with: sudo BUILD_IMAGE_TAG=$image_tag mise run generate-vm-artifact"
  exit 1
fi

bootable="$(realpath "$bootable")"
if [ -f "$bootable_image_id_file" ]; then
  bootable_image_id_file="$(realpath "$bootable_image_id_file")"
fi

if [ "$vm_sandbox" = "1" ] && [ "$sandbox_require_artifact_stamp" = "1" ]; then
  if [ ! -s "$bootable_image_id_file" ]; then
    echo "Sandbox mode requires a non-empty artifact stamp at $bootable_image_id_file."
    echo "Generate it outside the sandbox first with: sudo BUILD_IMAGE_TAG=$image_tag mise run generate-vm-artifact"
    exit 1
  fi
  debug "Using sandbox VM artifact:"
  debug "  disk: $bootable"
  debug "  stamp: $bootable_image_id_file"
  debug "  image id: $(cat "$bootable_image_id_file")"
fi

if [ "$inject_loader_kargs" = "1" ]; then
  if [ "$vm_sandbox" = "1" ]; then
    echo "Sandbox mode cannot patch loader kernel args."
    echo "Set BOOTC_VM_INJECT_LOADER_KARGS=0 and rely on fw_cfg kernel cmdline injection."
    exit 1
  fi
  run_as_root=""
  if [ "$(id -u)" -ne 0 ]; then
    run_as_root="sudo"
  fi

  loopdev="$($run_as_root losetup -fP --show "$bootable")"
  esp_mount="$(mktemp -d "${TMPDIR:-/tmp}/esp-mount.XXXXXX")"
  $run_as_root mount "${loopdev}p2" "$esp_mount"
  for entry in "$esp_mount"/loader/entries/*.conf; do
    [ -f "$entry" ] || continue
    current_opts="$($run_as_root sed -n 's/^options //p' "$entry")"
    base_opts="$(strip_managed_kargs "$current_opts")"
    new_opts="$base_opts"
    if [ -n "$effective_kernel_cmdline" ]; then
      if [ -n "$new_opts" ]; then
        new_opts="$new_opts $effective_kernel_cmdline"
      else
        new_opts="$effective_kernel_cmdline"
      fi
    fi
    escaped_new_opts="$(printf '%s\n' "$new_opts" | sed -e 's/[&|]/\\&/g')"
    if $run_as_root grep -q '^options ' "$entry"; then
      $run_as_root sed -i "s|^options .*$|options $escaped_new_opts|" "$entry"
    else
      printf 'options %s\n' "$new_opts" | $run_as_root tee -a "$entry" >/dev/null
    fi
  done
  $run_as_root umount "$esp_mount"
  rmdir "$esp_mount"
  $run_as_root losetup -d "$loopdev"
fi

if ss -ltn "( sport = :$ssh_port )" | grep -q LISTEN; then
  echo "SSH forward port $ssh_port is already in use; set BOOTC_VM_SSH_PORT to another port."
  exit 1
fi

ovmf_code=""
ovmf_vars=""
for pair in \
  "/usr/share/OVMF/OVMF_CODE.fd:/usr/share/OVMF/OVMF_VARS.fd" \
  "/usr/share/OVMF/OVMF_CODE_4M.fd:/usr/share/OVMF/OVMF_VARS_4M.fd" \
  "/usr/share/edk2/ovmf/OVMF_CODE.fd:/usr/share/edk2/ovmf/OVMF_VARS.fd" \
  "/usr/share/edk2-ovmf/x64/OVMF_CODE.fd:/usr/share/edk2-ovmf/x64/OVMF_VARS.fd"
do
  code_path="${pair%%:*}"
  vars_path="${pair##*:}"
  if [ -f "$code_path" ] && [ -f "$vars_path" ]; then
    ovmf_code="$code_path"
    ovmf_vars="$vars_path"
    break
  fi
done

log_file="$(mktemp "${TMPDIR:-/tmp}/qemu-vm-smoke.XXXXXX.log")"
trace_file="$(mktemp "${TMPDIR:-/tmp}/qemu-vm-trace.XXXXXX.log")"
known_hosts_file="/dev/null"
bootable_runtime="$bootable"
bootable_runtime_format="raw"
bootable_overlay=""
ssh_key_dir=""
ssh_private_key=""
esp_image=""
esp_extract_dir=""
kernel_path=""
initrd_path=""
loader_entry=""
kernel_boot_append=""
firstboot_credential_dir=""
firstboot_timezone_file=""
firstboot_locale_file=""
firstboot_keymap_file=""
homed_firstboot_identity_file=""
homed_firstboot_password_file=""
ssh_listen_file=""
qemu_serial_socket=""
cleanup_ran=0
cleanup() {
  if [ "${cleanup_ran:-0}" = "1" ]; then
    return
  fi
  cleanup_ran=1
  if [ -n "${log_tail_pid:-}" ] && kill -0 "$log_tail_pid" 2>/dev/null; then
    kill "$log_tail_pid" >/dev/null 2>&1 || true
  fi
  pkill -P "$$" -f '^tail -n \+[01] -F ' >/dev/null 2>&1 || true
  if [ -n "${vm_pid:-}" ] && kill -0 "$vm_pid" 2>/dev/null; then
    kill "$vm_pid" >/dev/null 2>&1 || true
    wait "$vm_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "${ovmf_vars_runtime:-}" ] && [ -f "${ovmf_vars_runtime:-}" ]; then
    rm -f "$ovmf_vars_runtime" || true
  fi
  if [ -n "${kernel_cmdline_file:-}" ] && [ -f "${kernel_cmdline_file:-}" ]; then
    rm -f "$kernel_cmdline_file" || true
  fi
  if [ -n "${known_hosts_file:-}" ] && [ -f "${known_hosts_file:-}" ]; then
    rm -f "$known_hosts_file" || true
  fi
  if [ -n "${bootable_overlay:-}" ] && [ -f "${bootable_overlay:-}" ]; then
    rm -f "$bootable_overlay" || true
  fi
  if [ -n "${qemu_serial_socket:-}" ] && [ -S "${qemu_serial_socket:-}" ]; then
    rm -f "$qemu_serial_socket" || true
  fi
  if [ -n "${esp_image:-}" ] && [ -f "${esp_image:-}" ]; then
    rm -f "$esp_image" || true
  fi
  if [ -n "${esp_extract_dir:-}" ] && [ -d "${esp_extract_dir:-}" ]; then
    rm -rf "$esp_extract_dir" || true
  fi
  if [ -n "${firstboot_credential_dir:-}" ] && [ -d "${firstboot_credential_dir:-}" ]; then
    rm -rf "$firstboot_credential_dir" || true
  fi
  if [ -n "${ssh_key_dir:-}" ] && [ -d "${ssh_key_dir:-}" ]; then
    rm -rf "$ssh_key_dir" || true
  fi
  pkill -P "$$" -f '^sed -u s/\^/\[qemu\] /' >/dev/null 2>&1 || true
  pkill -P "$$" -f "^perl -ne BEGIN \\{ \\$\\| = 1 \\}" >/dev/null 2>&1 || true
  if [ "${boot_vm_success:-0}" != "1" ]; then
    echo "qemu vm log: $log_file"
    if [ "${qemu_trace:-0}" = "1" ]; then
      echo "qemu trace log: $trace_file"
    else
      rm -f "$trace_file" || true
    fi
  else
    rm -f "$trace_file" || true
  fi
  if command -v stty >/dev/null 2>&1; then
    stty sane >/dev/null 2>&1 || true
  fi
  if [ -t 1 ] && [ -c /dev/tty ] && [ -w /dev/tty ]; then
    printf '\033[0m\033[?25h' >/dev/tty 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [ "$qemu_overlay" = "1" ]; then
  if ! command -v qemu-img >/dev/null 2>&1; then
    echo "qemu-img is required for BOOTC_VM_QEMU_OVERLAY=1"
    exit 1
  fi
  bootable_overlay="$(mktemp "${TMPDIR:-/tmp}/qemu-vm-overlay.XXXXXX.qcow2")"
  rm -f "$bootable_overlay"
  qemu-img create -f qcow2 -F raw -b "$bootable" "$bootable_overlay" >/dev/null
  bootable_runtime="$bootable_overlay"
  bootable_runtime_format="qcow2"
fi

if [ "$direct_kernel_boot" = "1" ]; then
  if ! command -v sfdisk >/dev/null 2>&1; then
    echo "sfdisk is required for BOOTC_VM_DIRECT_KERNEL_BOOT=1"
    exit 1
  fi
  if ! command -v 7z >/dev/null 2>&1; then
    echo "7z is required for BOOTC_VM_DIRECT_KERNEL_BOOT=1"
    exit 1
  fi

  esp_image="$(mktemp "${TMPDIR:-/tmp}/qemu-vm-esp.XXXXXX.img")"
  esp_extract_dir="$(mktemp -d "${TMPDIR:-/tmp}/qemu-vm-esp.XXXXXX")"
  python3 - <<'PY' "$bootable" "$esp_image"
import json
import subprocess
import sys
bootable = sys.argv[1]
esp_image = sys.argv[2]
data = json.loads(subprocess.check_output(["sfdisk", "-J", bootable], text=True))
parts = data["partitiontable"]["partitions"]
if len(parts) < 2:
    raise SystemExit(f"expected at least 2 partitions in {bootable}")
esp = parts[1]
start = int(esp["start"])
size = int(esp["size"])
subprocess.check_call([
    "dd",
    f"if={bootable}",
    f"of={esp_image}",
    "bs=512",
    f"skip={start}",
    f"count={size}",
    "status=none",
])
PY
  7z x -y "$esp_image" 'loader/*' 'EFI/Linux/*' -o"$esp_extract_dir" >/dev/null
  loader_entry="$(find "$esp_extract_dir/loader/entries" -type f | head -n1)"
  if [ -z "$loader_entry" ] || [ ! -f "$loader_entry" ]; then
    echo "Failed to extract a loader entry from $bootable"
    exit 1
  fi
  kernel_rel="$(sed -n 's/^linux //p' "$loader_entry")"
  initrd_rel="$(sed -n 's/^initrd //p' "$loader_entry")"
  base_opts="$(sed -n 's/^options //p' "$loader_entry")"
  kernel_path="$esp_extract_dir$kernel_rel"
  initrd_path="$esp_extract_dir$initrd_rel"
  if [ ! -f "$kernel_path" ] || [ ! -f "$initrd_path" ]; then
    echo "Failed to extract kernel/initrd from $bootable"
    exit 1
  fi
  base_opts="$(strip_managed_kargs "$base_opts")"
  kernel_boot_append="$base_opts"
  if [ -n "$effective_kernel_cmdline" ]; then
    if [ -n "$kernel_boot_append" ]; then
      kernel_boot_append="$kernel_boot_append $effective_kernel_cmdline"
    else
      kernel_boot_append="$effective_kernel_cmdline"
    fi
  fi
fi

set -- "$qemu_bin" \
  -machine "q35,accel=$qemu_accel" \
  -cpu "$qemu_cpu" \
  -m "$qemu_mem" \
  -smp "$qemu_smp" \
  -display "$qemu_display" \
  -object rng-random,id=rng0,filename=/dev/urandom \
  -device virtio-rng-pci,rng=rng0 \
  -netdev "user,id=net0,hostfwd=tcp::${ssh_port}-:22" \
  -device virtio-net-pci,netdev=net0,bootindex=2 \
  -drive "if=none,id=bootdisk,file=$bootable_runtime,format=$bootable_runtime_format" \
  -device ich9-ahci,id=ahci \
  -device ide-hd,drive=bootdisk,bus=ahci.0,bootindex=1 \
  -monitor none

if [ "$qemu_serial_mode" = "file" ]; then
  set -- "$@" -serial "file:$log_file"
elif [ "$qemu_serial_mode" = "socket" ]; then
  qemu_serial_socket="$(mktemp -u "${TMPDIR:-/tmp}/qemu-serial.XXXXXX.sock")"
  set -- "$@" \
    -chardev "socket,id=serial0,path=$qemu_serial_socket,server=on,wait=off,logfile=$log_file,logappend=on" \
    -serial chardev:serial0
else
  set -- "$@" -serial stdio
fi

if [ "$graphical_session_smoke" = "1" ]; then
  set -- "$@" \
    -device "$qemu_gpu" \
    -device usb-ehci,id=ehci \
    -device usb-tablet,bus=ehci.0
fi

if [ "$direct_kernel_boot" != "1" ]; then
  set -- "$@" -boot order=c
fi

if [ "$qemu_snapshot" = "1" ]; then
  set -- "$@" -snapshot
fi

if [ "$use_systemd_ssh_generator" = "1" ]; then
  if ! command -v ssh-keygen >/dev/null 2>&1; then
    echo "ssh-keygen is required for systemd-ssh-generator VM access (install openssh-client)."
    exit 1
  fi
  ssh_key_dir="$(mktemp -d "${TMPDIR:-/tmp}/qemu-vm-key.XXXXXX")"
  ssh_private_key="$ssh_key_dir/id_ed25519"
  ssh-keygen -q -t ed25519 -N '' -C arch-bootc-vm-smoke -f "$ssh_private_key"
  set -- "$@" \
    -fw_cfg "name=opt/io.systemd.credentials/ssh.authorized_keys.root,file=$ssh_private_key.pub"
fi

if [ "$direct_kernel_boot" = "1" ] || [ "$configure_homed_firstboot" = "1" ]; then
  firstboot_credential_dir="$(mktemp -d "${TMPDIR:-/tmp}/qemu-vm-firstboot.XXXXXX")"
  firstboot_timezone_file="$firstboot_credential_dir/firstboot.timezone"
  firstboot_locale_file="$firstboot_credential_dir/firstboot.locale"
  firstboot_keymap_file="$firstboot_credential_dir/firstboot.keymap"
  printf '%s\n' "${BOOTC_VM_FIRSTBOOT_TIMEZONE:-UTC}" >"$firstboot_timezone_file"
  printf '%s\n' "${BOOTC_VM_FIRSTBOOT_LOCALE:-C.UTF-8}" >"$firstboot_locale_file"
  printf '%s\n' "${BOOTC_VM_FIRSTBOOT_KEYMAP:-us}" >"$firstboot_keymap_file"
  set -- "$@" \
    -fw_cfg "name=opt/io.systemd.credentials/firstboot.timezone,file=$firstboot_timezone_file" \
    -fw_cfg "name=opt/io.systemd.credentials/firstboot.locale,file=$firstboot_locale_file" \
    -fw_cfg "name=opt/io.systemd.credentials/firstboot.keymap,file=$firstboot_keymap_file"
fi

if [ "$use_systemd_ssh_generator" = "1" ] && [ "$use_ssh_listen_credential" = "1" ]; then
  if [ -z "$firstboot_credential_dir" ]; then
    firstboot_credential_dir="$(mktemp -d "${TMPDIR:-/tmp}/qemu-vm-firstboot.XXXXXX")"
  fi
  ssh_listen_file="$firstboot_credential_dir/ssh.listen"
  printf '%s\n' "$systemd_ssh_listen" >"$ssh_listen_file"
  set -- "$@" \
    -fw_cfg "name=opt/io.systemd.credentials/ssh.listen,file=$ssh_listen_file"
fi

if [ "$configure_homed_firstboot" = "1" ]; then
  if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required for BOOTC_VM_CONFIGURE_HOMED_FIRSTBOOT=1"
    exit 1
  fi
  if [ -z "$firstboot_credential_dir" ]; then
    firstboot_credential_dir="$(mktemp -d "${TMPDIR:-/tmp}/qemu-vm-firstboot.XXXXXX")"
  fi
  homed_firstboot_password_file="$firstboot_credential_dir/home.create.password"
  homed_firstboot_identity_file="$firstboot_credential_dir/home.create.$homed_firstboot_user"
  homed_firstboot_password_hash="$(openssl passwd -6 -salt codexsmoke "$homed_firstboot_password")"
  cat >"$homed_firstboot_identity_file" <<JSON
{
  "userName": "$homed_firstboot_user",
  "realName": "$homed_firstboot_real_name",
  "homeDirectory": "/home/$homed_firstboot_user",
  "imagePath": "$homed_firstboot_image_path",
  "shell": "$homed_firstboot_shell",
  "uid": $homed_firstboot_uid,
  "gid": $homed_firstboot_gid,
  "memberOf": ["$(printf '%s' "$homed_firstboot_groups" | sed 's/,/","/g')"],
  "storage": "$homed_firstboot_storage",
  "enforcePasswordPolicy": false,
  "privileged": {
    "hashedPassword": ["$homed_firstboot_password_hash"]
  },
  "secret": {
    "password": ["$homed_firstboot_password"]
  }
}
JSON
  set -- "$@" \
    -fw_cfg "name=opt/io.systemd.credentials/home.create.$homed_firstboot_user,file=$homed_firstboot_identity_file"
fi

if [ "$direct_kernel_boot" = "1" ]; then
  set -- "$@" \
    -kernel "$kernel_path" \
    -initrd "$initrd_path" \
    -append "$kernel_boot_append"
fi

if [ "$direct_kernel_boot" != "1" ] && [ -n "$ovmf_code" ] && [ -n "$ovmf_vars" ]; then
  ovmf_vars_runtime="$(mktemp "${TMPDIR:-/tmp}/OVMF_VARS.XXXXXX.fd")"
  cp "$ovmf_vars" "$ovmf_vars_runtime"
  set -- "$@" \
    -drive "if=pflash,format=raw,readonly=on,file=$ovmf_code" \
    -drive "if=pflash,format=raw,file=$ovmf_vars_runtime"
fi

if [ "$direct_kernel_boot" != "1" ] && [ "$serial_kernel_log" = "1" ] && [ "$inject_loader_kargs" != "1" ]; then
  kernel_cmdline_file="$(mktemp "${TMPDIR:-/tmp}/qemu-kcmdline.XXXXXX")"
  printf '%s\n' "$effective_kernel_cmdline" >"$kernel_cmdline_file"
  set -- "$@" \
    -fw_cfg "name=opt/org.systemd.stub.kernel-cmdline,file=$kernel_cmdline_file"
fi

if [ "$qemu_trace" = "1" ]; then
  set -- "$@" \
    -d guest_errors,cpu_reset \
    -D "$trace_file" \
    -no-reboot
fi

if [ "$qemu_serial_mode" = "file" ] || [ "$qemu_serial_mode" = "socket" ]; then
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" </dev/null >>"$log_file" 2>&1 &
  else
    "$@" </dev/null >>"$log_file" 2>&1 &
  fi
else
  "$@" >"$log_file" 2>&1 &
fi
vm_pid="$!"

if [ "$follow_qemu_log" = "1" ]; then
  tail -n +1 -F "$log_file" \
    | perl -ne 'BEGIN { $| = 1 } s/\e\[[0-9;?]*[ -\/]*[@-~]//g; s/\eP.*?\e\\\\//g; s/\e\].*?(?:\a|\e\\\\)//g; s/\r//g; print if /\S/' \
    | sed -u 's/^/[qemu] /' &
  log_tail_pid="$!"
fi

if ! command -v ssh-keyscan >/dev/null 2>&1; then
  echo "ssh-keyscan is required for vm SSH readiness checks (install openssh-client)."
  kill "$vm_pid" >/dev/null 2>&1 || true
  wait "$vm_pid" >/dev/null 2>&1 || true
  exit 1
fi

log "Waiting for SSH banner on 127.0.0.1:$ssh_port (timeout: ${ssh_banner_timeout}s)..."
ssh_wait_start="$(date +%s)"
ssh_wait_last_status="$ssh_wait_start"
while true; do
  if ssh-keyscan -T 2 -p "$ssh_port" 127.0.0.1 >/dev/null 2>&1; then
    log "SSH banner is available on 127.0.0.1:$ssh_port"
    break
  fi

  if ! kill -0 "$vm_pid" 2>/dev/null; then
    echo "qemu exited before SSH banner became available"
    print_sanitized_qemu_log_tail
    exit 1
  fi

  ssh_wait_now="$(date +%s)"
  if [ $((ssh_wait_now - ssh_wait_start)) -ge "$ssh_banner_timeout" ]; then
    echo "Timed out waiting for SSH banner on 127.0.0.1:$ssh_port"
    print_sanitized_qemu_log_tail
    kill "$vm_pid" >/dev/null 2>&1 || true
    wait "$vm_pid" >/dev/null 2>&1 || true
    exit 1
  fi
  if [ "$wait_status_interval" -gt 0 ] && [ $((ssh_wait_now - ssh_wait_last_status)) -ge "$wait_status_interval" ]; then
    debug "Still waiting for SSH banner on 127.0.0.1:$ssh_port..."
    ssh_wait_last_status="$ssh_wait_now"
  fi

  sleep 2
done

ssh_extra_opts="${BOOTC_VM_SSH_EXTRA_OPTS:-}"
if [ -n "$ssh_private_key" ]; then
  ssh_extra_opts="$ssh_extra_opts -i $ssh_private_key -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
fi

log "Waiting for SSH authentication to succeed..."
ssh_auth_start="$(date +%s)"
ssh_auth_last_status="$ssh_auth_start"
ssh_auth_reason=""
ssh_auth_reason_file="$(mktemp "${TMPDIR:-/tmp}/qemu-vm-ssh-auth.XXXXXX")"
while true; do
  if timeout 5 ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o NumberOfPasswordPrompts=0 \
    -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no \
    -o GSSAPIAuthentication=no \
    -o LogLevel=ERROR \
    ${ssh_extra_opts} \
    -p "$ssh_port" "$ssh_user@127.0.0.1" true >/dev/null 2>"$ssh_auth_reason_file"; then
    log "SSH authentication is available on 127.0.0.1:$ssh_port"
    break
  fi

  ssh_auth_reason="$(tr '\n' ' ' <"$ssh_auth_reason_file" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  case "$ssh_auth_reason" in
    *"System is booting up."*|*"System is booting up"*|*"Please wait until boot process completes"*)
      ssh_auth_reason="guest boot is not complete yet (pam_nologin)"
      ;;
    *"Permission denied (publickey"*)
      ssh_auth_reason="SSH public key was rejected"
      ;;
    *"Connection refused"*)
      ssh_auth_reason="SSH daemon is not accepting authenticated sessions yet"
      ;;
    *"Host key verification failed"*)
      ssh_auth_reason="SSH host key verification failed"
      ;;
    *"Connection timed out"*|*"Operation timed out"*)
      ssh_auth_reason="SSH connection timed out"
      ;;
    "")
      ssh_auth_reason="no SSH error text captured"
      ;;
  esac

  if ! kill -0 "$vm_pid" 2>/dev/null; then
    echo "qemu exited before SSH authentication became available"
    print_sanitized_qemu_log_tail
    exit 1
  fi

  ssh_auth_now="$(date +%s)"
  if [ $((ssh_auth_now - ssh_auth_start)) -ge "$ssh_banner_timeout" ]; then
    echo "Timed out waiting for SSH authentication on 127.0.0.1:$ssh_port"
    echo "Last SSH authentication blocker: $ssh_auth_reason"
    if [ "$ssh_auth_reason" = "guest boot is not complete yet (pam_nologin)" ]; then
      print_boot_blocker_log
    fi
    print_sanitized_qemu_log_tail
    kill "$vm_pid" >/dev/null 2>&1 || true
    wait "$vm_pid" >/dev/null 2>&1 || true
    exit 1
  fi
  if [ "$wait_status_interval" -gt 0 ] && [ $((ssh_auth_now - ssh_auth_last_status)) -ge "$wait_status_interval" ]; then
    debug "Still waiting for SSH authentication on 127.0.0.1:$ssh_port... ($ssh_auth_reason)"
    ssh_auth_last_status="$ssh_auth_now"
  fi

  sleep 2
done

rm -f "$ssh_auth_reason_file"

if [ "$graphical_session_smoke" = "1" ]; then
  log "Bootstrapping graphical session for homed user '$homed_firstboot_user'..."
  graphical_bootstrap_log="$(mktemp "${TMPDIR:-/tmp}/qemu-vm-graphical-bootstrap.XXXXXX.log")"
  if [ "$vm_verbose" = "1" ]; then
    echo "Graphical bootstrap: initial homed state..."
    timeout 10 ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o NumberOfPasswordPrompts=0 \
    -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no \
    -o GSSAPIAuthentication=no \
    -o LogLevel=ERROR \
    ${ssh_extra_opts} \
    -p "$ssh_port" "$ssh_user@127.0.0.1" \
    "homectl inspect $homed_firstboot_user --no-pager 2>/dev/null || true" || true
    echo "Graphical bootstrap: homed account diagnostics..."
    timeout 15 ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o NumberOfPasswordPrompts=0 \
    -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no \
    -o GSSAPIAuthentication=no \
    -o LogLevel=ERROR \
    ${ssh_extra_opts} \
    -p "$ssh_port" "$ssh_user@127.0.0.1" "
      set -eu
      echo '--- getent passwd ---'
      getent passwd $homed_firstboot_user || true
      echo '--- loginctl user-status ---'
      loginctl user-status $homed_firstboot_user 2>/dev/null || true
      echo '--- home image path ---'
      ls -ld /home/$homed_firstboot_user.homedir 2>/dev/null || true
      echo '--- home blob dir ---'
      ls -ld /var/cache/systemd/home/$homed_firstboot_user 2>/dev/null || true
      echo '--- homed service status ---'
      systemctl --no-pager --plain --full status systemd-homed.service 2>/dev/null || true
      echo '--- homed journal ---'
      journalctl -b -u systemd-homed.service --no-pager -n 80 2>/dev/null || true
      echo '--- tty/login journal ---'
      journalctl -b --no-pager -n 200 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|homed|home1' || true
      echo '--- seat status ---'
      loginctl seat-status seat0 2>/dev/null || true
    " || true
  fi
  if ! timeout 10 ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o NumberOfPasswordPrompts=0 \
    -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no \
    -o GSSAPIAuthentication=no \
    -o LogLevel=ERROR \
    ${ssh_extra_opts} \
    -p "$ssh_port" "$ssh_user@127.0.0.1" \
    "getent passwd $homed_firstboot_user >/dev/null"; then
    echo "Expected homed user '$homed_firstboot_user' to exist after boot, but it was not present."
    echo "The graphical smoke path will not synthesize the user at runtime."
    echo "This indicates the firstboot homed provisioning path did not materialize the account."
    print_sanitized_qemu_log_tail
    exit 1
  fi
run_graphical_bootstrap_step() {
  step_name="$1"
  step_cmd="$2"
  debug "Graphical bootstrap: $step_name..."
  bootstrap_status=0
  timeout 20 ssh \
      -o BatchMode=yes \
      -o ConnectTimeout=5 \
      -o NumberOfPasswordPrompts=0 \
      -o PasswordAuthentication=no \
      -o KbdInteractiveAuthentication=no \
      -o GSSAPIAuthentication=no \
      -o LogLevel=ERROR \
      ${ssh_extra_opts} \
      -p "$ssh_port" "$ssh_user@127.0.0.1" \
      "$step_cmd" >"$graphical_bootstrap_log" 2>&1 || bootstrap_status="$?"
  if [ "$bootstrap_status" -ne 0 ]; then
    echo "Graphical session bootstrap failed during '$step_name' (exit $bootstrap_status)."
    if [ -s "$graphical_bootstrap_log" ]; then
      echo "Bootstrap output:"
      cat "$graphical_bootstrap_log"
    else
      echo "Bootstrap produced no stdout/stderr."
    fi
    print_sanitized_qemu_log_tail
    exit 1
  fi
}

serial_socket_login() {
  if [ -z "${qemu_serial_socket:-}" ]; then
    echo "QEMU serial socket is not available for graphical session bootstrap."
    exit 1
  fi
  python3 - "$qemu_serial_socket" "$homed_firstboot_user" "$homed_firstboot_password" <<'PY'
import os
import re
import socket
import sys
import time

sock_path, username, password = sys.argv[1:4]
deadline = time.time() + 30

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(0.5)
while True:
    try:
        sock.connect(sock_path)
        break
    except OSError:
        if time.time() >= deadline:
            raise SystemExit("Timed out connecting to QEMU serial socket")
        time.sleep(0.2)

buffer = b""
password_sent = False

def recv_until(patterns, timeout_s, poke=False):
    global buffer
    end = time.time() + timeout_s
    poked = False
    while time.time() < end:
        for pattern in patterns:
            if re.search(pattern, buffer, re.IGNORECASE):
                return pattern
        try:
            chunk = sock.recv(4096)
            if chunk:
                buffer += chunk
                continue
        except socket.timeout:
            pass
        if poke and not poked:
            sock.sendall(b"\n")
            poked = True
        time.sleep(0.1)
    raise SystemExit(f"Timed out waiting for serial prompt: {[p.decode() for p in patterns]}")

recv_until([b"login:\\s*$", b"archlinux login:\\s*$"], 20, poke=True)
sock.sendall(username.encode("ascii") + b"\n")
recv_until([b"password:\\s*$"], 10)
sock.sendall(password.encode("ascii") + b"\n")
password_sent = True
result = recv_until(
    [
        b"login incorrect",
        b"authentication failure",
        b"too many unsuccessful login attempts",
        b"last login",
        b"\\$\\s*$",
        b"#\\s*$",
        b"\\[.*@.*\\]\\$\\s*$",
        b"login:\\s*$",
        b"archlinux login:\\s*$",
    ],
    15,
)
if result in (b"login incorrect", b"authentication failure", b"too many unsuccessful login attempts"):
    raise SystemExit(
        "Serial login was rejected\n--- serial transcript ---\n"
        + buffer.decode("utf-8", "replace")
    )
if password_sent and result in (b"login:\\s*$", b"archlinux login:\\s*$"):
    raise SystemExit(
        "Serial login returned to login prompt before reaching a shell\n--- serial transcript ---\n"
        + buffer.decode("utf-8", "replace")
    )
sock.close()
PY
}

  run_graphical_bootstrap_step "install smoke Hypr config" "
    set -eu
    install -d -o $homed_firstboot_user -g $homed_firstboot_user -m 0755 $homed_firstboot_image_path/.config/hypr/hyprland.conf.d
    install -d -o $homed_firstboot_user -g $homed_firstboot_user -m 0755 $homed_firstboot_image_path/.local/share/cloudflare-warp-gui
    rm -f $homed_firstboot_image_path/.config/hypr/hyprland.conf.d/99-graphical-smoke.conf
    cat >/etc/profile.d/uwsm.sh <<'EOF'
if uwsm check may-start; then
    if [ "\${LOGNAME:-\${USER:-}}" = "$homed_firstboot_user" ] && [ "\${XDG_VTNR:-}" = "1" ]; then
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
  "

  run_graphical_bootstrap_step "enable linger" "
    set -eu
    loginctl enable-linger $homed_firstboot_user
  "

  run_graphical_bootstrap_step "prepare tty1 login" "
    set -eu
    faillock --user $homed_firstboot_user --reset >/dev/null 2>&1 || true
    systemctl restart getty@tty1.service >/dev/null 2>&1 || true
    systemctl restart serial-getty@ttyS0.service >/dev/null 2>&1 || true
    chvt 1 >/dev/null 2>&1 || true
  "

  run_graphical_bootstrap_step "wait for homed activation readiness" "
    set -eu
    start=\$(date +%s)
    while true; do
      output=\$(PASSWORD='$homed_firstboot_password' homectl activate $homed_firstboot_user 2>&1) && {
        homectl deactivate $homed_firstboot_user >/dev/null 2>&1 || true
        exit 0
      }
      case \"\$output\" in
        *\"currently being used\"*|*\"operation on home\"*)
          now=\$(date +%s)
          if [ \$((now - start)) -ge 60 ]; then
            printf '%s\n' \"\$output\" >&2
            exit 1
          fi
          sleep 2
          ;;
        *)
          printf '%s\n' \"\$output\" >&2
          exit 1
          ;;
      esac
    done
  "

  if [ -z "${homed_firstboot_password:-}" ]; then
    echo "No homed firstboot password is available for graphical login."
    print_sanitized_qemu_log_tail
    exit 1
  fi
  if [ "$qemu_serial_mode" != "socket" ] || [ -z "${qemu_serial_socket:-}" ]; then
    echo "Graphical session bootstrap requires a QEMU serial socket."
    print_sanitized_qemu_log_tail
    exit 1
  fi

  debug "Graphical bootstrap: inject serial login via QEMU serial socket..."
  sleep 2
  serial_login_status=1
  serial_login_attempt=1
  while [ "$serial_login_attempt" -le 3 ]; do
    if serial_socket_login; then
      serial_login_status=0
      break
    fi
    timeout 10 ssh \
      -o BatchMode=yes \
      -o ConnectTimeout=5 \
      -o NumberOfPasswordPrompts=0 \
      -o PasswordAuthentication=no \
      -o KbdInteractiveAuthentication=no \
      -o GSSAPIAuthentication=no \
      -o LogLevel=ERROR \
      ${ssh_extra_opts} \
      -p "$ssh_port" "$ssh_user@127.0.0.1" "
        set -eu
        faillock --user $homed_firstboot_user --reset >/dev/null 2>&1 || true
        loginctl terminate-user $homed_firstboot_user >/dev/null 2>&1 || true
        systemctl stop user@$homed_firstboot_uid.service >/dev/null 2>&1 || true
        homectl deactivate $homed_firstboot_user >/dev/null 2>&1 || true
        systemctl restart serial-getty@ttyS0.service >/dev/null 2>&1 || true
      " >/dev/null 2>&1 || true
    sleep 3
    serial_login_attempt=$((serial_login_attempt + 1))
  done
  if [ "$serial_login_status" -ne 0 ]; then
    echo "Graphical session bootstrap failed during 'serial login injection'."
    timeout 15 ssh \
      -o BatchMode=yes \
      -o ConnectTimeout=5 \
      -o NumberOfPasswordPrompts=0 \
      -o PasswordAuthentication=no \
      -o KbdInteractiveAuthentication=no \
      -o GSSAPIAuthentication=no \
      -o LogLevel=ERROR \
      ${ssh_extra_opts} \
      -p "$ssh_port" "$ssh_user@127.0.0.1" "
        set -eu
        echo '--- homed user ---'
        homectl inspect $homed_firstboot_user --no-pager 2>/dev/null || true
        echo '--- tty/login journal ---'
        journalctl -b --no-pager -n 200 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|ttyS0|homed|home1' || true
        echo '--- serial getty status ---'
        systemctl status serial-getty@ttyS0.service --no-pager 2>/dev/null || true
      " || true
    print_sanitized_qemu_log_tail
    exit 1
  fi

  run_graphical_bootstrap_step "autologin smoke on tty1 after homed activation" "
    set -eu
    install -d /run/systemd/system/getty@tty1.service.d
    cat >/run/systemd/system/getty@tty1.service.d/10-smoke-autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/usr/bin/agetty --autologin $homed_firstboot_user --noreset --noclear --issue-file=/etc/issue:/etc/issue.d:/run/issue.d:/usr/lib/issue.d - linux
EOF
    systemctl daemon-reload
    systemctl restart getty@tty1.service
    chvt 1 >/dev/null 2>&1 || true
    sleep 1
    printf '\r\r' >/dev/tty1 || true
  "

  debug "Graphical bootstrap: wait for homed login activation..."
  homed_activation_status=0
  timeout 30 ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o NumberOfPasswordPrompts=0 \
    -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no \
    -o GSSAPIAuthentication=no \
    -o LogLevel=ERROR \
    ${ssh_extra_opts} \
    -p "$ssh_port" "$ssh_user@127.0.0.1" "
      set -eu
      start=\$(date +%s)
      while true; do
        if homectl inspect $homed_firstboot_user --no-pager 2>/dev/null | grep -Fqx '       State: active'; then
          exit 0
        fi
        now=\$(date +%s)
        if [ \$((now - start)) -ge 25 ]; then
          exit 1
        fi
        sleep 1
      done
    " >"$graphical_bootstrap_log" 2>&1 || homed_activation_status="$?"
  if [ "$homed_activation_status" -ne 0 ]; then
    echo "Graphical session bootstrap failed during 'wait for homed login activation' (exit $homed_activation_status)."
    timeout 15 ssh \
      -o BatchMode=yes \
      -o ConnectTimeout=5 \
      -o NumberOfPasswordPrompts=0 \
      -o PasswordAuthentication=no \
      -o KbdInteractiveAuthentication=no \
      -o GSSAPIAuthentication=no \
      -o LogLevel=ERROR \
      ${ssh_extra_opts} \
      -p "$ssh_port" "$ssh_user@127.0.0.1" "
        set -eu
        echo '--- homed user ---'
        homectl inspect $homed_firstboot_user --no-pager 2>/dev/null || true
        echo '--- tty/login journal ---'
        journalctl -b --no-pager -n 200 2>/dev/null | grep -Ei 'pam|login|agetty|tty1|homed|home1' || true
        echo '--- getty@tty1 status ---'
        systemctl status getty@tty1.service --no-pager 2>/dev/null || true
      " || true
    print_sanitized_qemu_log_tail
    exit 1
  fi

  rm -f "$graphical_bootstrap_log"
fi

if [ "$run_smoke_tests" != "1" ]; then
  log "VM is running."
  log "SSH: ssh ${ssh_extra_opts} -p $ssh_port $ssh_user@127.0.0.1"
  if [ "$graphical_session_smoke" = "1" ]; then
    log "Close the QEMU window or press Ctrl-C here to stop the VM."
  fi
  vm_status=0
  wait "$vm_pid" || vm_status="$?"
  if [ "$vm_status" -eq 0 ]; then
    boot_vm_success=1
  fi
  trap - EXIT INT TERM
  cleanup
  exit "$vm_status"
fi

BOOTC_VM_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o GSSAPIAuthentication=no -o KbdInteractiveAuthentication=no -o PasswordAuthentication=no -o NumberOfPasswordPrompts=0 -o LogLevel=ERROR ${ssh_extra_opts} -p $ssh_port $ssh_user@127.0.0.1" \
BOOTC_VM_BOOT_TIMEOUT_S="$boot_timeout" \
BOOTC_VM_DIRECT_KERNEL_BOOT="$direct_kernel_boot" \
BOOTC_VM_GRAPHICAL_SESSION_SMOKE="$graphical_session_smoke" \
BOOTC_VM_HOMED_FIRSTBOOT_USER="$homed_firstboot_user" \
BOOTC_VM_HOMED_FIRSTBOOT_UID="$homed_firstboot_uid" \
mise exec -- bats tests/smoke/vm-bootc.bats &
bats_pid="$!"

while kill -0 "$bats_pid" 2>/dev/null; do
  if ! kill -0 "$vm_pid" 2>/dev/null; then
    echo "mkosi/qemu exited before smoke tests completed"
    print_graphical_guest_diagnostics
    print_sanitized_qemu_log_tail
    kill "$bats_pid" >/dev/null 2>&1 || true
    wait "$bats_pid" >/dev/null 2>&1 || true
    exit 1
  fi

  if grep -Eq \
    "Could not set up host forwarding rule|Address already in use|Could not access KVM kernel module|failed to initialize kvm|could not open disk image|Failed to get \"write\" lock" \
    "$log_file"; then
    echo "Detected fatal qemu error while smoke tests were running"
    print_graphical_guest_diagnostics
    print_sanitized_qemu_log_tail
    kill "$vm_pid" "$bats_pid" >/dev/null 2>&1 || true
    wait "$bats_pid" >/dev/null 2>&1 || true
    exit 1
  fi

  sleep 2
done

bats_status=0
wait "$bats_pid" || bats_status="$?"
if [ "$bats_status" -ne 0 ]; then
  if command -v print_graphical_guest_diagnostics >/dev/null 2>&1; then
    print_graphical_guest_diagnostics
  fi
fi
trap - EXIT INT TERM
if [ "$bats_status" -eq 0 ]; then
  boot_vm_success=1
fi
cleanup
exit "$bats_status"
