#!/usr/bin/env bash
set -Eeuo pipefail

REMNAWAVE_VERSION="${REMNAWAVE_VERSION:-2.7.4}"
REMNAWAVE_DIR="/opt/remnawave"
DOMAIN="${1:-sub.karipuza.ru}"
BACKUP_ROOT="/root/karipuza-backups"
LOCAL_PANEL_PORT="${LOCAL_PANEL_PORT:-3002}"
LOCAL_PANEL_SITE="/etc/nginx/sites-available/remnawave-local-panel"
LOCAL_PANEL_LINK="/etc/nginx/sites-enabled/remnawave-local-panel"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if ! find "${BACKUP_ROOT}" -maxdepth 1 -type f \
  -name 'karipuza-before-remnawave-*.tar.gz' -print -quit 2>/dev/null |
  grep -q .; then
  echo "A pre-Remnawave backup was not found in ${BACKUP_ROOT}." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker with the Compose plugin is required." >&2
  exit 1
fi

if ss -ltn | grep -qE '127\.0\.0\.1:3000\b'; then
  echo "Port 127.0.0.1:3000 is already occupied." >&2
  exit 1
fi

if [[ -e "${REMNAWAVE_DIR}/docker-compose.yml" || -e "${REMNAWAVE_DIR}/.env" ]]; then
  echo "${REMNAWAVE_DIR} already contains Remnawave files. Nothing was overwritten." >&2
  exit 1
fi

echo "==> Preparing swap safety net"
if [[ "$(swapon --show --noheadings | wc -l)" -eq 0 ]]; then
  if [[ ! -e /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 0600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  grep -qE '^/swapfile\s' /etc/fstab ||
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Downloading official Remnawave ${REMNAWAVE_VERSION} files"
tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

curl --fail --location --silent --show-error \
  "https://raw.githubusercontent.com/remnawave/backend/${REMNAWAVE_VERSION}/docker-compose-prod.yml" \
  --output "${tmp_dir}/docker-compose.yml"
curl --fail --location --silent --show-error \
  "https://raw.githubusercontent.com/remnawave/backend/${REMNAWAVE_VERSION}/.env.sample" \
  --output "${tmp_dir}/.env"

install -d -m 0750 "${REMNAWAVE_DIR}"
install -m 0644 "${tmp_dir}/docker-compose.yml" "${REMNAWAVE_DIR}/docker-compose.yml"
install -m 0600 "${tmp_dir}/.env" "${REMNAWAVE_DIR}/.env"

cd "${REMNAWAVE_DIR}"

sed -i \
  "s|image: remnawave/backend:2$|image: remnawave/backend:${REMNAWAVE_VERSION}|" \
  docker-compose.yml

auth_secret="$(openssl rand -hex 64)"
api_secret="$(openssl rand -hex 64)"
metrics_password="$(openssl rand -hex 32)"
webhook_secret="$(openssl rand -hex 32)"
postgres_password="$(openssl rand -hex 24)"

sed -i \
  -e "s|^JWT_AUTH_SECRET=.*|JWT_AUTH_SECRET=${auth_secret}|" \
  -e "s|^JWT_API_TOKENS_SECRET=.*|JWT_API_TOKENS_SECRET=${api_secret}|" \
  -e "s|^METRICS_PASS=.*|METRICS_PASS=${metrics_password}|" \
  -e "s|^WEBHOOK_SECRET_HEADER=.*|WEBHOOK_SECRET_HEADER=${webhook_secret}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${postgres_password}|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=\"postgresql://postgres:${postgres_password}@remnawave-db:5432/postgres\"|" \
  -e "s|^PANEL_DOMAIN=.*|PANEL_DOMAIN=${DOMAIN}|" \
  -e "s|^FRONT_END_DOMAIN=.*|FRONT_END_DOMAIN=*|" \
  -e "s|^SUB_PUBLIC_DOMAIN=.*|SUB_PUBLIC_DOMAIN=${DOMAIN}/api/sub|" \
  .env

chmod 0600 .env

echo "==> Starting Remnawave Panel locally"
docker compose pull
docker compose up -d

echo "==> Waiting for health check"
for _ in $(seq 1 60); do
  if curl --fail --silent "http://127.0.0.1:3001/health" >/dev/null; then
    if ! command -v nginx >/dev/null 2>&1; then
      apt-get update
      apt-get install -y nginx
    fi

    cat > "${LOCAL_PANEL_SITE}" <<EOF
server {
    listen 127.0.0.1:${LOCAL_PANEL_PORT};
    server_name _;

    access_log off;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

    ln -sfn "${LOCAL_PANEL_SITE}" "${LOCAL_PANEL_LINK}"
    nginx -t
    systemctl enable --now nginx
    systemctl reload nginx

    panel_code="$(
      curl --silent --output /dev/null --write-out '%{http_code}' \
        --max-time 10 "http://127.0.0.1:${LOCAL_PANEL_PORT}/"
    )"
    if [[ "${panel_code}" == "000" || "${panel_code}" -ge 500 ]]; then
      echo "Local panel proxy check failed with HTTP ${panel_code}." >&2
      exit 1
    fi

    echo
    echo "Remnawave Panel is healthy."
    echo "Old Marzban and port 443 were not changed."
    echo "Local panel proxy returned HTTP ${panel_code}."
    echo
    echo "Open a new PowerShell window and run:"
    echo "C:\\Windows\\System32\\OpenSSH\\ssh.exe -N -o ServerAliveInterval=30 -L 3300:127.0.0.1:${LOCAL_PANEL_PORT} root@176.124.220.50"
    echo
    echo "Then open http://127.0.0.1:3300"
    trap - EXIT
    cleanup
    exit 0
  fi
  sleep 2
done

echo "Remnawave did not become healthy. Recent logs:" >&2
docker compose logs --tail=120 >&2
exit 1
