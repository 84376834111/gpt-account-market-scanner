#!/usr/bin/env python3
"""Server-only controls for LDXP automatic and manual scans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


ENV_FILE = Path("/etc/ldxp-scanner.env")
BASE_URL = "http://127.0.0.1:8765"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def request(path: str, *, method: str = "GET", payload=None, admin: bool = False):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    if admin:
        key = read_env().get("LDXP_ADMIN_KEY", "")
        if not key:
            raise RuntimeError("LDXP_ADMIN_KEY is missing from /etc/ldxp-scanner.env")
        headers["X-LDXP-Admin-Key"] = key
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode()).get("error")
        except Exception:
            message = str(exc)
        raise RuntimeError(message or str(exc)) from exc


def health() -> dict:
    return request("/api/health")


def set_schedule(*, enabled: bool, minutes: int) -> dict:
    if minutes < 1 or minutes > 1440:
        raise ValueError("minutes must be between 1 and 1440")
    return request(
        "/api/settings/scan",
        method="PUT",
        payload={"enabled": enabled, "interval_minutes": minutes},
        admin=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="ldxp-scanctl")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="show current scanner status")
    enable = subparsers.add_parser("enable", help="enable automatic scans")
    enable.add_argument("minutes", nargs="?", type=int)
    subparsers.add_parser("disable", help="pause automatic scans")
    interval = subparsers.add_parser("interval", help="change interval in minutes")
    interval.add_argument("minutes", type=int)
    subparsers.add_parser("scan", help="start one server-side scan")
    subparsers.add_parser("discover", help="discover sources and scan once")
    args = parser.parse_args()

    current = health()
    current_minutes = max(1, round(int(current.get("scan_interval") or 900) / 60))
    if args.command == "status":
        print(f"active={str(bool(current.get('auto_scan_enabled'))).lower()}")
        print(f"interval_minutes={current_minutes}")
        print(f"source_interval_seconds={current.get('source_interval')}")
        print(f"scanning={str(bool(current.get('scanning'))).lower()}")
        return 0
    if args.command == "enable":
        result = set_schedule(enabled=True, minutes=args.minutes or current_minutes)
    elif args.command == "disable":
        result = set_schedule(enabled=False, minutes=current_minutes)
    elif args.command == "interval":
        result = set_schedule(
            enabled=bool(current.get("auto_scan_enabled")), minutes=args.minutes
        )
    elif args.command == "scan":
        result = request("/api/scan", method="POST", payload={}, admin=True)
    else:
        result = request("/api/discover", method="POST", payload={}, admin=True)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
