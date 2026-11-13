#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

case "${1:-}" in
    '') docker compose build --pull bot mongo ;;
    --no-build) ;;
    *) echo "Usage: sh deploy.sh [--no-build]" >&2; exit 2 ;;
esac

export HWSUK_SETUP_UID="${HWSUK_SETUP_UID:-$(id -u)}"
export HWSUK_SETUP_GID="${HWSUK_SETUP_GID:-$(id -g)}"
mkdir -p .docker-secrets
chmod 700 .docker-secrets
docker compose run --rm --no-deps prepare
exec docker compose up --no-build -d --force-recreate bot mongo-init
