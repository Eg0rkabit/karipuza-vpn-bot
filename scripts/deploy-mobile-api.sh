#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/karipuza-bot"
APP_BRANCH="${APP_BRANCH:-codex/remnawave-v2}"
BOT_SERVICE="karipuza-bot"
WEBAPP_SERVICE="karipuza-webapp"
WEBAPP_PORT="${WEBAPP_PORT:-8080}"
BOT_USERNAME="${BOT_USERNAME:-KaripuzaVPN_bot}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "${APP_DIR} is not a Git repository." >&2
  exit 1
fi

cd "${APP_DIR}"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked files contain local changes. Commit or stash them first." >&2
  exit 1
fi

previous_sha="$(git rev-parse HEAD)"
backup_dir="/root/karipuza-backups/mobile-api-$(date +%Y%m%d-%H%M%S)"
install -d -m 0700 "${backup_dir}"
[[ -f .env ]] && cp -a .env "${backup_dir}/"
[[ -f bot.db ]] && cp -a bot.db "${backup_dir}/"
[[ -d data ]] && cp -a data "${backup_dir}/"
printf '%s\n' "${previous_sha}" >"${backup_dir}/previous-commit.txt"

echo "==> Updating code"
git fetch origin "${APP_BRANCH}"
if [[ "$(git branch --show-current)" != "${APP_BRANCH}" ]]; then
  git switch "${APP_BRANCH}"
fi
git merge --ff-only "origin/${APP_BRANCH}"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

export BOT_USERNAME WEBAPP_PORT
python3 - <<'PY'
import os
from pathlib import Path

path = Path("/opt/karipuza-bot/.env")
updates = {
    "BOT_USERNAME": os.environ["BOT_USERNAME"],
    "MOBILE_AUTH_TTL_SECONDS": "600",
    "MOBILE_SESSION_TTL_DAYS": "180",
    "MOBILE_SUBSCRIPTION_MAX_BYTES": "2097152",
    "MOBILE_SUBSCRIPTION_ALLOWED_HOSTS": "sub.karipuza.ru",
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

chown root:karipuza .env
chmod 0640 .env

echo "==> Checking Python code"
venv/bin/python -m compileall -q bot.py karipuza_bot

echo "==> Restarting bot API"
systemctl restart "${BOT_SERVICE}" "${WEBAPP_SERVICE}"
sleep 4

for service in "${BOT_SERVICE}" "${WEBAPP_SERVICE}"; do
  if ! systemctl is-active --quiet "${service}"; then
    echo "${service} failed to start. Recent logs:" >&2
    journalctl -u "${service}" -n 100 --no-pager >&2
    echo "Backup: ${backup_dir}" >&2
    exit 1
  fi
done

if ! curl --fail --silent "http://127.0.0.1:${WEBAPP_PORT}/health" >/dev/null; then
  echo "Local web API health check failed." >&2
  echo "Backup: ${backup_dir}" >&2
  exit 1
fi

test_code="$(
  curl --silent --output /tmp/karipaza-mobile-api-check.json \
    --write-out '%{http_code}' \
    --request POST \
    --header 'Content-Type: application/json' \
    --data '{"deviceId":"invalid"}' \
    "http://127.0.0.1:${WEBAPP_PORT}/api/mobile/auth/start"
)"
rm -f /tmp/karipaza-mobile-api-check.json
if [[ "${test_code}" != "400" ]]; then
  echo "Mobile API route check failed with HTTP ${test_code}." >&2
  echo "Backup: ${backup_dir}" >&2
  exit 1
fi

echo
echo "Karipaza mobile API is ready."
echo "Backup: ${backup_dir}"
echo "Current commit: $(git rev-parse --short HEAD)"
