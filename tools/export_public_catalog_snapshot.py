from __future__ import annotations

import gzip
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path


def main() -> None:
    database = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT p.name, p.price, p.market_price, p.stock_count, p.in_stock,
               p.tags, p.link, p.last_seen,
               COALESCE(m.comment_count, 0) AS review_count,
               ROUND(COALESCE(m.rating_average, 0), 3) AS rating_average,
               ROUND(COALESCE(m.weighted_score, 0), 3) AS weighted_score
        FROM products AS p
        LEFT JOIN product_comment_metrics AS m ON m.goods_key = p.goods_key
        WHERE p.active = 1 AND p.off_shelf = 0 AND p.platform_banned = 0
        ORDER BY p.name COLLATE NOCASE, p.link
        """
    )
    snapshot = output_dir / "catalog-snapshot.jsonl.gz"
    categories: Counter[str] = Counter()
    stock = Counter()
    reviewed_products = reviews = 0
    total = 0
    with gzip.open(snapshot, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            item = dict(row)
            try:
                item["categories"] = json.loads(item.pop("tags") or "[]")
            except json.JSONDecodeError:
                item["categories"] = []
            categories.update(item["categories"])
            count = int(item["stock_count"])
            stock["unknown" if count < 0 else "out_of_stock" if count == 0 else "in_stock"] += 1
            review_count = int(item["review_count"])
            if review_count:
                reviewed_products += 1
                reviews += review_count
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            total += 1
    summary = {
        "generated_at": int(time.time()),
        "products": total,
        "inventory": dict(stock),
        "categories": dict(sorted(categories.items())),
        "reviews": {"products_with_reviews": reviewed_products, "review_count": reviews},
        "snapshot": snapshot.name,
        "privacy": "No server address, credentials, internal source tokens, reviewer identity, review body, or image data.",
    }
    (output_dir / "catalog-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
