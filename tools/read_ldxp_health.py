#!/usr/bin/env python3
"""Print a compact, non-sensitive LDXP scanner health summary."""

from __future__ import annotations

import json
import urllib.request


def main() -> int:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=10) as response:
        health = json.load(response)
    stats = health.get("stats") or {}
    print(f"SCANNING={str(bool(health.get('scanning'))).lower()}")
    print(f"SCAN_INTERVAL={health.get('scan_interval')}")
    print(f"AUTO_SCAN_ENABLED={str(bool(health.get('auto_scan_enabled'))).lower()}")
    print(f"SOURCE_INTERVAL={health.get('source_interval')}")
    print(f"DISCOVERY_INTERVAL={health.get('discovery_interval')}")
    print(f"PAGE_SIZE={health.get('page_size')}")
    print(f"FAILOVER_ENABLED={str(bool(health.get('failover_proxy_enabled'))).lower()}")
    print(f"LAST_STARTED={health.get('last_started')}")
    print(f"LAST_COMPLETED={health.get('last_completed')}")
    print(f"SOURCES={stats.get('sources')}")
    print(f"PRODUCTS={stats.get('total')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
