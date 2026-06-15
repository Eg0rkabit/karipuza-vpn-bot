#!/usr/bin/env bash
set -Eeuo pipefail

BOT_DIR="/opt/karipuza-bot"
BOT_BRANCH="${BOT_BRANCH:-codex/remnawave-v2}"
BOT_USER="karipuza"
BOT_GROUP="karipuza"
SERVICE_FILE="/etc/systemd/system/karipuza-bot.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if [[ ! -d "${BOT_DIR}/.git" ]]; then
  echo "${BOT_DIR} is not a Git repository." >&2
  exit 1
fi

if ! curl --fail --silent "http://127.0.0.1:3001/health" >/dev/null; then
  echo "Remnawave health check failed." >&2
  exit 1
fi

if ! curl --fail --silent \
  -H "X-Forwarded-For: 127.0.0.1" \
  -H "X-Forwarded-Proto: https" \
  "http://127.0.0.1:3000/" >/dev/null; then
  echo "Remnawave API port is not reachable." >&2
  exit 1
fi

read -rsp "Paste Remnawave API token: " REMNAWAVE_API_TOKEN
echo
read -rp "Paste Default-Squad UUID: " REMNAWAVE_SQUAD_UUID

if [[ -z "${REMNAWAVE_API_TOKEN}" || -z "${REMNAWAVE_SQUAD_UUID}" ]]; then
  echo "API token and squad UUID are required." >&2
  exit 1
fi

if ! [[ "${REMNAWAVE_SQUAD_UUID}" =~ ^[0-9a-fA-F-]{36}$ ]]; then
  echo "The squad UUID has an invalid format." >&2
  exit 1
fi

echo "==> Checking Remnawave credentials"
api_code="$(
  curl --silent --output /tmp/karipuza-remnawave-health.json \
    --write-out '%{http_code}' \
    -H "Authorization: Bearer ${REMNAWAVE_API_TOKEN}" \
    "http://127.0.0.1:3002/api/system/health"
)"
if [[ "${api_code}" != "200" ]]; then
  echo "Remnawave API token check failed with HTTP ${api_code}." >&2
  rm -f /tmp/karipuza-remnawave-health.json
  exit 1
fi

squad_code="$(
  curl --silent --output /tmp/karipuza-remnawave-squad.json \
    --write-out '%{http_code}' \
    -H "Authorization: Bearer ${REMNAWAVE_API_TOKEN}" \
    "http://127.0.0.1:3002/api/internal-squads/${REMNAWAVE_SQUAD_UUID}"
)"
rm -f /tmp/karipuza-remnawave-health.json /tmp/karipuza-remnawave-squad.json
if [[ "${squad_code}" != "200" ]]; then
  echo "Default-Squad UUID check failed with HTTP ${squad_code}." >&2
  exit 1
fi

backup_dir="/root/karipuza-backups/bot-remnawave-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "${backup_dir}"
[[ -f "${BOT_DIR}/.env" ]] && cp -a "${BOT_DIR}/.env" "${backup_dir}/"
[[ -f "${BOT_DIR}/bot.db" ]] && cp -a "${BOT_DIR}/bot.db" "${backup_dir}/"
[[ -d "${BOT_DIR}/data" ]] && cp -a "${BOT_DIR}/data" "${backup_dir}/"

echo "==> Updating bot code"
cd "${BOT_DIR}"
git fetch origin "${BOT_BRANCH}"
git checkout -B "${BOT_BRANCH}" "origin/${BOT_BRANCH}"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

export REMNAWAVE_API_TOKEN REMNAWAVE_SQUAD_UUID
python3 - <<'PY'
import os
from pathlib import Path

path = Path("/opt/karipuza-bot/.env")
updates = {
    "DATABASE_PATH": "/opt/karipuza-bot/data/karipuza.db",
    "REMNAWAVE_URL": "http://127.0.0.1:3002",
    "REMNAWAVE_API_TOKEN": os.environ["REMNAWAVE_API_TOKEN"],
    "REMNAWAVE_SQUAD_UUIDS": os.environ["REMNAWAVE_SQUAD_UUID"],
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
unset REMNAWAVE_API_TOKEN REMNAWAVE_SQUAD_UUID

if ! getent group "${BOT_GROUP}" >/dev/null; then
  groupadd --system "${BOT_GROUP}"
fi
if ! id "${BOT_USER}" >/dev/null 2>&1; then
  useradd --system \
    --gid "${BOT_GROUP}" \
    --home-dir "${BOT_DIR}" \
    --shell /usr/sbin/nologin \
    "${BOT_USER}"
fi

install -d -o "${BOT_USER}" -g "${BOT_GROUP}" -m 0750 "${BOT_DIR}/data"
chown root:"${BOT_GROUP}" "${BOT_DIR}/.env"
chmod 0640 "${BOT_DIR}/.env"

echo "==> Installing Python dependencies"
python3 -m venv "${BOT_DIR}/venv"
"${BOT_DIR}/venv/bin/pip" install --upgrade pip
"${BOT_DIR}/venv/bin/pip" install -r "${BOT_DIR}/requirements.txt"

echo "==> Checking bot code"
"${BOT_DIR}/venv/bin/python" -m compileall -q \
  "${BOT_DIR}/bot.py" "${BOT_DIR}/karipuza_bot"

install -m 0644 "${BOT_DIR}/systemd/karipuza-bot.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable karipuza-bot
systemctl restart karipuza-bot
sleep 4

if ! systemctl is-active --quiet karipuza-bot; then
  echo "Karipuza bot did not start. Recent logs:" >&2
  journalctl -u karipuza-bot -n 100 --no-pager >&2
  exit 1
fi

echo
echo "Karipuza bot is running with Remnawave."
echo "Backup: ${backup_dir}"
systemctl status karipuza-bot --no-pager
