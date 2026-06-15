#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${1:-sub.karipuza.ru}"
XRAY_LOCAL_PORT="${XRAY_LOCAL_PORT:-10000}"
NGINX_SITE="/etc/nginx/sites-available/karipuza-remnawave"
NGINX_LINK="/etc/nginx/sites-enabled/karipuza-remnawave"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
MARZBAN_DIR="/opt/marzban"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if [[ "${CONFIRM_CUTOVER:-}" != "YES" ]]; then
  echo "Cutover was not confirmed." >&2
  echo "Run: CONFIRM_CUTOVER=YES bash scripts/cutover-remnawave.sh ${DOMAIN}" >&2
  exit 1
fi

if [[ ! -f "${CERT_DIR}/fullchain.pem" || ! -f "${CERT_DIR}/privkey.pem" ]]; then
  echo "TLS certificate for ${DOMAIN} was not found." >&2
  exit 1
fi

if ! curl --fail --silent "http://127.0.0.1:3001/health" >/dev/null; then
  echo "Remnawave Panel health check failed." >&2
  exit 1
fi

if ! timeout 3 bash -c \
  "exec 3<>/dev/tcp/127.0.0.1/${XRAY_LOCAL_PORT}" 2>/dev/null; then
  echo "The new Xray inbound is not listening on 127.0.0.1:${XRAY_LOCAL_PORT}." >&2
  echo "Do not switch yet. Check the Remnawave node and config profile." >&2
  exit 1
fi

backup_dir="/root/karipuza-backups/cutover-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "${backup_dir}"
cp -a /etc/nginx "${backup_dir}/nginx"

rollback() {
  local exit_code=$?
  echo "Cutover failed. Restoring the previous VPN..." >&2
  rm -f "${NGINX_LINK}"
  nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
  if [[ -f "${MARZBAN_DIR}/docker-compose.yml" ]]; then
    (cd "${MARZBAN_DIR}" && docker compose up -d) || true
  fi
  exit "${exit_code}"
}
trap rollback ERR

cat > "${NGINX_SITE}" <<EOF
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${DOMAIN};

    ssl_certificate ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key ${CERT_DIR}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location = /karipuza {
        proxy_pass http://127.0.0.1:${XRAY_LOCAL_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location = /api/sub {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location ^~ /api/sub/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location / {
        return 404;
    }
}
EOF

ln -sfn "${NGINX_SITE}" "${NGINX_LINK}"
nginx -t

echo "==> Stopping old Marzban"
if [[ -f "${MARZBAN_DIR}/docker-compose.yml" ]]; then
  (cd "${MARZBAN_DIR}" && docker compose stop)
fi

systemctl reload nginx
sleep 2

if ! ss -ltnp | grep -qE ':(443)\b.*nginx'; then
  echo "Nginx did not take port 443." >&2
  false
fi

http_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}' \
    --resolve "${DOMAIN}:443:127.0.0.1" \
    "https://${DOMAIN}/api/sub/not-a-real-user"
)"
if [[ "${http_code}" == "000" || "${http_code}" -ge 500 ]]; then
  echo "Subscription endpoint check failed with HTTP ${http_code}." >&2
  false
fi

trap - ERR

echo
echo "Cutover completed."
echo "Nginx owns port 443 and forwards /karipuza to the Remnawave node."
echo "Subscription endpoint returned HTTP ${http_code} for a test token."
echo "Old Marzban is stopped but its files and backup are preserved."
