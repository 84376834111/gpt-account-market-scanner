from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reclassify active products from deterministic title rules."
    )
    parser.add_argument("--db", type=Path, required=True, help="SQLite database path")
    parser.add_argument(
        "--app-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Directory containing app.py",
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_dir.resolve()))

    from app import Database  # noqa: PLC0415

    result = Database(args.db).reclassify_products()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
