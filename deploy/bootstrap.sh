#!/usr/bin/env bash
# Install or update LDXP Scanner from a clean Ubuntu host.
set -euo pipefail

REPOSITORY="${LDXP_REPOSITORY:-https://github.com/84376834111/gpt-.git}"
REF="${LDXP_REF:-main}"
SOURCE_DIR="${LDXP_SOURCE_DIR:-/opt/ldxp-scanner-source}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run with sudo: curl ... | sudo bash" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This bootstrap script supports Ubuntu and Debian hosts with apt-get." >&2
  exit 1
fi

packages=(ca-certificates git python3)
if [[ -n "${LDXP_NGINX_SITE:-}" ]]; then
  packages+=(nginx)
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install --yes --no-install-recommends "${packages[@]}"

if [[ -d "$SOURCE_DIR/.git" ]]; then
  current_origin="$(git -C "$SOURCE_DIR" remote get-url origin 2>/dev/null || true)"
  if [[ "$current_origin" != "$REPOSITORY" ]]; then
    echo "Existing source directory has a different origin: $SOURCE_DIR" >&2
    exit 1
  fi
  if ! git -C "$SOURCE_DIR" diff --quiet || ! git -C "$SOURCE_DIR" diff --cached --quiet; then
    echo "Source checkout contains local changes; refusing to overwrite it." >&2
    exit 1
  fi
  git -C "$SOURCE_DIR" fetch --depth 1 origin "+refs/heads/$REF:refs/remotes/origin/$REF"
  git -C "$SOURCE_DIR" checkout --detach "origin/$REF"
elif [[ -e "$SOURCE_DIR" ]]; then
  echo "Source path exists but is not a Git checkout: $SOURCE_DIR" >&2
  exit 1
else
  git clone --depth 1 --branch "$REF" "$REPOSITORY" "$SOURCE_DIR"
fi

export LDXP_NGINX_SITE LDXP_PUBLIC_URL
bash "$SOURCE_DIR/deploy/install.sh" "$SOURCE_DIR"

systemctl is-active --quiet ldxp-scanner.service
echo "LDXP Scanner is active. Source: $SOURCE_DIR"
