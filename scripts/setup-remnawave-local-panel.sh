#!/usr/bin/env bash
set -Eeuo pipefail

LOCAL_PORT="${1:-3002}"
NGINX_SITE="/etc/nginx/sites-available/remnawave-local-panel"
NGINX_LINK="/etc/nginx/sites-enabled/remnawave-local-panel"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "==> Installing nginx"
  apt-get update
  apt-get install -y nginx
fi

if ! curl --fail --silent "http://127.0.0.1:3001/health" >/dev/null; then
  echo "Remnawave health check failed on 127.0.0.1:3001." >&2
  echo "Check it with: cd /opt/remnawave && docker compose logs --tail=120" >&2
  exit 1
fi

echo "==> Configuring local Remnawave panel proxy"
cat > "${NGINX_SITE}" <<EOF
server {
    listen 127.0.0.1:${LOCAL_PORT};
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

ln -sfn "${NGINX_SITE}" "${NGINX_LINK}"
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> Checking the panel through nginx"
http_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 10 "http://127.0.0.1:${LOCAL_PORT}/"
)"

if [[ "${http_code}" == "000" || "${http_code}" -ge 500 ]]; then
  echo "Panel proxy check failed with HTTP ${http_code}." >&2
  exit 1
fi

echo
echo "Local Remnawave panel proxy is ready (HTTP ${http_code})."
echo
echo "Open a new PowerShell window and run:"
echo "C:\\Windows\\System32\\OpenSSH\\ssh.exe -N -o ServerAliveInterval=30 -L 3300:127.0.0.1:${LOCAL_PORT} root@176.124.220.50"
echo
echo "Then open http://127.0.0.1:3300"
