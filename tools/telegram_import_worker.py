from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--resolver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-key", default="ga7uvr")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--attempts", type=int, default=20)
    args = parser.parse_args()

    sys.path.insert(0, str(args.app_dir.resolve()))
    from app import LDXPClient  # noqa: PLC0415

    available = False
    for attempt in range(1, args.attempts + 1):
        try:
            product = LDXPClient().goods_info(args.probe_key)
            available = bool(product.get("goods_key"))
        except Exception as exc:
            print(
                json.dumps(
                    {"phase": "probe", "attempt": attempt, "ok": False, "error": str(exc)},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            print(
                json.dumps({"phase": "probe", "attempt": attempt, "ok": available}, ensure_ascii=False),
                flush=True,
            )
        if available:
            break
        if attempt < args.attempts:
            time.sleep(args.interval)

    if not available:
        raise SystemExit("LDXP API did not recover within the retry window")

    env = os.environ.copy()
    command = [
        sys.executable,
        str(args.resolver),
        str(args.input),
        "--app-dir",
        str(args.app_dir),
        "--output",
        str(args.output),
        "--workers",
        "1",
        "--delay",
        "0.25",
        "--apply",
    ]
    subprocess.run(command, check=True, env=env)
    report = json.loads(args.output.read_text(encoding="utf-8"))
    if not report.get("valid_shops") or not report.get("resolved_items"):
        raise RuntimeError("LDXP API recovered only partially; retry is required")
    if report.get("applied"):
        request = urllib.request.Request(
            "http://127.0.0.1:8765/api/scan",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    print(
        json.dumps(
            {
                "phase": "complete",
                "valid_shops": len(report.get("valid_shops") or []),
                "already_existing": len(report.get("already_existing") or []),
                "applied": len(report.get("applied") or []),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
