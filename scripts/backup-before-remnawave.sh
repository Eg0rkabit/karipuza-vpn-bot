#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/root/karipuza-backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
ARCHIVE="${BACKUP_ROOT}/karipuza-before-remnawave-${TIMESTAMP}.tar.gz"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root."
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_ROOT" "$BACKUP_DIR"

copy_if_exists() {
  local source="$1"
  local destination="$2"

  if [ -e "$source" ]; then
    mkdir -p "$(dirname "${BACKUP_DIR}/${destination}")"
    cp -a "$source" "${BACKUP_DIR}/${destination}"
  fi
}

echo "==> Saving Karipaza Froxy bot"
if [ -d /opt/karipuza-bot ]; then
  mkdir -p "${BACKUP_DIR}/opt/karipuza-bot"
  cp -a \
    /opt/karipuza-bot/.env \
    /opt/karipuza-bot/bot.db \
    /opt/karipuza-bot/*.py \
    /opt/karipuza-bot/requirements.txt \
    /opt/karipuza-bot/systemd \
    "${BACKUP_DIR}/opt/karipuza-bot/" 2>/dev/null || true

  git -C /opt/karipuza-bot status --short --branch \
    >"${BACKUP_DIR}/opt/karipuza-bot/git-status.txt" 2>&1 || true
  git -C /opt/karipuza-bot rev-parse HEAD \
    >"${BACKUP_DIR}/opt/karipuza-bot/git-commit.txt" 2>&1 || true
fi

echo "==> Saving Marzban data"
copy_if_exists /opt/marzban opt/marzban
copy_if_exists /var/lib/marzban var/lib/marzban

echo "==> Saving nginx and certificates"
copy_if_exists /etc/nginx etc/nginx
copy_if_exists /etc/letsencrypt etc/letsencrypt

echo "==> Saving service and network state"
copy_if_exists /etc/systemd/system/karipuza-bot.service \
  etc/systemd/system/karipuza-bot.service

docker ps -a --no-trunc >"${BACKUP_DIR}/docker-ps.txt" 2>&1 || true
docker image ls --digests >"${BACKUP_DIR}/docker-images.txt" 2>&1 || true
ss -lntup >"${BACKUP_DIR}/listening-ports.txt" 2>&1 || true
iptables-save >"${BACKUP_DIR}/iptables.rules" 2>/dev/null || true
ip address show >"${BACKUP_DIR}/ip-address.txt" 2>&1 || true
ip route show table all >"${BACKUP_DIR}/ip-routes.txt" 2>&1 || true
systemctl status karipuza-bot --no-pager \
  >"${BACKUP_DIR}/karipuza-bot-status.txt" 2>&1 || true

echo "==> Creating archive"
tar -C "$BACKUP_ROOT" -czf "$ARCHIVE" "$TIMESTAMP"
chmod 600 "$ARCHIVE"
sha256sum "$ARCHIVE" >"${ARCHIVE}.sha256"

echo "==> Verifying archive"
MANIFEST="${BACKUP_DIR}/archive-manifest.txt"
tar -tzf "$ARCHIVE" >"$MANIFEST"

bot_db_status="missing"
if grep -q '/opt/karipuza-bot/bot.db$' "$MANIFEST"; then
  bot_db_status="saved"
fi

bot_env_status="missing"
if grep -q '/opt/karipuza-bot/.env$' "$MANIFEST"; then
  bot_env_status="saved"
fi

marzban_db_status="missing"
if grep -q '/var/lib/marzban/' "$MANIFEST"; then
  marzban_db_status="saved"
fi

echo
echo "Backup completed."
echo "Archive: $ARCHIVE"
echo "SHA256: $(cut -d' ' -f1 "${ARCHIVE}.sha256")"
echo "Bot database: $bot_db_status"
echo "Bot environment: $bot_env_status"
echo "Marzban data: $marzban_db_status"
echo
echo "No services were stopped and no configuration was changed."
