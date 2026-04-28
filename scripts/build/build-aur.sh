#!/usr/bin/env bash
set -euo pipefail

exec /usr/bin/python3 /usr/libexec/build-aur.py "$@"
