#!/usr/bin/env python3
"""Render a Mihomo config without putting the subscription URL in argv."""

from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit


PLACEHOLDER = "__SUBSCRIPTION_URL_JSON__"


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: render-mihomo-config.py TEMPLATE OUTPUT")

    template_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    subscription_url = sys.stdin.readline().strip()
    parsed = urlsplit(subscription_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("subscription URL must be an absolute HTTPS URL")

    template = template_path.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise SystemExit("subscription placeholder is missing or duplicated")

    rendered = template.replace(PLACEHOLDER, json.dumps(subscription_url))
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o640,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    os.chmod(temporary_path, 0o640)
    os.chown(temporary_path, 0, grp.getgrnam("mihomo").gr_gid)
    os.replace(temporary_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
