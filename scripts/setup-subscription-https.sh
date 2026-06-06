#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-sub.karipuza.ru}"
PORT="${PORT:-9443}"
MARZBAN_UPSTREAM="${MARZBAN_UPSTREAM:-http://127.0.0.1:8000}"
MARZBAN_ENV="${MARZBAN_ENV:-/opt/marzban/.env}"
BOT_ENV="${BOT_ENV:-/opt/karipuza-bot/.env}"
WEBROOT="${WEBROOT:-/var/www/letsencrypt}"
NGINX_SITE="/etc/nginx/sites-available/karipuza-subscription.conf"
NGINX_LINK="/etc/nginx/sites-enabled/karipuza-subscription.conf"
SUBSCRIPTION_URL="https://${DOMAIN}:${PORT}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root."
  exit 1
fi

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"

  if [ ! -f "$file" ]; then
    echo "Missing env file: $file"
    return 1
  fi

  if grep -qE "^[#[:space:]]*${key}=" "$file"; then
    sed -i -E "s|^[#[:space:]]*${key}=.*|${key}=${value}|" "$file"
  else
    printf "\n%s=%s\n" "$key" "$value" >> "$file"
  fi
}

restart_marzban() {
  if [ -f /opt/marzban/docker-compose.yml ]; then
    (cd /opt/marzban && docker compose up -d --force-recreate)
    return
  fi

  if [ -f /opt/marzban/docker-compose.yaml ]; then
    (cd /opt/marzban && docker compose up -d --force-recreate)
    return
  fi

  if systemctl list-unit-files --no-pager 2>/dev/null | grep -q '^marzban\.service'; then
    systemctl restart marzban
    return
  fi

  if command -v marzban >/dev/null 2>&1; then
    marzban restart
    return
  fi

  echo "WARNING: could not restart Marzban automatically. Restart it manually."
}

echo "==> Installing nginx and certbot"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot curl

echo "==> Preparing ACME webroot"
mkdir -p "$WEBROOT"

cat >"$NGINX_SITE" <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    location ^~ /.well-known/acme-challenge/ {
        root ${WEBROOT};
        default_type "text/plain";
    }

    location / {
        return 404;
    }
}
NGINX

ln -sf "$NGINX_SITE" "$NGINX_LINK"
nginx -t
systemctl enable --now nginx
systemctl reload nginx

if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp >/dev/null || true
  ufw allow "${PORT}/tcp" >/dev/null || true
fi

echo "==> Issuing/refreshing certificate for ${DOMAIN}"
certbot_args=(
  certonly
  --webroot
  -w "$WEBROOT"
  -d "$DOMAIN"
  --agree-tos
  --non-interactive
  --keep-until-expiring
)

if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
  certbot_args+=(--email "$LETSENCRYPT_EMAIL")
else
  certbot_args+=(--register-unsafely-without-email)
fi

certbot "${certbot_args[@]}"

if ss -H -ltn "sport = :${PORT}" | grep -q .; then
  echo "Port ${PORT} is already in use. Choose another PORT before continuing."
  ss -ltnp "sport = :${PORT}" || true
  exit 1
fi

echo "==> Writing nginx subscription proxy"
cat >"$NGINX_SITE" <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    location ^~ /.well-known/acme-challenge/ {
        root ${WEBROOT};
        default_type "text/plain";
    }

    location / {
        return 404;
    }
}

server {
    listen ${PORT} ssl http2;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    client_max_body_size 20m;

    location = / {
        return 404;
    }

    location = /sub {
        proxy_pass ${MARZBAN_UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port ${PORT};
    }

    location ^~ /sub/ {
        proxy_pass ${MARZBAN_UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port ${PORT};
    }
}
NGINX

nginx -t
systemctl reload nginx

echo "==> Adding nginx reload hook for certificate renewal"
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat >/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
systemctl reload nginx
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo "==> Configuring Marzban subscription URL"
set_env_value "$MARZBAN_ENV" "XRAY_SUBSCRIPTION_URL_PREFIX" "$SUBSCRIPTION_URL"
set_env_value "$MARZBAN_ENV" "XRAY_SUBSCRIPTION_PATH" "sub"
restart_marzban

echo "==> Configuring Karipuza bot subscription URL"
if [ -f "$BOT_ENV" ]; then
  set_env_value "$BOT_ENV" "SUBSCRIPTION_URL_PREFIX" "$SUBSCRIPTION_URL"
  sed -i -E "/^[#[:space:]]*SUBSCRIPTION_CHECK_HOST=/d" "$BOT_ENV"
fi

if systemctl list-unit-files --no-pager 2>/dev/null | grep -q '^karipuza-bot\.service'; then
  systemctl restart karipuza-bot
fi

echo "==> Checking HTTPS endpoint"
http_code="000"
for _ in $(seq 1 30); do
  http_code="$(curl -sS -o /dev/null -w "%{http_code}" "${SUBSCRIPTION_URL}/sub/not-a-real-token" || true)"
  if [ "$http_code" != "000" ] && [ "$http_code" != "502" ] && [ "$http_code" != "503" ]; then
    break
  fi
  sleep 2
done

echo "HTTPS check: ${http_code}"
if [ "$http_code" = "000" ] || [ "$http_code" = "502" ] || [ "$http_code" = "503" ]; then
  echo "Subscription endpoint is not ready."
  exit 1
fi

echo
echo "Done."
echo "Subscription URL prefix: ${SUBSCRIPTION_URL}"
echo "Reality on port 443 was not changed."
