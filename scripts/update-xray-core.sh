#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "ERROR: update stopped at line ${LINENO}." >&2' ERR

MARZBAN_DIR="${MARZBAN_DIR:-/opt/marzban}"
MARZBAN_ENV="${MARZBAN_ENV:-${MARZBAN_DIR}/.env}"
XRAY_DIR="${XRAY_DIR:-/var/lib/marzban/xray-core}"
XRAY_PATH="${XRAY_DIR}/xray"
XRAY_ASSETS_PATH="${XRAY_DIR}"
XRAY_CONFIG="${XRAY_CONFIG:-/var/lib/marzban/xray_config.json}"
GITHUB_REPO="XTLS/Xray-core"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root."
  exit 1
fi

if [ ! -f "$MARZBAN_ENV" ]; then
  echo "Missing Marzban environment file: $MARZBAN_ENV"
  exit 1
fi

if [ ! -f "${MARZBAN_DIR}/docker-compose.yml" ] &&
   [ ! -f "${MARZBAN_DIR}/docker-compose.yaml" ]; then
  echo "Missing docker-compose.yml or docker-compose.yaml in $MARZBAN_DIR"
  exit 1
fi

case "$(uname -m)" in
  x86_64|amd64)
    asset_arch="64"
    ;;
  aarch64|arm64)
    asset_arch="arm64-v8a"
    ;;
  *)
    echo "Unsupported CPU architecture: $(uname -m)"
    exit 1
    ;;
esac

compose() {
  (cd "$MARZBAN_DIR" && docker compose "$@")
}

set_env_value() {
  local key="$1"
  local value="$2"

  if grep -qE "^[#[:space:]]*${key}=" "$MARZBAN_ENV"; then
    sed -i -E "s|^[#[:space:]]*${key}=.*|${key}=${value}|" "$MARZBAN_ENV"
  else
    printf "\n%s=%s\n" "$key" "$value" >>"$MARZBAN_ENV"
  fi
}

get_container_id() {
  local container_id

  container_id="$(compose ps -q marzban 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    container_id="$(compose ps -q 2>/dev/null | head -n1 || true)"
  fi

  printf "%s" "$container_id"
}

wait_for_xray() {
  local container_id

  for _ in $(seq 1 30); do
    container_id="$(get_container_id)"
    if [ -n "$container_id" ] &&
       [ "$(docker inspect -f '{{.State.Running}}' "$container_id" 2>/dev/null || true)" = "true" ] &&
       docker top "$container_id" 2>/dev/null | grep -Fq "${XRAY_PATH} run" &&
       ss -H -ltnp "sport = :443" 2>/dev/null | grep -Fq "xray"; then
      return 0
    fi
    sleep 1
  done

  return 1
}

remove_test_mss_rule() {
  local rule=(
    -p tcp
    --dport 443
    --tcp-flags SYN,RST SYN
    -j TCPMSS
    --set-mss 1160
  )

  while iptables -t mangle -C PREROUTING "${rule[@]}" 2>/dev/null; do
    iptables -t mangle -D PREROUTING "${rule[@]}"
  done
}

rollback() {
  set +e
  echo "Update check failed. Restoring the previous Marzban settings."
  cp -a "$env_backup" "$MARZBAN_ENV"

  if [ "$xray_existed" = "yes" ]; then
    cp -a "$xray_backup" "$XRAY_PATH"
  else
    rm -f "$XRAY_PATH"
  fi

  if [ "$geoip_existed" = "yes" ]; then
    cp -a "$geoip_backup" "${XRAY_DIR}/geoip.dat"
  else
    rm -f "${XRAY_DIR}/geoip.dat"
  fi

  if [ "$geosite_existed" = "yes" ]; then
    cp -a "$geosite_backup" "${XRAY_DIR}/geosite.dat"
  else
    rm -f "${XRAY_DIR}/geosite.dat"
  fi

  compose up -d --force-recreate
  echo "Rollback complete."
  echo "Inspect logs with: cd ${MARZBAN_DIR} && docker compose logs --tail=100"
}

echo "==> Installing download tools"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates

container_id="$(get_container_id)"
if [ -z "$container_id" ]; then
  echo "Marzban container was not found."
  exit 1
fi

if ! docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$container_id" |
  grep -qx "/var/lib/marzban"; then
  echo "The Marzban container does not mount /var/lib/marzban."
  echo "No changes were made."
  exit 1
fi

current_version="$(
  docker exec "$container_id" /usr/local/bin/xray version 2>/dev/null |
    sed -n '1p' || true
)"
echo "Current bundled core: ${current_version:-unknown}"

if [ -n "${XRAY_VERSION:-}" ]; then
  version="$XRAY_VERSION"
else
  echo "==> Resolving the latest official Xray release"
  version="$(
    curl -fsSL \
      -H "Accept: application/vnd.github+json" \
      -H "User-Agent: karipuza-xray-updater" \
      "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" |
      python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])'
  )"
fi

if [ -z "$version" ]; then
  echo "Could not resolve the Xray version."
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

archive="${tmp_dir}/xray.zip"
download_url="https://github.com/${GITHUB_REPO}/releases/download/${version}/Xray-linux-${asset_arch}.zip"

echo "==> Downloading Xray ${version}"
curl -fL --retry 3 --retry-delay 2 "$download_url" -o "$archive"
unzip -tq "$archive" >/dev/null

mkdir -p "$XRAY_DIR"
mkdir -p "$tmp_dir/extracted"
unzip -jo "$archive" xray geoip.dat geosite.dat -d "$tmp_dir/extracted" >/dev/null
install -m 0755 "$tmp_dir/extracted/xray" "${XRAY_PATH}.new"
install -m 0644 "$tmp_dir/extracted/geoip.dat" "${XRAY_DIR}/geoip.dat.new"
install -m 0644 "$tmp_dir/extracted/geosite.dat" "${XRAY_DIR}/geosite.dat.new"

new_version="$("${XRAY_PATH}.new" version | sed -n '1p')"
echo "Downloaded core: $new_version"

if [ -f "$XRAY_CONFIG" ]; then
  XRAY_LOCATION_ASSET="$tmp_dir/extracted" \
    "${XRAY_PATH}.new" run -test -config "$XRAY_CONFIG"
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
env_backup="${MARZBAN_ENV}.karipuza-backup-${timestamp}"
cp -a "$MARZBAN_ENV" "$env_backup"

xray_existed="no"
xray_backup="${XRAY_PATH}.backup-${timestamp}"
if [ -f "$XRAY_PATH" ]; then
  xray_existed="yes"
  cp -a "$XRAY_PATH" "$xray_backup"
fi

geoip_existed="no"
geoip_backup="${XRAY_DIR}/geoip.dat.backup-${timestamp}"
if [ -f "${XRAY_DIR}/geoip.dat" ]; then
  geoip_existed="yes"
  cp -a "${XRAY_DIR}/geoip.dat" "$geoip_backup"
fi

geosite_existed="no"
geosite_backup="${XRAY_DIR}/geosite.dat.backup-${timestamp}"
if [ -f "${XRAY_DIR}/geosite.dat" ]; then
  geosite_existed="yes"
  cp -a "${XRAY_DIR}/geosite.dat" "$geosite_backup"
fi

mv -f "${XRAY_PATH}.new" "$XRAY_PATH"
mv -f "${XRAY_DIR}/geoip.dat.new" "${XRAY_DIR}/geoip.dat"
mv -f "${XRAY_DIR}/geosite.dat.new" "${XRAY_DIR}/geosite.dat"

set_env_value "XRAY_EXECUTABLE_PATH" "$XRAY_PATH"
set_env_value "XRAY_ASSETS_PATH" "$XRAY_ASSETS_PATH"
remove_test_mss_rule

echo "==> Restarting Marzban with the new core"
if ! compose up -d --force-recreate; then
  rollback
  exit 1
fi

if ! wait_for_xray; then
  rollback
  exit 1
fi

container_id="$(get_container_id)"
echo "Running core: $(docker exec "$container_id" "$XRAY_PATH" version | sed -n '1p')"
echo "Port 443: OK"
echo
echo "Xray update completed successfully."
echo "Marzban environment backup: $env_backup"
