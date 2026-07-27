from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import GOODS_TYPES, LDXP_BASE_URL, LDXPClient, product_from_api, safe_int


def fetch_state(base_url: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/state"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def scan_source(source: dict[str, Any], proxy: str = "", source_delay: float = 0.0) -> dict[str, Any]:
    token = str(source["token"])
    base_url = str(source.get("base_url") or LDXP_BASE_URL).rstrip("/")
    remote_token = str(source.get("remote_token") or token)
    try:
        if source_delay > 0:
            time.sleep(source_delay)
        client = LDXPClient(base_url=base_url)
        if proxy:
            client.direct_opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            )
        info = client.shop_info(remote_token)
        source_name = str(info.get("nickname") or source.get("name") or remote_token)
        available_types = [
            goods_type
            for goods_type in GOODS_TYPES
            if safe_int(info.get(f"{goods_type}_count"), 0) > 0
        ]
        if not available_types:
            available_types = list(GOODS_TYPES)

        products: dict[str, dict[str, Any]] = {}
        raw_items = 0
        for goods_type in available_types:
            page = 1
            page_size = 100
            while page <= 50:
                payload = client.goods_page(remote_token, goods_type, page, page_size)
                items = payload.get("list") or []
                raw_items += len(items)
                total = safe_int(payload.get("total"), len(items))
                for item in items:
                    product = product_from_api(item, token, source_name, base_url)
                    if product is not None:
                        products[product["goods_key"]] = product
                if not items or page * page_size >= total or len(items) < page_size:
                    break
                page += 1
                time.sleep(0.1)

        # catfk may expose a public item while omitting it from the shop list.
        # Preserve the item used to add the source and fetch it explicitly when needed.
        entry_goods_key = str(source.get("entry_goods_key") or "").strip()
        if entry_goods_key and entry_goods_key not in products:
            item = client.goods_info(entry_goods_key)
            product = product_from_api(item, token, source_name, base_url)
            if product is not None:
                products[product["goods_key"]] = product
        return {
            "token": token,
            "name": source_name,
            "complete": True,
            "raw_items": raw_items,
            "products": list(products.values()),
            "error": "",
        }
    except Exception as exc:
        return {
            "token": token,
            "name": str(source.get("name") or token),
            "complete": False,
            "raw_items": 0,
            "products": [],
            "error": str(exc) or exc.__class__.__name__,
        }


def save_report(path: Path, report: dict[str, Any], lock: threading.Lock) -> None:
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--all-enabled", action="store_true")
    parser.add_argument("--tokens", nargs="*")
    parser.add_argument("--manifest", type=Path, help="server-exported source manifest JSON")
    parser.add_argument("--retry-report", type=Path, help="only scan tokens that failed in a prior report")
    parser.add_argument("--proxy", default="", help="local HTTP(S) proxy, e.g. http://127.0.0.1:7890")
    parser.add_argument("--source-delay", type=float, default=0.0, help="delay before each source request")
    args = parser.parse_args()

    if args.manifest:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("manifest must contain a JSON list of sources")
        sources = [source for source in payload if isinstance(source, dict) and source.get("enabled")]
    else:
        state = fetch_state(args.base_url)
        sources = [source for source in state.get("sources") or [] if source.get("enabled")]
    sources = [source for source in sources if source.get("source_kind", "shop_api") == "shop_api"]
    if args.retry_report:
        prior = json.loads(args.retry_report.read_text(encoding="utf-8"))
        failed_tokens = {
            str(item.get("token"))
            for item in prior.get("sources") or []
            if isinstance(item, dict) and not item.get("complete") and item.get("token")
        }
        sources = [source for source in sources if str(source.get("token")) in failed_tokens]
    if args.tokens:
        requested_tokens = set(args.tokens)
        sources = [source for source in sources if source["token"] in requested_tokens]
    elif not args.manifest and not args.all_enabled:
        # A source currently owned by the server scanner must not be duplicated
        # by a helper node. Only completed failures are eligible for rescue.
        sources = [source for source in sources if source.get("status") == "error"]

    report: dict[str, Any] = {
        "created_at": int(time.time()),
        "server": args.base_url,
        "requested_sources": [source["token"] for source in sources],
        "sources": [],
    }
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(scan_source, source, args.proxy, args.source_delay): source
            for source in sources
        }
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            report["sources"].append(result)
            save_report(args.output, report, lock)
            print(
                json.dumps(
                    {
                        "finished": index,
                        "total": len(sources),
                        "token": result["token"],
                        "complete": result["complete"],
                        "products": len(result["products"]),
                        "error": result["error"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    unique_products = {
        product["goods_key"]: product
        for source in report["sources"]
        if source["complete"]
        for product in source["products"]
    }
    report["summary"] = {
        "requested": len(sources),
        "completed": sum(1 for source in report["sources"] if source["complete"]),
        "failed": sum(1 for source in report["sources"] if not source["complete"]),
        "products_before_global_dedupe": sum(len(source["products"]) for source in report["sources"]),
        "unique_products": len(unique_products),
    }
    save_report(args.output, report, lock)
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
