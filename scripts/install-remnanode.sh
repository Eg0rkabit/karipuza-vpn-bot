#!/usr/bin/env bash
set -Eeuo pipefail

NODE_IMAGE="${NODE_IMAGE:-remnawave/node:latest}"
NODE_DIR="/opt/remnanode"
NODE_PORT="${1:-2222}"
SECRET_KEY="${2:-}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root." >&2
  exit 1
fi

if ! [[ "${NODE_PORT}" =~ ^[0-9]+$ ]] ||
  (( NODE_PORT < 1024 || NODE_PORT > 65535 )); then
  echo "Invalid node port: ${NODE_PORT}" >&2
  exit 1
fi

if [[ "${#SECRET_KEY}" -lt 100 ]] ||
  [[ "${SECRET_KEY}" =~ [[:space:]] ]]; then
  echo "Pass the SECRET_KEY copied from the Remnawave node form." >&2
  echo "Example: bash scripts/install-remnanode.sh 2222 'YOUR_SECRET_KEY'" >&2
  exit 1
fi

if ! docker network inspect remnawave-network >/dev/null 2>&1; then
  echo "Docker network remnawave-network was not found. Start the panel first." >&2
  exit 1
fi

install -d -m 0750 "${NODE_DIR}"
cd "${NODE_DIR}"

if [[ -f docker-compose.yml ]]; then
  cp -a docker-compose.yml "docker-compose.yml.backup-$(date +%Y%m%d-%H%M%S)"
fi

cat > docker-compose.yml <<EOF
services:
  remnanode:
    image: ${NODE_IMAGE}
    container_name: remnanode
    hostname: remnanode
    restart: always
    ports:
      - "127.0.0.1:10000:10000"
    environment:
      NODE_PORT: "${NODE_PORT}"
      SECRET_KEY: "${SECRET_KEY}"
    networks:
      - remnawave-network
    logging:
      driver: json-file
      options:
        max-size: 25m
        max-file: "4"

networks:
  remnawave-network:
    name: remnawave-network
    external: true
EOF

chmod 0600 docker-compose.yml
docker compose pull
docker compose up -d
sleep 4

if [[ "$(docker inspect -f '{{.State.Running}}' remnanode 2>/dev/null)" != "true" ]]; then
  echo "Remnawave Node did not start." >&2
  docker compose logs --tail=100 >&2
  exit 1
fi

echo
echo "Remnawave Node is running."
echo "Node port: ${NODE_PORT}"
echo "Use this address in the Remnawave node form: remnanode"
echo
echo "The node management port is available only inside the Docker network."
echo "Old Marzban and port 443 were not changed."
