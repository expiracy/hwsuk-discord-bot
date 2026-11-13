#!/bin/bash
set -Eeuo pipefail
umask 077
if [ ! -s /data/configdb/replica-key ]; then
    openssl rand -base64 756 > /data/configdb/replica-key
fi
if [ ! -s /data/configdb/admin-password ]; then
    openssl rand -hex 32 > /data/configdb/admin-password
fi
chmod 400 /data/configdb/replica-key /data/configdb/admin-password
exec /usr/local/bin/docker-entrypoint.sh "$@"
