#!/usr/bin/env python3
"""Probe how many items LDXP actually returns for requested page sizes."""

from __future__ import annotations

import sys

from app import GOODS_TYPES, LDXPClient, safe_int


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: probe_ldxp_page_size.py SHOP_TOKEN")

    token = sys.argv[1]
    client = LDXPClient()
    shop = client.shop_info(token)
    goods_types = [
        goods_type
        for goods_type in GOODS_TYPES
        if safe_int(shop.get(f"{goods_type}_count"), 0) > 0
    ]
    print(f"ACTIVE_TYPES={len(goods_types)}")
    for goods_type in goods_types:
        declared = safe_int(shop.get(f"{goods_type}_count"), 0)
        for requested in (100, 300, 500):
            payload = client.goods_page(token, goods_type, 1, requested)
            returned = len(payload.get("list") or [])
            total = safe_int(payload.get("total"), returned)
            print(
                f"TYPE={goods_type} DECLARED={declared} "
                f"REQUESTED={requested} RETURNED={returned} TOTAL={total}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
