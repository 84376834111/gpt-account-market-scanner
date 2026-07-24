#!/usr/bin/env python3
"""Force the direct leg to fail and verify the real Mihomo fallback path."""

from __future__ import annotations

import urllib.error

from app import LDXPClient


class FailingDirectOpener:
    def open(self, *_args, **_kwargs):
        raise urllib.error.URLError("intentional direct-path test failure")


def main() -> int:
    client = LDXPClient(
        timeout=12,
        proxy_url="http://127.0.0.1:7891",
        direct_attempts=1,
        proxy_attempts=3,
        retry_delay=0.2,
    )
    client.direct_opener = FailingDirectOpener()
    shop = client.shop_info("CodexBro")
    if not isinstance(shop, dict) or not shop:
        raise SystemExit("failover request did not return shop data")
    print("APPLICATION_FAILOVER_OK=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
