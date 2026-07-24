#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_DIR=/opt/ldxp-scanner
ENV_FILE=/etc/ldxp-scanner.env
NGINX_SITE="${LDXP_NGINX_SITE:-}"
PUBLIC_URL="${LDXP_PUBLIC_URL:-http://127.0.0.1:8765/}"
SNIPPET="$SOURCE_DIR/deploy/nginx-location.conf"

if [[ ! -f "$SOURCE_DIR/app.py" || ! -f "$SNIPPET" ]]; then
  echo "部署包不完整：$SOURCE_DIR" >&2
  exit 1
fi

sudo install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/static"
sudo install -o root -g root -m 0644 "$SOURCE_DIR/app.py" "$APP_DIR/app.py"
sudo install -o root -g root -m 0644 "$SOURCE_DIR/static/index.html" "$APP_DIR/static/index.html"
sudo install -o root -g root -m 0644 "$SOURCE_DIR/static/style.css" "$APP_DIR/static/style.css"
sudo install -o root -g root -m 0644 "$SOURCE_DIR/static/app.js" "$APP_DIR/static/app.js"
sudo install -o root -g root -m 0644 "$SOURCE_DIR/deploy/ldxp-scanner.service" /etc/systemd/system/ldxp-scanner.service
sudo install -o root -g root -m 0755 "$SOURCE_DIR/tools/ldxp_scanctl.py" /usr/local/bin/ldxp-scanctl

if [[ ! -f "$ENV_FILE" ]]; then
  sudo sh -c "umask 077; printf '%s\n' 'LDXP_HOST=127.0.0.1' 'LDXP_PORT=8765' 'LDXP_DB_PATH=/var/lib/ldxp-scanner/ldxp.db' 'LDXP_AUTO_SCAN_ENABLED=true' 'LDXP_SCAN_INTERVAL=900' 'LDXP_SOURCE_INTERVAL=15' 'LDXP_DISCOVERY_INTERVAL=21600' 'LDXP_PAGE_SIZE=300' 'LDXP_MAX_PAGES=20' 'LDXP_PAGE_DELAY=0.05' 'LDXP_REQUEST_TIMEOUT=12' 'LDXP_FAILOVER_PROXY_URL=http://127.0.0.1:7891' 'LDXP_DIRECT_ATTEMPTS=1' 'LDXP_PROXY_ATTEMPTS=3' 'LDXP_RETRY_DELAY=0.4' 'LDXP_LOCAL_UPLOAD_MAX_ITEMS=6000' > '$ENV_FILE'"
fi
sudo python3 "$SOURCE_DIR/deploy/ensure-admin-key.py"

if [[ -n "$NGINX_SITE" ]]; then
  if [[ ! -f "$NGINX_SITE" ]]; then
    echo "Nginx site not found: $NGINX_SITE" >&2
    exit 1
  fi

  backup="${NGINX_SITE}.bak.$(date +%Y%m%d%H%M%S)"
  sudo cp "$NGINX_SITE" "$backup"
  sudo python3 - "$NGINX_SITE" "$SNIPPET" <<'PY'
from pathlib import Path
import sys

target = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text(encoding="utf-8").rstrip() + "\n\n"
content = target.read_text(encoding="utf-8")
start_marker = "    # BEGIN LDXP_SCANNER"
end_marker = "    # END LDXP_SCANNER"
if start_marker in content and end_marker in content:
    start = content.index(start_marker)
    end = content.index(end_marker, start) + len(end_marker)
    while end < len(content) and content[end] in "\r\n":
        end += 1
    content = content[:start] + snippet + content[end:]
else:
    anchor = "    location / {"
    if anchor not in content:
        raise SystemExit(f"Nginx 配置中找不到插入位置：{anchor}")
    content = content.replace(anchor, snippet + anchor, 1)
target.write_text(content, encoding="utf-8", newline="\n")
PY

  if ! sudo nginx -t; then
    sudo cp "$backup" "$NGINX_SITE"
    echo "Nginx 检查失败，已恢复 $backup" >&2
    exit 1
  fi
fi

sudo systemctl daemon-reload
sudo systemctl enable --now ldxp-scanner.service
sudo systemctl restart ldxp-scanner.service
if [[ -n "$NGINX_SITE" ]]; then
  sudo systemctl reload nginx
fi

echo "DEPLOYED_URL=$PUBLIC_URL"
