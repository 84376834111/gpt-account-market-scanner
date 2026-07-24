from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")


def api_json(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765/")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    direct_tokens: set[str] = set()
    for url in data.get("urls") or []:
        parsed = urlparse(url)
        if (parsed.hostname or "").casefold() != "pay.ldxp.cn":
            continue
        path = parsed.path.strip("/").split("/")
        if len(path) >= 2 and path[-2] == "shop" and TOKEN_RE.fullmatch(path[-1]):
            direct_tokens.add(path[-1])

    # Telegram shortens long snippets with an ellipsis. Remove only candidates
    # that are a strict prefix of a longer token found in the same full scan.
    truncated = {
        token
        for token in direct_tokens
        if any(other != token and other.startswith(token) for other in direct_tokens)
    }
    candidates = sorted(direct_tokens - truncated)

    base = args.base_url.rstrip("/") + "/"
    state = api_json(base + "api/state")
    existing = {source["token"] for source in state.get("sources") or []}
    pending = [token for token in candidates if token not in existing]
    added: list[str] = []
    failed: dict[str, str] = {}
    if not args.dry_run:
        for token in pending:
            try:
                api_json(
                    base + "api/sources",
                    method="POST",
                    payload={"source": f"https://pay.ldxp.cn/shop/{token}"},
                )
                added.append(token)
            except Exception as exc:
                failed[token] = str(exc)

    report = {
        "direct_tokens": sorted(direct_tokens),
        "truncated_skipped": sorted(truncated),
        "candidates": candidates,
        "already_existing": sorted(set(candidates) & existing),
        "pending": pending,
        "added": added,
        "failed": failed,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
