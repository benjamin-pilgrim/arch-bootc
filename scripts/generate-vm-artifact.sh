#!/usr/bin/env bash
exec python3 "$(dirname "$0")/generate_vm_artifact.py" "$@"
