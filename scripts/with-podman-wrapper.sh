#!/usr/bin/env bash

set -eu

use_run0_podman="${BOOTC_PODMAN_USE_RUN0:-1}"
podman_wrapper_dir=""

cleanup() {
  if [ -n "${podman_wrapper_dir:-}" ] && [ -d "${podman_wrapper_dir:-}" ]; then
    rm -rf "$podman_wrapper_dir"
  fi
}

trap cleanup EXIT

if [ "$use_run0_podman" = "1" ] && [ "$(id -u)" -ne 0 ]; then
  podman_wrapper_dir="$(mktemp -d "${TMPDIR:-/tmp}/podman-wrapper.XXXXXX")"
  if command -v run0 >/dev/null 2>&1; then
    cat >"$podman_wrapper_dir/podman" <<'EOF'
#!/bin/sh
exec run0 podman "$@"
EOF
  elif command -v sudo >/dev/null 2>&1; then
    cat >"$podman_wrapper_dir/podman" <<'EOF'
#!/bin/sh
exec sudo podman "$@"
EOF
  fi
fi

if [ -n "${podman_wrapper_dir:-}" ] && [ -f "${podman_wrapper_dir:-}/podman" ]; then
  chmod +x "$podman_wrapper_dir/podman"
  PATH="$podman_wrapper_dir:$PATH"
fi

exec "$@"
