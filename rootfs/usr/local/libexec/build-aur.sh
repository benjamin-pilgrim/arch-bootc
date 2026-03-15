#!/usr/bin/env bash
set -euo pipefail

exec /usr/bin/python3 /usr/local/libexec/build-aur.py "$@"
