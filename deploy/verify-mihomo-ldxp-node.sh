#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_CONFIG="${1:-/etc/mihomo/config.yaml}"
TEST_PORT=17890
tmp_dir="$(mktemp -d /tmp/mihomo-ldxp-node-test.XXXXXX)"
test_pid=""

cleanup() {
  if [[ -n "$test_pid" ]] && kill -0 "$test_pid" 2>/dev/null; then
    kill "$test_pid" 2>/dev/null || true
    wait "$test_pid" 2>/dev/null || true
  fi
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this verifier as root." >&2
  exit 1
fi

if [[ ! -r "$SOURCE_CONFIG" ]]; then
  echo "Cannot read the Mihomo configuration." >&2
  exit 1
fi

mkdir -p "$tmp_dir/state"
sed \
  -e "s/^mixed-port: 7890$/mixed-port: $TEST_PORT/" \
  -e 's/^    port: 7891$/    port: 17891/' \
  -e 's/DOMAIN-SUFFIX,ldxp.cn,LDXP-DIRECT-FALLBACK/DOMAIN-SUFFIX,ldxp.cn,LDXP-NODES/' \
  "$SOURCE_CONFIG" > "$tmp_dir/config.yaml"
chmod 0600 "$tmp_dir/config.yaml"
chown -R mihomo:mihomo "$tmp_dir"

runuser -u mihomo -- /usr/local/bin/mihomo \
  -d "$tmp_dir/state" -f "$tmp_dir/config.yaml" \
  > "$tmp_dir/mihomo.log" 2>&1 &
test_pid="$!"

for _ in $(seq 1 40); do
  if ! kill -0 "$test_pid" 2>/dev/null; then
    echo "Temporary Mihomo process exited before becoming ready." >&2
    exit 1
  fi
  if ss -lnt | grep -q "127.0.0.1:$TEST_PORT"; then
    break
  fi
  sleep 0.5
done

if ! ss -lnt | grep -q "127.0.0.1:$TEST_PORT"; then
  echo "Temporary Mihomo proxy did not become ready." >&2
  exit 1
fi

# Provider health checks are asynchronous at startup.
sleep 6
http_status="$(
  /usr/bin/curl --silent --show-error --output /dev/null \
    --write-out '%{http_code}' \
    --connect-timeout 10 --max-time 30 \
    --proxy "http://127.0.0.1:$TEST_PORT" \
    https://pay.ldxp.cn/
)"

case "$http_status" in
  2??|3??) ;;
  *)
    echo "Node-only LDXP request failed with HTTP status: $http_status" >&2
    exit 1
    ;;
esac

if ! grep -q 'using LDXP-NODES\[' "$tmp_dir/mihomo.log"; then
  echo "The test request did not use the LDXP node group." >&2
  exit 1
fi

echo "NODE_ONLY_LDXP_HTTP_STATUS=$http_status"
echo "NODE_ROUTE_CONFIRMED=true"
