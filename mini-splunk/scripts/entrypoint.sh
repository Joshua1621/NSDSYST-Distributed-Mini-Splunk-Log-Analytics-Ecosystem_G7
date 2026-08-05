#!/bin/sh
set -e

echo "[ENTRYPOINT] Starting ${SERVICE_NAME:-service}"

exec "$@"