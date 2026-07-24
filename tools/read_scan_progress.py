#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter


def main() -> None:
    database = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/ldxp-scanner/ldxp.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    statuses = {
        row["status"]: row["count"]
        for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM sources GROUP BY status"
        )
    }
    recent = [
        dict(row)
        for row in connection.execute(
            """
            SELECT token, status, product_count, last_error
            FROM sources ORDER BY updated_at DESC LIMIT 5
            """
        )
    ]
    errors = [
        dict(row)
        for row in connection.execute(
            """
            SELECT token, name, last_error
            FROM sources WHERE status = 'error' ORDER BY updated_at DESC
            """
        )
    ]
    total = connection.execute(
        "SELECT COUNT(*) FROM products WHERE active = 1"
    ).fetchone()[0]
    bugteam = connection.execute(
        "SELECT COUNT(*) FROM products WHERE active = 1 AND tags LIKE '%\"bugteam\"%'"
    ).fetchone()[0]
    catfk = connection.execute(
        "SELECT COUNT(*) FROM sources WHERE base_url LIKE '%catfk.com%'"
    ).fetchone()[0]
    tag_counts: Counter[str] = Counter()
    for row in connection.execute("SELECT tags FROM products WHERE active = 1"):
        tag_counts.update(json.loads(row["tags"] or "[]"))
    platform_products = {
        row["base_url"]: row["count"]
        for row in connection.execute(
            """
            SELECT sources.base_url, COUNT(products.goods_key) AS count
            FROM sources
            LEFT JOIN products
              ON products.source_token = sources.token AND products.active = 1
            GROUP BY sources.base_url
            """
        )
    }
    print(
        json.dumps(
            {
                "statuses": statuses,
                "recent": recent,
                "errors": errors,
                "active_products": total,
                "bugteam": bugteam,
                "catfk_sources": catfk,
                "tag_counts": dict(sorted(tag_counts.items())),
                "platform_products": platform_products,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
