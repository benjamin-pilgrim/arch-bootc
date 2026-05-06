#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


def is_record(value: Any) -> bool:
    return isinstance(value, dict)


def statusline_rate_limits_path() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return state_home / "claude-code" / "statusline-rate-limits.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    temp_path.replace(path)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if not is_record(payload):
        return 0

    rate_limits = payload.get("rate_limits")
    if not is_record(rate_limits):
        return 0

    record = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "sessionId": payload.get("session_id"),
        "transcriptPath": payload.get("transcript_path"),
        "cwd": payload.get("cwd"),
        "version": payload.get("version"),
        "rate_limits": rate_limits,
    }

    try:
        atomic_write_json(statusline_rate_limits_path(), record)
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
