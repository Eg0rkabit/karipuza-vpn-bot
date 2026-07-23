#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/karipuza-bot}"
REMNAWAVE_URL="${REMNAWAVE_URL:-}"
HOST_REMARK="${1:-Karipaza Finland}"
HOST_UUID="${2:-}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if [[ -z "${HOST_REMARK// }" ]]; then
  echo "Host remark cannot be empty." >&2
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

hosts_file="$(mktemp)"
payload_file="$(mktemp)"
response_file="$(mktemp)"
selection_file="$(mktemp)"
trap 'rm -f "${hosts_file}" "${payload_file}" "${response_file}" "${selection_file}"' EXIT

curl --fail --silent --show-error --connect-timeout 5 --max-time 20 \
  --header "Authorization: Bearer ${api_token}" \
  --header "Accept: application/json" \
  "${REMNAWAVE_URL}/api/hosts" \
  --output "${hosts_file}"

export HOST_REMARK HOST_UUID hosts_file payload_file selection_file
"${PYTHON}" - <<'PY'
import json
import os
from pathlib import Path

data = json.loads(Path(os.environ["hosts_file"]).read_text(encoding="utf-8"))
hosts = data["response"]
requested_uuid = os.environ["HOST_UUID"].strip()

if requested_uuid:
    matches = [host for host in hosts if host["uuid"] == requested_uuid]
elif len(hosts) == 1:
    matches = hosts
else:
    matches = [
        host
        for host in hosts
        if "finland" in host["remark"].lower()
        or "финлянд" in host["remark"].lower()
    ]

if len(matches) != 1:
    available = ", ".join(
        f'{host["remark"]} ({host["uuid"]})'
        for host in hosts
    ) or "none"
    raise SystemExit(
        "Cannot select exactly one host. "
        f"Available hosts: {available}. "
        "Pass the required host UUID as the second argument."
    )

selected = matches[0]
payload = {
    "uuid": selected["uuid"],
    "remark": os.environ["HOST_REMARK"],
}
Path(os.environ["payload_file"]).write_text(
    json.dumps(payload, ensure_ascii=False),
    encoding="utf-8",
)
Path(os.environ["selection_file"]).write_text(
    json.dumps(
        {
            "uuid": selected["uuid"],
            "oldRemark": selected["remark"],
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
PY

curl --fail --silent --show-error --connect-timeout 5 --max-time 20 \
  --request PATCH \
  --header "Authorization: Bearer ${api_token}" \
  --header "Accept: application/json" \
  --header "Content-Type: application/json" \
  --data-binary "@${payload_file}" \
  "${REMNAWAVE_URL}/api/hosts" \
  --output "${response_file}"

export response_file
"${PYTHON}" - <<'PY'
import json
import os
from pathlib import Path

selection = json.loads(
    Path(os.environ["selection_file"]).read_text(encoding="utf-8")
)
response = json.loads(
    Path(os.environ["response_file"]).read_text(encoding="utf-8")
)
updated = response["response"]
expected = os.environ["HOST_REMARK"]

if updated["uuid"] != selection["uuid"] or updated["remark"] != expected:
    raise SystemExit("Remnawave returned unexpected host data.")

print(f'Host remark updated: {selection["oldRemark"]} -> {updated["remark"]}')
print("Refresh the subscription in Happ to see the new server name.")
PY
