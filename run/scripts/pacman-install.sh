#!/usr/bin/env bash
set -euo pipefail

if [ ! -e /usr/lib/pacman/sync/core.db ]; then
    pacman -Sy --noconfirm
fi

exec pacman -S --noconfirm --needed "$@"
