#!/usr/bin/env bash
exec python3 "$(dirname "$0")/with_podman_wrapper.py" "$@"
