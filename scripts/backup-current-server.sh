#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/root/karipaza-backups}"
BOT_DIR="${BOT_DIR:-/opt/karipuza-bot}"
REMNAWAVE_DIR="${REMNAWAVE_DIR:-/opt/remnawave}"
REMNANODE_DIR="${REMNANODE_DIR:-/opt/remnanode}"
REMNAWAVE_DB_CONTAINER="${REMNAWAVE_DB_CONTAINER:-remnawave-db}"
LEGACY_MARZBAN_DIR="${LEGACY_MARZBAN_DIR:-/opt/marzban}"
LEGACY_MARZBAN_DATA_DIR="${LEGACY_MARZBAN_DATA_DIR:-/var/lib/marzban}"
PREVIOUS_BACKUP_DIR="${PREVIOUS_BACKUP_DIR:-/root/karipuza-backups}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
ARCHIVE="${BACKUP_ROOT}/karipaza-server-${TIMESTAMP}.tar.gz"
CHECKSUM="${ARCHIVE}.sha256"
MANIFEST="${ARCHIVE}.manifest.txt"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

for command in docker python3 tar sha256sum; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command is missing: ${command}" >&2
    exit 1
  fi
done

if [[ ! -f "${BOT_DIR}/.env" ]]; then
  echo "Bot environment was not found: ${BOT_DIR}/.env" >&2
  exit 1
fi

if [[ ! -f "${REMNAWAVE_DIR}/.env" ]] ||
  [[ ! -f "${REMNAWAVE_DIR}/docker-compose.yml" ]]; then
  echo "Remnawave configuration was not found in ${REMNAWAVE_DIR}." >&2
  exit 1
fi

if [[ "$(docker inspect -f '{{.State.Running}}' "${REMNAWAVE_DB_CONTAINER}" 2>/dev/null)" != "true" ]]; then
  echo "PostgreSQL container is not running: ${REMNAWAVE_DB_CONTAINER}" >&2
  exit 1
fi

install -d -m 0700 "${BACKUP_ROOT}"
WORK_DIR="$(mktemp -d "${BACKUP_ROOT}/.karipaza-backup-${TIMESTAMP}-XXXXXX")"
trap 'rm -rf -- "${WORK_DIR}"' EXIT

copy_if_exists() {
  local source="$1"
  local destination="$2"

  if [[ -e "${source}" ]]; then
    install -d -m 0700 "$(dirname "${WORK_DIR}/${destination}")"
    cp -a "${source}" "${WORK_DIR}/${destination}"
  fi
}

link_directory_if_exists() {
  local source="$1"
  local destination="$2"

  if [[ -d "${source}" ]]; then
    install -d -m 0700 "${WORK_DIR}/${destination}"
    cp -al "${source}/." "${WORK_DIR}/${destination}/"
  fi
}

copy_directory_without_runtime_files() {
  local source="$1"
  local destination="$2"

  install -d -m 0700 "${WORK_DIR}/${destination}"
  tar \
    --exclude='.git' \
    --exclude='.pytest_cache' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='*.db' \
    --exclude='*.db-shm' \
    --exclude='*.db-wal' \
    -C "${source}" -cf - . |
    tar -C "${WORK_DIR}/${destination}" -xf -
}

echo "==> Backing up the bot database"
BOT_DIR="${BOT_DIR}" WORK_DIR="${WORK_DIR}" python3 - <<'PY'
import os
import shlex
import sqlite3
from pathlib import Path

bot_dir = Path(os.environ["BOT_DIR"]).resolve()
work_dir = Path(os.environ["WORK_DIR"]).resolve()
env_path = bot_dir / ".env"

env_values: dict[str, str] = {}
for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    try:
        parsed = shlex.split(value, posix=True)
        env_values[key.strip()] = parsed[0] if parsed else ""
    except ValueError:
        env_values[key.strip()] = value.strip().strip("\"'")

candidates = {
    Path(env_values.get("DATABASE_PATH", "")),
    bot_dir / "data" / "karipuza.db",
    bot_dir / "bot.db",
}

existing = []
for candidate in candidates:
    if not str(candidate):
        continue
    path = candidate if candidate.is_absolute() else bot_dir / candidate
    path = path.resolve()
    if path.is_file():
        existing.append(path)

if not existing:
    raise SystemExit("No bot SQLite database was found.")

destination_root = work_dir / "databases" / "bot"
destination_root.mkdir(parents=True, mode=0o700, exist_ok=True)

for index, source_path in enumerate(sorted(set(existing))):
    destination = destination_root / f"{index:02d}-{source_path.name}"
    with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise SystemExit(f"SQLite integrity check failed for {source_path}")

    metadata = destination.with_suffix(destination.suffix + ".source.txt")
    metadata.write_text(f"{source_path}\n", encoding="utf-8")
PY

echo "==> Dumping the Remnawave PostgreSQL database"
install -d -m 0700 "${WORK_DIR}/databases/remnawave"
docker exec "${REMNAWAVE_DB_CONTAINER}" sh -c '
  export PGPASSWORD="${POSTGRES_PASSWORD:-}"
  exec pg_dumpall \
    --username="${POSTGRES_USER:-postgres}" \
    --clean \
    --if-exists
' \
  >"${WORK_DIR}/databases/remnawave/postgres.sql"

if [[ ! -s "${WORK_DIR}/databases/remnawave/postgres.sql" ]]; then
  echo "Remnawave PostgreSQL dump is empty." >&2
  exit 1
fi

echo "==> Saving application and server configuration"
copy_directory_without_runtime_files "${BOT_DIR}" "opt/karipuza-bot"
copy_if_exists "${REMNAWAVE_DIR}" "opt/remnawave"
copy_if_exists "${REMNANODE_DIR}" "opt/remnanode"
copy_if_exists "${LEGACY_MARZBAN_DIR}" "legacy/opt/marzban"
copy_if_exists "${LEGACY_MARZBAN_DATA_DIR}" "legacy/var/lib/marzban"
link_directory_if_exists \
  "${PREVIOUS_BACKUP_DIR}" "previous-backups/karipuza-backups"
copy_if_exists /etc/nginx etc/nginx
copy_if_exists /etc/letsencrypt etc/letsencrypt
copy_if_exists /etc/systemd/system/karipuza-bot.service \
  etc/systemd/system/karipuza-bot.service
copy_if_exists /etc/systemd/system/karipuza-webapp.service \
  etc/systemd/system/karipuza-webapp.service
copy_if_exists /etc/docker etc/docker
copy_if_exists /etc/sysctl.conf etc/sysctl.conf
copy_if_exists /etc/sysctl.d etc/sysctl.d
copy_if_exists /etc/fstab etc/fstab
copy_if_exists /etc/netplan etc/netplan
copy_if_exists /etc/network etc/network
copy_if_exists /etc/systemd/network etc/systemd/network
copy_if_exists /etc/ssh/sshd_config etc/ssh/sshd_config
copy_if_exists /etc/ssh/sshd_config.d etc/ssh/sshd_config.d
copy_if_exists /etc/ufw etc/ufw
copy_if_exists /root/.ssh root/.ssh

echo "==> Recording service and network state"
install -d -m 0700 "${WORK_DIR}/diagnostics"
docker ps -a --no-trunc \
  >"${WORK_DIR}/diagnostics/docker-ps.txt" 2>&1 || true
docker image ls --digests \
  >"${WORK_DIR}/diagnostics/docker-images.txt" 2>&1 || true
docker version \
  >"${WORK_DIR}/diagnostics/docker-version.txt" 2>&1 || true
ss -lntup >"${WORK_DIR}/diagnostics/listening-ports.txt" 2>&1 || true
ip address show >"${WORK_DIR}/diagnostics/ip-address.txt" 2>&1 || true
ip route show table all >"${WORK_DIR}/diagnostics/ip-routes.txt" 2>&1 || true
ip -6 route show table all >"${WORK_DIR}/diagnostics/ip6-routes.txt" 2>&1 || true
iptables-save >"${WORK_DIR}/diagnostics/iptables.rules" 2>/dev/null || true
nft list ruleset >"${WORK_DIR}/diagnostics/nftables.rules" 2>/dev/null || true
systemctl status karipuza-bot karipuza-webapp nginx --no-pager \
  >"${WORK_DIR}/diagnostics/service-status.txt" 2>&1 || true
systemctl list-unit-files --state=enabled --no-pager \
  >"${WORK_DIR}/diagnostics/enabled-services.txt" 2>&1 || true
dpkg-query -W -f='${binary:Package}\t${Version}\n' \
  >"${WORK_DIR}/diagnostics/installed-packages.txt" 2>&1 || true
crontab -l >"${WORK_DIR}/diagnostics/root-crontab.txt" 2>&1 || true

if [[ -d "${BOT_DIR}/.git" ]]; then
  git -C "${BOT_DIR}" status --short --branch \
    >"${WORK_DIR}/diagnostics/git-status.txt" 2>&1 || true
  git -C "${BOT_DIR}" rev-parse HEAD \
    >"${WORK_DIR}/diagnostics/git-commit.txt" 2>&1 || true
  git -C "${BOT_DIR}" remote -v \
    >"${WORK_DIR}/diagnostics/git-remotes.txt" 2>&1 || true
fi

cat >"${WORK_DIR}/README-RESTORE.txt" <<'EOF'
This archive contains secrets, private TLS keys and complete databases.
Keep it private and do not upload it to public file-sharing services.

Important restore components:
- databases/bot/: consistent SQLite backups for the Telegram bot
- databases/remnawave/postgres.sql: PostgreSQL cluster dump
- opt/karipuza-bot/: application code and .env
- opt/remnawave/: Remnawave Docker Compose configuration and .env
- opt/remnanode/: Remnawave Node configuration
- etc/nginx/ and etc/letsencrypt/: reverse proxy and TLS data
- legacy/: old Marzban files kept as an emergency rollback source
- previous-backups/: earlier deployment and pre-Remnawave archives
- root/.ssh/: SSH configuration and keys; protect this directory carefully
- diagnostics/: service, Docker and network state captured at backup time
EOF

echo "==> Creating the sensitive-data archive"
tar -C "${WORK_DIR}" -czf "${ARCHIVE}" .
chmod 0600 "${ARCHIVE}"
sha256sum "${ARCHIVE}" >"${CHECKSUM}"
tar -tzf "${ARCHIVE}" >"${MANIFEST}"
chmod 0600 "${CHECKSUM}" "${MANIFEST}"

echo "==> Verifying the archive"

for required_path in \
  "./databases/bot/" \
  "./databases/remnawave/postgres.sql" \
  "./opt/karipuza-bot/.env" \
  "./opt/remnawave/.env" \
  "./opt/remnawave/docker-compose.yml"; do
  if ! grep -Fqx "${required_path}" "${MANIFEST}"; then
    echo "Required backup entry is missing: ${required_path}" >&2
    exit 1
  fi
done

archive_size="$(du -h "${ARCHIVE}" | cut -f1)"
archive_hash="$(cut -d' ' -f1 "${CHECKSUM}")"

echo
echo "Backup completed without stopping any services."
echo "Archive: ${ARCHIVE}"
echo "Size: ${archive_size}"
echo "SHA256: ${archive_hash}"
echo
echo "The archive contains passwords and private keys. Keep it secret."
echo "Do not erase the VPS until this archive is downloaded and verified."
