from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.app_dir.resolve()))
    from app import Database, DB_PATH  # noqa: PLC0415

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.backup:
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as source, sqlite3.connect(args.backup) as destination:
            source.backup(destination)
    database = Database(DB_PATH)
    totals = {
        "sources_completed": 0,
        "sources_failed": 0,
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "removed": 0,
        "unique_goods_keys": set(),
    }
    source_reports: list[dict] = []
    for source in payload.get("sources") or []:
        token = str(source["token"])
        if not source.get("complete"):
            totals["sources_failed"] += 1
            source_reports.append({"token": token, "complete": False, "error": source.get("error") or ""})
            continue
        totals["sources_completed"] += 1
        products = source.get("products") or []
        database.upsert_source(
            token,
            str(source.get("name") or token),
            enabled=True,
            origin="本地电脑扫描",
        )
        seen: set[str] = set()
        changes = {"new": 0, "changed": 0, "unchanged": 0}
        for product in products:
            goods_key = str(product["goods_key"])
            if goods_key in totals["unique_goods_keys"]:
                continue
            totals["unique_goods_keys"].add(goods_key)
            seen.add(goods_key)
            change, _saved = database.upsert_product(product)
            changes[change] += 1
            totals[change] += 1
        removed = database.deactivate_missing(token, seen)
        totals["removed"] += len(removed)
        database.update_source_scan(
            token,
            status="ok",
            name=str(source.get("name") or token),
            error="",
            count=len(products),
            scanned=True,
        )
        source_reports.append(
            {
                "token": token,
                "complete": True,
                "products": len(products),
                "removed": len(removed),
                **changes,
            }
        )

    output = {
        **{key: value for key, value in totals.items() if key != "unique_goods_keys"},
        "unique_products": len(totals["unique_goods_keys"]),
        "sources": source_reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "sources"}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
