from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relay_rules import relay_classification_reason


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify relay/API-credit products")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row
    matches = []
    for row in connection.execute(
        "SELECT goods_key, name, description_excerpt, tags, active, off_shelf FROM products ORDER BY goods_key"
    ):
        reason = relay_classification_reason(row["name"], row["description_excerpt"])
        if not reason:
            continue
        try:
            tags = json.loads(row["tags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        matches.append({
            "goods_key": row["goods_key"], "name": row["name"], "reason": reason,
            "previous_tags": tags, "active": row["active"], "off_shelf": row["off_shelf"],
        })
        if args.apply and "relay" not in tags:
            tags.append("relay")
            connection.execute(
                "UPDATE products SET tags = ?, changed_at = strftime('%s','now') WHERE goods_key = ?",
                (json.dumps(tags, ensure_ascii=False, separators=(",", ":")), row["goods_key"]),
            )
    if args.apply:
        timestamp = int(time.time())
        connection.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES('catalog_revision',?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (str(timestamp), timestamp),
        )
        connection.commit()
    counts: dict[str, int] = {}
    for match in matches:
        counts[match["reason"]] = counts.get(match["reason"], 0) + 1
    args.report.write_text(json.dumps({
        "applied": args.apply, "matched": len(matches), "reason_counts": counts, "products": matches,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": args.apply, "matched": len(matches), "reason_counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
