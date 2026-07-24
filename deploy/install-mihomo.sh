#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${MIHOMO_VERSION:-v1.19.29}"
REPOSITORY="MetaCubeX/mihomo"
CONFIG_DIR="/etc/mihomo"
STATE_DIR="/var/lib/mihomo"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
SERVICE_FILE="/etc/systemd/system/mihomo.service"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

for command in curl python3 gzip sha256sum systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

case "$(uname -m)" in
  x86_64|amd64) release_arch="amd64" ;;
  aarch64|arm64) release_arch="arm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

asset="mihomo-linux-${release_arch}-${VERSION}.gz"
api_url="https://api.github.com/repos/${REPOSITORY}/releases/tags/${VERSION}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

echo "Fetching official release metadata for $VERSION..."
curl --fail --location --silent --show-error \
  --retry 3 --connect-timeout 10 --max-time 60 \
  -H "Accept: application/vnd.github+json" \
  -o "$tmp_dir/release.json" "$api_url"

mapfile -t asset_metadata < <(
  python3 - "$tmp_dir/release.json" "$asset" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    release = json.load(handle)

name = sys.argv[2]
matching = [item for item in release.get("assets", []) if item.get("name") == name]
if len(matching) != 1:
    raise SystemExit(f"Release asset not found: {name}")

item = matching[0]
digest = item.get("digest", "")
if not digest.startswith("sha256:"):
    raise SystemExit(f"Official SHA-256 digest is unavailable for: {name}")

print(item["browser_download_url"])
print(digest.removeprefix("sha256:"))
PY
)

if [[ "${#asset_metadata[@]}" -ne 2 || -z "${asset_metadata[0]}" || -z "${asset_metadata[1]}" ]]; then
  echo "Unable to read the release URL and SHA-256 digest." >&2
  exit 1
fi

download_url="${asset_metadata[0]}"
expected_sha256="${asset_metadata[1]}"
archive="$tmp_dir/$asset"
binary="$tmp_dir/mihomo"

if [[ -n "${MIHOMO_ARCHIVE:-}" ]]; then
  if [[ ! -f "$MIHOMO_ARCHIVE" ]]; then
    echo "Local release archive not found: $MIHOMO_ARCHIVE" >&2
    exit 1
  fi
  echo "Using uploaded release archive: $MIHOMO_ARCHIVE"
  cp "$MIHOMO_ARCHIVE" "$archive"
else
  echo "Downloading $asset..."
  curl --fail --location --silent --show-error \
    --retry 3 --connect-timeout 10 --max-time 300 \
    -o "$archive" "$download_url"
fi

actual_sha256="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$actual_sha256" != "$expected_sha256" ]]; then
  echo "SHA-256 verification failed for $asset" >&2
  echo "Expected: $expected_sha256" >&2
  echo "Actual:   $actual_sha256" >&2
  exit 1
fi
echo "SHA-256 verified: $actual_sha256"
gzip --decompress --stdout "$archive" > "$binary"
chmod 0755 "$binary"
"$binary" -v

if ! getent group mihomo >/dev/null 2>&1; then
  groupadd --system mihomo
fi
if ! id mihomo >/dev/null 2>&1; then
  useradd --system --gid mihomo --home-dir "$STATE_DIR" \
    --shell /usr/sbin/nologin mihomo
fi

install -d -o root -g mihomo -m 0750 "$CONFIG_DIR"
install -d -o mihomo -g mihomo -m 0750 "$STATE_DIR"
install -o root -g root -m 0755 "$binary" /usr/local/bin/mihomo

if [[ ! -e "$CONFIG_FILE" ]]; then
  cat > "$tmp_dir/config.yaml" <<'YAML'
# Safe bootstrap configuration. Replace this file with your Clash YAML or
# configure a proxy provider, then run: sudo systemctl restart mihomo
mixed-port: 7890
allow-lan: false
bind-address: 127.0.0.1
mode: rule
log-level: info
ipv6: false

proxies: []
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - DIRECT
rules:
  - MATCH,PROXY
YAML
  install -o root -g mihomo -m 0640 "$tmp_dir/config.yaml" "$CONFIG_FILE"
fi

cat > "$tmp_dir/mihomo.service" <<'UNIT'
[Unit]
Description=Mihomo (Clash-compatible proxy core)
Documentation=https://wiki.metacubex.one/
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=mihomo
Group=mihomo
UMask=0027
StateDirectory=mihomo
StateDirectoryMode=0750
ExecStartPre=/usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml
ExecStart=/usr/local/bin/mihomo -d /var/lib/mihomo -f /etc/mihomo/config.yaml
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

# Permit an optional TUN configuration without running the daemon as root.
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
NoNewPrivileges=true

# Service hardening. Only the state directory remains writable.
ProtectSystem=strict
ProtectHome=true
ProtectHostname=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
PrivateTmp=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictRealtime=true
RestrictSUIDSGID=true
ReadWritePaths=/var/lib/mihomo

[Install]
WantedBy=multi-user.target
UNIT
install -o root -g root -m 0644 "$tmp_dir/mihomo.service" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable mihomo.service >/dev/null
systemctl restart mihomo.service
systemctl is-active --quiet mihomo.service

echo "Mihomo $VERSION is active."
echo "Configuration: $CONFIG_FILE"
echo "Local mixed proxy: 127.0.0.1:7890"
