#!/usr/bin/env python3
"""Update selected KEY=VALUE entries in an environment file atomically."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: update-env-file.py FILE KEY=VALUE [KEY=VALUE ...]")

    path = Path(sys.argv[1])
    updates: dict[str, str] = {}
    for item in sys.argv[2:]:
        key, separator, value = item.partition("=")
        if not separator or not key or not key.replace("_", "").isalnum():
            raise SystemExit(f"invalid environment assignment: {item}")
        updates[key] = value

    original = path.read_text(encoding="utf-8") if path.exists() else ""
    rendered: list[str] = []
    applied: set[str] = set()
    for line in original.splitlines():
        key, separator, _ = line.partition("=")
        if separator and key in updates:
            rendered.append(f"{key}={updates[key]}")
            applied.add(key)
        else:
            rendered.append(line)
    for key, value in updates.items():
        if key not in applied:
            rendered.append(f"{key}={value}")

    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(rendered).rstrip() + "\n")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.chmod(temporary, 0o600)
    os.chown(temporary, 0, 0)
    os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
