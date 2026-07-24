from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import LDXPClient  # noqa: E402


def api_json(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    item_keys = set()
    for url in payload.get("urls") or []:
        parsed = urlparse(url)
        if (parsed.hostname or "").casefold() != "pay.ldxp.cn":
            continue
        parts = parsed.path.strip("/").split("/")
        if parts[-2:-1] == ["item"]:
            item_keys.add(parts[-1])

    def resolve(goods_key: str) -> tuple[str, str | None, str]:
        try:
            item = LDXPClient().goods_info(goods_key)
            token = str((item.get("user") or {}).get("token") or "").strip()
            return goods_key, token or None, "" if token else "missing shop token"
        except Exception as exc:
            return goods_key, None, str(exc) or exc.__class__.__name__
        finally:
            time.sleep(0.12)

    resolved_items: dict[str, str] = {}
    invalid_items: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(resolve, key): key for key in sorted(item_keys)}
        for index, future in enumerate(as_completed(futures), start=1):
            goods_key, token, error = future.result()
            if token:
                resolved_items[goods_key] = token
            else:
                invalid_items[goods_key] = error
            if index % 20 == 0 or index == len(item_keys):
                print(
                    json.dumps(
                        {"resolved": index, "total": len(item_keys), "shop_tokens": len(set(resolved_items.values()))},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    state = api_json(args.base_url.rstrip("/") + "/api/state")
    existing = {source["token"] for source in state.get("sources") or []}
    candidate_tokens = sorted(set(resolved_items.values()))
    pending = [token for token in candidate_tokens if token not in existing]
    added: list[str] = []
    failed_additions: dict[str, str] = {}
    for token in pending:
        try:
            api_json(
                args.base_url.rstrip("/") + "/api/sources",
                method="POST",
                payload={"source": f"https://pay.ldxp.cn/shop/{token}"},
            )
            added.append(token)
        except Exception as exc:
            failed_additions[token] = str(exc)

    report = {
        "item_candidates": len(item_keys),
        "resolved_items": resolved_items,
        "invalid_items": invalid_items,
        "candidate_tokens": candidate_tokens,
        "already_existing": sorted(set(candidate_tokens) & existing),
        "new_tokens": pending,
        "added": added,
        "failed_additions": failed_additions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "item_candidates": len(item_keys),
                "resolved_items": len(resolved_items),
                "invalid_items": len(invalid_items),
                "shop_tokens": len(candidate_tokens),
                "already_existing": len(report["already_existing"]),
                "added": len(added),
                "failed_additions": len(failed_additions),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
