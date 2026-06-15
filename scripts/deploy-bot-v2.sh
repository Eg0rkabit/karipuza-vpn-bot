#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/karipuza-bot"
SERVICE_FILE="/etc/systemd/system/karipuza-bot.service"
SERVICE_USER="karipuza"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

cd "${APP_DIR}"

if [[ ! -f .env ]]; then
  echo "Missing ${APP_DIR}/.env. Copy .env.example and fill it first." >&2
  exit 1
fi

if grep -Eq '^(BOT_TOKEN|ADMIN_IDS)=(|token_from_botfather|123456789,987654321)$' .env; then
  echo "BOT_TOKEN or ADMIN_IDS still contains an example value." >&2
  exit 1
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd \
    --system \
    --home-dir "${APP_DIR}" \
    --shell /usr/sbin/nologin \
    "${SERVICE_USER}"
fi

python3 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/pip install --requirement requirements.txt
venv/bin/python -m compileall -q bot.py karipuza_bot

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${APP_DIR}/data"
chown -R root:root \
  "${APP_DIR}/karipuza_bot" \
  "${APP_DIR}/bot.py" \
  "${APP_DIR}/requirements.txt"
chmod -R a+rX "${APP_DIR}/karipuza_bot"
chmod 0644 "${APP_DIR}/bot.py" "${APP_DIR}/requirements.txt"
chown root:"${SERVICE_USER}" "${APP_DIR}/.env"
chmod 0640 "${APP_DIR}/.env"

install -o root -g root -m 0644 \
  "${APP_DIR}/systemd/karipuza-bot.service" \
  "${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable karipuza-bot.service
systemctl restart karipuza-bot.service
sleep 3

if ! systemctl is-active --quiet karipuza-bot.service; then
  echo "Bot failed to start. Recent logs:" >&2
  journalctl -u karipuza-bot.service -n 80 --no-pager >&2
  exit 1
fi

echo
echo "Karipuza bot v2 is running."
systemctl status karipuza-bot.service --no-pager
