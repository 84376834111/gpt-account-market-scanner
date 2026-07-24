#!/usr/bin/env bash
set -u

attempts="${1:-16}"
proxy_url="${2:-http://127.0.0.1:7891}"
tmp_dir="$(mktemp -d /tmp/ldxp-proxy-node-probe.XXXXXX)"
trap 'rm -rf "$tmp_dir"' EXIT

successes=0
for index in $(seq 1 "$attempts"); do
  response="$tmp_dir/response-$index"
  metrics="$tmp_dir/metrics-$index"
  if /usr/bin/curl --silent --show-error --http1.1 --compressed \
    --connect-timeout 8 --max-time 15 \
    --proxy "$proxy_url" \
    --header 'Accept: application/json, text/plain, */*' \
    --header 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
    --header 'User-Agent: Mozilla/5.0 (compatible; LDXPPriceScanner/1.0)' \
    --header 'Visitorid: ldxp-scanner-node-probe' \
    --data-binary 'token=CodexBro' \
    --output "$response" \
    --write-out '%{http_code} %{content_type}' \
    https://pay.ldxp.cn/shopApi/Shop/info > "$metrics"; then
    curl_status=0
  else
    curl_status="$?"
  fi

  json_ok=false
  if [[ "$curl_status" -eq 0 ]] && grep -q '"code":1' "$response"; then
    json_ok=true
    successes=$((successes + 1))
  fi
  printf 'ATTEMPT=%s CURL=%s HTTP_AND_TYPE=%s JSON_OK=%s\n' \
    "$index" "$curl_status" "$(cat "$metrics")" "$json_ok"
  sleep 0.2
done

echo "USABLE_NODE_RESPONSES=$successes/$attempts"
