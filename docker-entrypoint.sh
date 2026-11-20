#!/bin/sh
# Container start-up: prepare the data folder, bring the database up to date, reload the demo shop
# (safe to repeat), make sure a staff account exists, then start the web server.
set -e

DATA_DIR="${DATA_DIR:-/data}"
export DATA_DIR
mkdir -p "$DATA_DIR/media"

python manage.py migrate --noinput
python manage.py seed_demo
python manage.py ensure_staff

exec gunicorn powerpick.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --access-logfile -
