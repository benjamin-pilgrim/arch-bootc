from __future__ import annotations

import os
import pathlib
import stat
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "rootfs/usr/share/hypr/scripts/toggle-bluetooth"


def run_toggle(tmp_path: pathlib.Path, powered: str | None) -> list[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    state = tmp_path / "state"
    if powered is not None:
        state.write_text(f"{powered}\n")

    bluetoothctl = bin_dir / "bluetoothctl"
    bluetoothctl.write_text(
        """#!/bin/sh
set -eu
case "$1" in
  show)
    if [ -f "$BT_STATE" ]; then
      printf 'Controller 00:11:22:33:44:55\\n'
      printf '    Powered: %s\\n' "$(cat "$BT_STATE")"
    else
      exit 1
    fi
    ;;
  power)
    printf '%s\\n' "$*" >>"$BT_LOG"
    ;;
  *)
    exit 1
    ;;
esac
"""
    )
    notify_send = bin_dir / "notify-send"
    notify_send.write_text(
        """#!/bin/sh
printf 'notify %s\\n' "$*" >>"$BT_LOG"
"""
    )
    for command in (bluetoothctl, notify_send):
        command.chmod(command.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["BT_LOG"] = str(log)
    env["BT_STATE"] = str(state)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    subprocess.run([str(SCRIPT)], check=True, env=env)
    return log.read_text().splitlines()


def test_toggle_bluetooth_turns_powered_controller_off(tmp_path: pathlib.Path) -> None:
    assert run_toggle(tmp_path, "yes") == ["power off", "notify Bluetooth Off"]


def test_toggle_bluetooth_turns_unpowered_controller_on(tmp_path: pathlib.Path) -> None:
    assert run_toggle(tmp_path, "no") == ["power on", "notify Bluetooth On"]


def test_toggle_bluetooth_reports_missing_controller(tmp_path: pathlib.Path) -> None:
    assert run_toggle(tmp_path, None) == ["notify Bluetooth No controller available"]
