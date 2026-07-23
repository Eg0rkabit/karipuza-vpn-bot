#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/karipuza-bot}"
REMNAWAVE_URL="${REMNAWAVE_URL:-}"
PROFILE_TITLE="${1:-Karipaza Froxy}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if [[ -z "${PROFILE_TITLE// }" ]]; then
  echo "Profile title cannot be empty." >&2
  exit 1
fi

cd "${APP_DIR}"
PYTHON="${APP_DIR}/venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  echo "Python environment was not found at ${PYTHON}." >&2
  exit 1
fi

api_token="$(
  "${PYTHON}" - <<'PY'
from karipuza_bot.config import settings

print(settings.remnawave_api_token)
PY
)"
if [[ -z "${REMNAWAVE_URL}" ]]; then
  REMNAWAVE_URL="$(
    "${PYTHON}" - <<'PY'
from karipuza_bot.config import settings

print(settings.remnawave_url)
PY
  )"
fi
if [[ -z "${api_token}" ]]; then
  echo "REMNAWAVE_API_TOKEN is not configured in ${APP_DIR}/.env." >&2
  exit 1
fi
if [[ -z "${REMNAWAVE_URL}" ]]; then
  echo "REMNAWAVE_URL is not configured in ${APP_DIR}/.env." >&2
  exit 1
fi

settings_file="$(mktemp)"
payload_file="$(mktemp)"
response_file="$(mktemp)"
trap 'rm -f "${settings_file}" "${payload_file}" "${response_file}"' EXIT

curl --fail --silent --show-error --connect-timeout 5 --max-time 20 \
  --header "Authorization: Bearer ${api_token}" \
  --header "Accept: application/json" \
  "${REMNAWAVE_URL}/api/subscription-settings" \
  --output "${settings_file}"

export PROFILE_TITLE settings_file payload_file
"${PYTHON}" - <<'PY'
import json
import os
from pathlib import Path

settings = json.loads(Path(os.environ["settings_file"]).read_text(encoding="utf-8"))
uuid = settings["response"]["uuid"]
payload = {
    "uuid": uuid,
    "profileTitle": os.environ["PROFILE_TITLE"],
}
Path(os.environ["payload_file"]).write_text(
    json.dumps(payload, ensure_ascii=False),
    encoding="utf-8",
)
PY

curl --fail --silent --show-error --connect-timeout 5 --max-time 20 \
  --request PATCH \
  --header "Authorization: Bearer ${api_token}" \
  --header "Accept: application/json" \
  --header "Content-Type: application/json" \
  --data-binary "@${payload_file}" \
  "${REMNAWAVE_URL}/api/subscription-settings" \
  --output "${response_file}"

export response_file
updated_title="$(
  "${PYTHON}" - <<'PY'
import json
import os
from pathlib import Path

response = json.loads(Path(os.environ["response_file"]).read_text(encoding="utf-8"))
print(response["response"]["profileTitle"])
PY
)"

if [[ "${updated_title}" != "${PROFILE_TITLE}" ]]; then
  echo "Remnawave returned an unexpected profile title: ${updated_title}" >&2
  exit 1
fi

echo "Subscription title updated: ${updated_title}"
echo "Refresh the subscription in Happ to see the new title."
