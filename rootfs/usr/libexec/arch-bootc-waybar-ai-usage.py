#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BATTERY_ICONS = ["", "", "", "", ""]
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


def is_record(value: Any) -> bool:
    return isinstance(value, dict)


def clamp_percent(value: float | int) -> int:
    return max(0, min(100, int(round(value))))


def remaining_percent(used_percent: float | int) -> int:
    return max(0, min(100, 100 - clamp_percent(used_percent)))


def battery_icon(percent: int) -> str:
    if percent <= 0:
        return BATTERY_ICONS[0]
    if percent <= 20:
        return BATTERY_ICONS[1]
    if percent <= 45:
        return BATTERY_ICONS[2]
    if percent <= 70:
        return BATTERY_ICONS[3]
    return BATTERY_ICONS[4]


def format_duration(ms: int | None) -> str | None:
    if ms is None or ms <= 0:
        return None

    minutes = (ms + 59_999) // 60_000
    if minutes < 60:
        return f"{minutes}m"

    hours = (minutes + 59) // 60
    if hours < 48:
        return f"{hours}h"

    days = (hours + 23) // 24
    return f"{days}d"


def to_iso_date(epoch_seconds: int | float | None) -> str | None:
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc).isoformat()
    except Exception:
        return None


def read_json_lines(path: Path) -> list[Any]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception:
        return []


def newest_jsonl_files(root: Path, max_files: int = 8) -> list[Path]:
    if not root.exists():
        return []

    entries: list[tuple[float, Path]] = []
    stack = [root]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as dir_entries:
                for entry in dir_entries:
                    entry_path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry_path)
                        continue
                    if not entry.is_file(follow_symlinks=False) or not entry.name.endswith(".jsonl"):
                        continue
                    try:
                        entries.append((entry.stat(follow_symlinks=False).st_mtime, entry_path))
                    except OSError:
                        continue
        except OSError:
            continue

    return [path for _, path in sorted(entries, key=lambda item: item[0], reverse=True)[:max_files]]


def parse_rate_bucket(bucket: Any) -> dict[str, Any] | None:
    if not is_record(bucket):
        return None

    used = bucket.get("usedPercent")
    if not isinstance(used, (int, float)):
        used = bucket.get("used_percent")
    if not isinstance(used, (int, float)):
        used = bucket.get("utilization")
    if not isinstance(used, (int, float)):
        return None

    window_minutes = bucket.get("windowMinutes")
    if not isinstance(window_minutes, (int, float)):
        window_minutes = bucket.get("windowDurationMins")
    if not isinstance(window_minutes, (int, float)):
        window_minutes = bucket.get("window_minutes")
    if not isinstance(window_minutes, (int, float)):
        window_minutes = None

    resets_at = bucket.get("resetsAt")
    if resets_at is None:
        resets_at = bucket.get("resets_at")

    parsed: dict[str, Any] = {
        "usedPercent": float(used),
    }
    if isinstance(window_minutes, (int, float)):
        parsed["windowMinutes"] = int(window_minutes)
    if isinstance(resets_at, (int, float)):
        parsed["resetsAt"] = to_iso_date(resets_at)
    elif isinstance(resets_at, str):
        parsed["resetsAt"] = resets_at
    return parsed


def parse_codex_rate_limits(payload: Any) -> dict[str, Any] | None:
    if not is_record(payload):
        return None

    rate_limits = payload.get("rateLimits")
    if not is_record(rate_limits):
        return None

    primary = parse_rate_bucket(rate_limits.get("primary"))
    secondary = parse_rate_bucket(rate_limits.get("secondary"))
    if not primary and not secondary:
        return None

    status = "rate_limited" if any(
        bucket and bucket.get("usedPercent", 0) >= 100 for bucket in (primary, secondary)
    ) else "ok"

    return {
        "source": "codex_app_server",
        "status": status,
        "primary": primary,
        "secondary": secondary,
    }


def codex_app_server_request(messages: list[dict[str, Any]], timeout_s: float = 8.0) -> dict[str, Any] | None:
    proc = subprocess.Popen(
        ["codex", "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    def send(message: dict[str, Any]) -> None:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    try:
        send({
            "method": "initialize",
            "id": 0,
            "params": {
                "clientInfo": {
                    "name": "waybar",
                    "title": "Waybar",
                    "version": "1.0.0",
                },
            },
        })
        send({"method": "initialized", "params": {}})

        pending = {msg["id"] for msg in messages if "id" in msg}
        responses: dict[int, Any] = {}
        deadline = time.monotonic() + timeout_s

        for message in messages:
            send(message)

        while pending and time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if is_record(payload) and isinstance(payload.get("id"), int) and payload["id"] in pending:
                responses[payload["id"]] = payload
                pending.discard(payload["id"])

        if not responses:
            return None
        return responses[max(responses)]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def fetch_codex_usage() -> dict[str, Any] | None:
    account = codex_app_server_request([{"method": "account/read", "id": 1, "params": {"refreshToken": False}}])
    if not is_record(account):
        return None

    account_result = account.get("result")
    if not is_record(account_result):
        return None

    account_info = account_result.get("account")
    if not is_record(account_info):
        return None

    account_type = account_info.get("type")
    if account_type not in {"chatgpt", "chatgptAuthTokens"}:
        return None

    rate_limits = codex_app_server_request([{"method": "account/rateLimits/read", "id": 2}])
    if not is_record(rate_limits):
        return None
    summary = parse_codex_rate_limits(rate_limits.get("result"))
    if summary:
        summary["fetchedAt"] = datetime.now(timezone.utc).isoformat()
    return summary


def claude_monitor_auth_path(home_dir: Path) -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or (home_dir / ".cache"))
    return cache_home / "waybar-ai-claude-auth.json"


def read_claude_monitor_auth(home_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(claude_monitor_auth_path(home_dir).read_text(encoding="utf-8"))
    except Exception:
        payload = None

    if is_record(payload) and is_record(payload.get("claudeAiOauth")):
        return payload
    return None


def write_claude_monitor_auth(home_dir: Path, credentials: dict[str, Any]) -> None:
    auth_path = claude_monitor_auth_path(home_dir)
    try:
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(credentials, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_claude_monitor_token(home_dir: Path) -> tuple[str | None, dict[str, Any] | None, str]:
    setup_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if isinstance(setup_token, str) and setup_token.strip():
        return setup_token.strip(), None, "setup_token"

    credentials = read_claude_monitor_auth(home_dir)
    token = credentials.get("claudeAiOauth", {}).get("accessToken") if is_record(credentials) else None
    if isinstance(token, str) and token.strip():
        source = credentials.get("claudeAiOauth", {}).get("source") if is_record(credentials) else None
        if source == "setup_token":
            return token.strip(), credentials, "setup_token"
        return token.strip(), credentials, "oauth"

    return None, None, "none"


def claude_usage_cache_path(home_dir: Path) -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or (home_dir / ".cache"))
    return cache_home / "waybar-ai-claude-usage.json"


def claude_statusline_rate_limits_path(home_dir: Path) -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (home_dir / ".local" / "state"))
    return state_home / "claude-code" / "statusline-rate-limits.json"


def read_cached_claude_usage(home_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(claude_usage_cache_path(home_dir).read_text(encoding="utf-8"))
    except Exception:
        return None

    if not is_record(payload):
        return None
    return payload


def write_cached_claude_usage(home_dir: Path, summary: dict[str, Any]) -> None:
    cache_path = claude_usage_cache_path(home_dir)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def read_claude_statusline_usage(home_dir: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(claude_statusline_rate_limits_path(home_dir).read_text(encoding="utf-8"))
    except Exception:
        return None

    if not is_record(payload):
        return None

    rate_limits = payload.get("rate_limits")
    if not is_record(rate_limits):
        return None

    five_hour = rate_limits.get("five_hour")
    seven_day = rate_limits.get("seven_day")
    primary = parse_rate_bucket({
        "used_percent": five_hour.get("used_percentage") if is_record(five_hour) else None,
        "window_minutes": 300,
        "resets_at": five_hour.get("resets_at") if is_record(five_hour) else None,
    })
    secondary = parse_rate_bucket({
        "used_percent": seven_day.get("used_percentage") if is_record(seven_day) else None,
        "window_minutes": 10080,
        "resets_at": seven_day.get("resets_at") if is_record(seven_day) else None,
    })
    if not primary and not secondary:
        return None

    summary = {
        "source": "claude_statusline",
        "status": "rate_limited" if any(
            bucket and bucket.get("usedPercent", 0) >= 100 for bucket in (primary, secondary)
        ) else "ok",
        "primary": primary,
        "secondary": secondary,
    }
    fetched_at = payload.get("fetchedAt")
    if isinstance(fetched_at, str):
        summary["fetchedAt"] = fetched_at
    return summary


def provision_claude_monitor_auth(home_dir: Path) -> int:
    env_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if isinstance(env_token, str) and env_token.strip():
        monitor_credentials = {
            "claudeAiOauth": {
                "accessToken": env_token.strip(),
                "source": "setup_token",
            },
        }
        write_claude_monitor_auth(home_dir, monitor_credentials)
        print(f"seeded {claude_monitor_auth_path(home_dir)} from CLAUDE_CODE_OAUTH_TOKEN", file=sys.stderr)
        return 0

    try:
        proc = subprocess.run(["claude", "setup-token"], check=False)
    except FileNotFoundError:
        print("claude is not installed", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"failed to start claude setup-token: {error}", file=sys.stderr)
        return 1

    if proc.returncode != 0:
        return proc.returncode

    print("Paste the long-lived Claude token that setup-token printed, then press Enter:", file=sys.stderr)
    try:
        pasted_token = input().strip()
    except EOFError:
        pasted_token = ""

    if not pasted_token:
        print("no token pasted; private Claude monitor cache was not seeded", file=sys.stderr)
        return 1

    monitor_credentials = {
        "claudeAiOauth": {
            "accessToken": pasted_token,
            "source": "setup_token",
        },
    }
    write_claude_monitor_auth(home_dir, monitor_credentials)
    print(f"seeded {claude_monitor_auth_path(home_dir)}", file=sys.stderr)
    return 0


def get_claude_code_version() -> str:
    try:
        proc = subprocess.run(
            ["claude", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"

    stdout = (proc.stdout or "").strip()
    match = None
    if stdout:
        import re
        match = re.search(r"^(\d+\.\d+\.\d+)", stdout)
    return match.group(1) if match else "unknown"


def refresh_claude_access_token(home_dir: Path, credentials: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    refresh_token = credentials.get("claudeAiOauth", {}).get("refreshToken") if is_record(credentials) else None
    if not isinstance(refresh_token, str):
        return None, None

    import urllib.request

    request = urllib.request.Request(
        "https://console.anthropic.com/v1/oauth/token",
        method="POST",
        headers={
            "content-type": "application/json",
            "user-agent": f"claude-code/{get_claude_code_version()}",
        },
        data=json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
        }).encode("utf-8"),
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None, None

    access_token = payload.get("access_token") if is_record(payload) else None
    next_refresh_token = payload.get("refresh_token") if is_record(payload) else None
    if not isinstance(access_token, str) or not isinstance(next_refresh_token, str):
        return None, None

    next_credentials = dict(credentials or {})
    oauth = dict(next_credentials.get("claudeAiOauth") or {})
    oauth["accessToken"] = access_token
    oauth["refreshToken"] = next_refresh_token
    expires_in = payload.get("expires_in") if is_record(payload) else None
    if isinstance(expires_in, (int, float)):
        oauth["expiresAt"] = int(time.time() * 1000 + (float(expires_in) * 1000))
    next_credentials["claudeAiOauth"] = oauth
    write_claude_monitor_auth(home_dir, next_credentials)

    return access_token, next_credentials


def to_claude_usage_summary(payload: Any) -> dict[str, Any] | None:
    if not is_record(payload):
        return None

    five_hour = payload.get("five_hour")
    seven_day = payload.get("seven_day")
    primary = parse_rate_bucket({
        "usedPercent": five_hour.get("utilization") if is_record(five_hour) else None,
        "windowMinutes": 300,
        "resetsAt": five_hour.get("resets_at") if is_record(five_hour) else None,
    })
    secondary = parse_rate_bucket({
        "usedPercent": seven_day.get("utilization") if is_record(seven_day) else None,
        "windowMinutes": 10080,
        "resetsAt": seven_day.get("resets_at") if is_record(seven_day) else None,
    })
    if not primary and not secondary:
        return None
    return {
        "source": "claude_oauth",
        "status": "rate_limited" if any(bucket and bucket.get("usedPercent", 0) >= 100 for bucket in (primary, secondary)) else "ok",
        "primary": primary,
        "secondary": secondary,
    }


def fetch_claude_usage(home_dir: Path) -> dict[str, Any] | None:
    summary = read_claude_statusline_usage(home_dir)
    if summary:
        write_cached_claude_usage(home_dir, summary)
        return summary

    cached = read_cached_claude_usage(home_dir)
    if cached:
        cached["status"] = "stale"
        cached["error"] = "waiting for Claude statusline data"
        return cached

    return None


def format_bucket_label(window_minutes: int) -> str:
    if window_minutes >= 7 * 24 * 60:
        return "7d"
    if window_minutes >= 24 * 60:
        return f"{round(window_minutes / (24 * 60))}d"
    if window_minutes >= 60:
        return f"{round(window_minutes / 60)}h"
    return f"{window_minutes}m"


def format_reset_label(iso_timestamp: str | None) -> str | None:
    if not iso_timestamp:
        return None

    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        remaining_ms = int((dt - datetime.now(timezone.utc)).total_seconds() * 1000)
    except Exception:
        return None

    return format_duration(remaining_ms)


def format_fetched_label(iso_timestamp: str | None) -> str | None:
    if not iso_timestamp:
        return None

    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        remaining_ms = int((datetime.now(timezone.utc) - dt).total_seconds() * 1000)
    except Exception:
        return None

    if remaining_ms < 60_000:
        return "just now"
    return format_duration(remaining_ms)


def format_usage(kind: str, summary: dict[str, Any] | None) -> dict[str, Any]:
    label = "Codex" if kind == "codex" else "Claude"

    if not summary:
        return {
            "text": f"{label} --",
            "tooltip": f"{label} usage unavailable",
            "class": "unavailable",
        }

    primary = summary.get("primary")
    secondary = summary.get("secondary")
    parts: list[str] = []
    tooltips: list[str] = [f"{label} rate limits"]
    remaining_values: list[int] = []
    fetched_at = summary.get("fetchedAt") if is_record(summary) else None

    for bucket in (primary, secondary):
        if not is_record(bucket):
            continue
        used = bucket.get("usedPercent")
        window_minutes = bucket.get("windowMinutes")
        if not isinstance(used, (int, float)) or not isinstance(window_minutes, int):
            continue

        remaining = remaining_percent(used)
        remaining_values.append(remaining)
        reset = format_reset_label(bucket.get("resetsAt") if isinstance(bucket.get("resetsAt"), str) else None)
        visible_reset = f"{reset} " if reset else ""
        parts.append(f"{visible_reset}{battery_icon(remaining)}")

        tooltip = f"{format_bucket_label(window_minutes)}: {clamp_percent(used)}% used, {remaining}% remaining"
        if reset:
            tooltip += f", resets in {reset}"
        tooltips.append(tooltip)

    if not parts:
        return {
            "text": f"{label} --",
            "tooltip": f"{label} usage unavailable",
            "class": "unavailable",
        }

    if isinstance(fetched_at, str):
        fetched = format_fetched_label(fetched_at)
        if fetched:
            tooltips.append(f"last polled {fetched}" if fetched == "just now" else f"last polled {fetched} ago")

    if summary.get("status") == "stale":
        error = summary.get("error")
        if isinstance(error, str) and error:
            tooltips.append(f"showing last successful value ({error})")
        else:
            tooltips.append("showing last successful value")

    if summary.get("status") == "rate_limited":
        class_name = "critical"
    else:
        class_name = "warning" if min(remaining_values) <= 30 else "ok"
        if summary.get("status") == "stale":
            class_name = "warning"

    return {
        "text": f"{label} " + " ".join(parts),
        "tooltip": "\n".join(tooltips),
        "class": class_name,
        "percentage": min(remaining_values),
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"codex", "claude", "provision-claude"}:
        print("{}", end="")
        return 1

    home_dir = Path.home()
    kind = sys.argv[1]
    if kind == "provision-claude":
        return provision_claude_monitor_auth(home_dir)
    summary = fetch_codex_usage() if kind == "codex" else fetch_claude_usage(home_dir)
    payload = format_usage(kind, summary)
    print(json.dumps(payload, ensure_ascii=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
