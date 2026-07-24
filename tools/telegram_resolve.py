from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def link_value(url: str) -> tuple[str, str] | None:
    path = urlparse(url).path.strip("/").split("/")
    if len(path) < 2 or path[-2] not in {"shop", "item"}:
        return None
    return path[-2], path[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    sys.path.insert(0, str(args.app_dir.resolve()))
    from app import Database, DB_PATH, LDXPClient  # noqa: PLC0415

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    direct_tokens: set[str] = set()
    item_keys: set[str] = set()
    for url in payload.get("urls") or []:
        parsed = link_value(url)
        if parsed is None:
            continue
        kind, value = parsed
        if kind == "shop":
            direct_tokens.add(value)
        else:
            item_keys.add(value)

    def resolve_item(goods_key: str) -> tuple[str, str | None, str | None]:
        try:
            item = LDXPClient().goods_info(goods_key)
            token = str((item.get("user") or {}).get("token") or "").strip()
            if not token:
                return goods_key, None, "missing shop token"
            return goods_key, token, None
        except Exception as exc:
            return goods_key, None, str(exc) or exc.__class__.__name__
        finally:
            if args.delay:
                time.sleep(args.delay)

    item_tokens: dict[str, str] = {}
    invalid_items: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(resolve_item, key): key for key in sorted(item_keys)}
        for future in as_completed(futures):
            key, token, error = future.result()
            if token:
                item_tokens[key] = token
            else:
                invalid_items[key] = error or "invalid item"

    candidate_tokens = direct_tokens | set(item_tokens.values())

    def validate_shop(token: str) -> tuple[str, dict[str, Any] | None, str | None]:
        try:
            info = LDXPClient().shop_info(token)
            name = str(info.get("nickname") or token).strip()
            return token, {"token": token, "name": name}, None
        except Exception as exc:
            return token, None, str(exc) or exc.__class__.__name__
        finally:
            if args.delay:
                time.sleep(args.delay)

    valid_shops: dict[str, dict[str, Any]] = {}
    invalid_shops: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(validate_shop, token): token for token in sorted(candidate_tokens)}
        for future in as_completed(futures):
            token, shop, error = future.result()
            if shop:
                valid_shops[token] = shop
            else:
                invalid_shops[token] = error or "invalid shop"

    database = Database(DB_PATH)
    existing = {source["token"] for source in database.list_sources()}
    new_tokens = sorted(set(valid_shops) - existing)
    existing_tokens = sorted(set(valid_shops) & existing)
    applied: list[str] = []
    if args.apply:
        for token in new_tokens:
            shop = valid_shops[token]
            database.upsert_source(
                token,
                shop["name"],
                enabled=True,
                origin="Telegram 公开搜索",
            )
            applied.append(token)

    report = {
        "input_urls": len(payload.get("urls") or []),
        "direct_shop_candidates": len(direct_tokens),
        "item_candidates": len(item_keys),
        "resolved_items": len(item_tokens),
        "invalid_items": invalid_items,
        "candidate_tokens": sorted(candidate_tokens),
        "valid_shops": [valid_shops[token] for token in sorted(valid_shops)],
        "invalid_shops": invalid_shops,
        "already_existing": existing_tokens,
        "new_tokens": new_tokens,
        "applied": applied,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "input_urls": report["input_urls"],
                "resolved_items": report["resolved_items"],
                "valid_shops": len(valid_shops),
                "already_existing": len(existing_tokens),
                "new_tokens": len(new_tokens),
                "applied": len(applied),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
