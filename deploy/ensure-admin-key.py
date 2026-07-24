#!/usr/bin/env python3
"""Create the server-only scanner admin key without printing it."""

from __future__ import annotations

import os
from pathlib import Path
import secrets


ENV_FILE = Path("/etc/ldxp-scanner.env")
SETTING = "LDXP_ADMIN_KEY"


def main() -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    found = False
    output: list[str] = []
    for line in lines:
        if line.startswith(f"{SETTING}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                output.append(line)
            else:
                output.append(f"{SETTING}={secrets.token_hex(32)}")
            found = True
        else:
            output.append(line)
    if not found:
        output.append(f"{SETTING}={secrets.token_hex(32)}")

    temporary = ENV_FILE.with_suffix(".env.tmp")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(ENV_FILE)
    os.chmod(ENV_FILE, 0o600)
    print("ADMIN_KEY_READY=true")


if __name__ == "__main__":
    main()
