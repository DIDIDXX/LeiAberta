#!/bin/sh
set -eu

backup_python=/opt/backup-venv/bin/python3
backup_script=/app/backup_postgres_to_s3.py

if [ "$(id -u)" -eq 0 ]; then
    exec runuser -u postgres -- "$backup_python" "$backup_script"
fi

exec "$backup_python" "$backup_script"
