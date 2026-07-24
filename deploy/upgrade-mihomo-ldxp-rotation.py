#!/usr/bin/env python3
"""Add a loopback-only rotating-node listener to an existing LDXP config."""

from __future__ import annotations

import grp
import os
from pathlib import Path
import sys


LISTENER = """listeners:
  - name: \"ldxp-rotating-node-in\"
    type: mixed
    listen: 127.0.0.1
    port: 7891
    proxy: LDXP-ROTATE
    users: []

"""

ROTATING_GROUP = """  - name: \"LDXP-ROTATE\"
    type: load-balance
    proxies:
      - DIRECT
    use:
      - ldxp-subscription
    strategy: round-robin
    url: \"https://pay.ldxp.cn/\"
    interval: 60
    timeout: 5000
    lazy: false
    max-failed-times: 1

"""

PROVIDER_FILTER = (
    '    exclude-filter: "(?i)剩余流量|距离下次重置|'
    '套餐到期|traffic|expire|reset"\n'
)

ROTATING_GROUP_WITHOUT_DIRECT = """  - name: \"LDXP-ROTATE\"
    type: load-balance
    use:
"""

ROTATING_GROUP_WITH_DIRECT = """  - name: \"LDXP-ROTATE\"
    type: load-balance
    proxies:
      - DIRECT
    use:
"""


def install_private_config(path: Path, content: str) -> None:
    temporary_path = path.with_name(path.name + ".tmp")
    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o640,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    os.chmod(temporary_path, 0o640)
    os.chown(temporary_path, 0, grp.getgrnam("mihomo").gr_gid)
    os.replace(temporary_path, path)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: upgrade-mihomo-ldxp-rotation.py SOURCE OUTPUT")

    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    output_path = Path(sys.argv[2])
    upgraded = source
    listener_anchor = "ipv6: false\n\n"
    group_anchor = '  - name: "LDXP-DIRECT-FALLBACK"\n'
    provider_anchor = "    health-check:\n      enable: true\n"

    if 'name: "ldxp-rotating-node-in"' not in upgraded:
        if upgraded.count(listener_anchor) != 1:
            raise SystemExit("Mihomo listener insertion point was not found")
        upgraded = upgraded.replace(listener_anchor, listener_anchor + LISTENER, 1)

    if 'name: "LDXP-ROTATE"' not in upgraded:
        if upgraded.count(group_anchor) != 1:
            raise SystemExit("Mihomo group insertion point was not found")
        upgraded = upgraded.replace(group_anchor, ROTATING_GROUP + group_anchor, 1)

    if ROTATING_GROUP_WITHOUT_DIRECT in upgraded:
        upgraded = upgraded.replace(
            ROTATING_GROUP_WITHOUT_DIRECT,
            ROTATING_GROUP_WITH_DIRECT,
            1,
        )

    if "exclude-filter:" not in upgraded:
        if upgraded.count(provider_anchor) != 1:
            raise SystemExit("Mihomo provider filter insertion point was not found")
        upgraded = upgraded.replace(provider_anchor, PROVIDER_FILTER + provider_anchor, 1)

    install_private_config(output_path, upgraded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
