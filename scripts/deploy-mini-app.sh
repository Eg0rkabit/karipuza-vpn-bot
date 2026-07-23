#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${1:-app.karipuza.ru}"
APP_DIR="/opt/karipuza-bot"
APP_BRANCH="${APP_BRANCH:-codex/remnawave-v2}"
APP_USER="karipuza"
APP_GROUP="karipuza"
WEBAPP_PORT="${WEBAPP_PORT:-8080}"
WEBAPP_URL="https://${DOMAIN}"
WEBAPP_SERVICE="/etc/systemd/system/karipuza-webapp.service"
BOT_SERVICE="/etc/systemd/system/karipuza-bot.service"
NGINX_SITE="/etc/nginx/sites-available/karipuza-mini-app"
NGINX_LINK="/etc/nginx/sites-enabled/karipuza-mini-app"
WEBROOT="/var/www/karipuza-mini-app"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "${APP_DIR} is not a Git repository." >&2
  exit 1
fi

resolved_ip="$(dig +short "${DOMAIN}" A | tail -n 1 || true)"
server_ip="$(curl -4 --silent --max-time 5 https://ifconfig.me || true)"
if [[ -z "${resolved_ip}" ]]; then
  echo "${DOMAIN} does not resolve yet." >&2
  exit 1
fi
if [[ -n "${server_ip}" && "${resolved_ip}" != "${server_ip}" ]]; then
  echo "Warning: ${DOMAIN} resolves to ${resolved_ip}, server public IP looks like ${server_ip}." >&2
fi

backup_dir="/root/karipuza-backups/mini-app-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "${backup_dir}"
[[ -f "${APP_DIR}/.env" ]] && cp -a "${APP_DIR}/.env" "${backup_dir}/"
[[ -d /etc/nginx ]] && cp -a /etc/nginx "${backup_dir}/nginx"

echo "==> Updating Karipaza Froxy code"
cd "${APP_DIR}"
git fetch origin "${APP_BRANCH}"
git checkout -B "${APP_BRANCH}" "origin/${APP_BRANCH}"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

export WEBAPP_URL WEBAPP_PORT
python3 - <<'PY'
import os
from pathlib import Path

path = Path("/opt/karipuza-bot/.env")
updates = {
    "MINI_APP_URL": os.environ["WEBAPP_URL"],
    "WEBAPP_HOST": "127.0.0.1",
    "WEBAPP_PORT": os.environ["WEBAPP_PORT"],
    "WEBAPP_DEV_AUTH": "false",
    "WEBAPP_AUTH_TTL_SECONDS": "86400",
}

lines = path.read_text(encoding="utf-8").splitlines()
result = []
seen = set()

for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line else ""
    if key in updates:
        result.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        result.append(line)

if result and result[-1]:
    result.append("")
for key, value in updates.items():
    if key not in seen:
        result.append(f"{key}={value}")

path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
PY

if ! getent group "${APP_GROUP}" >/dev/null; then
  groupadd --system "${APP_GROUP}"
fi
if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system \
    --gid "${APP_GROUP}" \
    --home-dir "${APP_DIR}" \
    --shell /usr/sbin/nologin \
    "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 "${APP_DIR}/data"
chown root:"${APP_GROUP}" "${APP_DIR}/.env"
chmod 0640 "${APP_DIR}/.env"

echo "==> Installing Python dependencies"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Checking Python code"
"${APP_DIR}/venv/bin/python" -m compileall -q \
  "${APP_DIR}/bot.py" "${APP_DIR}/karipuza_bot"

install -m 0644 "${APP_DIR}/systemd/karipuza-bot.service" "${BOT_SERVICE}"
install -m 0644 "${APP_DIR}/systemd/karipuza-webapp.service" "${WEBAPP_SERVICE}"
systemctl daemon-reload
systemctl enable karipuza-bot karipuza-webapp
systemctl restart karipuza-bot karipuza-webapp
sleep 4

if ! systemctl is-active --quiet karipuza-webapp; then
  echo "Mini App service did not start. Recent logs:" >&2
  journalctl -u karipuza-webapp -n 100 --no-pager >&2
  exit 1
fi

if ! curl --fail --silent "http://127.0.0.1:${WEBAPP_PORT}/health" >/dev/null; then
  echo "Local Mini App health check failed." >&2
  journalctl -u karipuza-webapp -n 100 --no-pager >&2
  exit 1
fi

echo "==> Installing nginx and certbot"
apt-get update
apt-get install -y nginx certbot curl
install -d -m 0755 "${WEBROOT}"

cat > "${NGINX_SITE}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location ^~ /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF

ln -sfn "${NGINX_SITE}" "${NGINX_LINK}"
nginx -t
systemctl enable nginx
systemctl reload nginx

echo "==> Issuing or refreshing TLS certificate for ${DOMAIN}"
certbot certonly \
  --webroot \
  --webroot-path "${WEBROOT}" \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  --keep-until-expiring \
  -d "${DOMAIN}"

cat > "${NGINX_SITE}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location ^~ /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key ${CERT_DIR}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:${WEBAPP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
EOF

nginx -t
systemctl reload nginx

echo "==> Checking public Mini App endpoint"
http_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}' \
    --resolve "${DOMAIN}:443:127.0.0.1" \
    "https://${DOMAIN}/health"
)"
if [[ "${http_code}" != "200" ]]; then
  echo "Mini App HTTPS check failed with HTTP ${http_code}." >&2
  exit 1
fi

if grep -q '^BOT_TOKEN=' "${APP_DIR}/.env"; then
  bot_token="$(grep '^BOT_TOKEN=' "${APP_DIR}/.env" | tail -n 1 | cut -d= -f2-)"
  if [[ -n "${bot_token}" && "${bot_token}" != "token_from_botfather" ]]; then
    echo "==> Setting Telegram bot menu button"
    curl --silent --show-error --fail \
      "https://api.telegram.org/bot${bot_token}/setChatMenuButton" \
      -H "Content-Type: application/json" \
      -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Karipaza Froxy\",\"web_app\":{\"url\":\"${WEBAPP_URL}\"}}}" \
      >/dev/null || echo "Could not set Telegram menu button automatically." >&2
  fi
fi

echo
echo "Mini App is ready: ${WEBAPP_URL}"
echo "Backup: ${backup_dir}"
echo "BotFather path for full Mini App card: /mybots -> Bot Settings -> Configure Mini App"
systemctl status karipuza-webapp --no-pager
