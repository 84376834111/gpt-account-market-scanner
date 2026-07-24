from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from telegram_ui import scroll


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = Path(__file__).with_name("telegram_collect_page.ps1")


def collect_page() -> dict:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(COLLECTOR),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        creationflags=0x08000000,
    )
    if completed.returncode:
        raise RuntimeError(
            f"collector failed ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}"
        )
    return json.loads(completed.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--query-label", default="pay.ldxp.cn/shop/")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "telegram_ldxp_links.json",
    )
    args = parser.parse_args()

    urls: set[str] = set()
    fingerprints: list[str] = []
    pages: list[dict] = []
    unchanged = 0
    for page_number in range(1, args.max_pages + 1):
        page = collect_page()
        before = len(urls)
        urls.update(page.get("urls") or [])
        page["page"] = page_number
        page["new_urls"] = len(urls) - before
        pages.append(page)
        print(
            json.dumps(
                {
                    "page": page_number,
                    "items": page["item_count"],
                    "new_urls": page["new_urls"],
                    "unique_urls": len(urls),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        fingerprint = page["fingerprint"]
        unchanged = unchanged + 1 if fingerprints and fingerprint == fingerprints[-1] else 0
        fingerprints.append(fingerprint)
        if unchanged >= 2:
            break
        scroll(250, 570, -4800)
        time.sleep(1.8)

    result = {
        "query": args.query_label,
        "pages": pages,
        "urls": sorted(urls),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"done": True, "pages": len(pages), "urls": len(urls), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
