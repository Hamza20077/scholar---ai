#!/bin/sh
set -eu

python manage.py migrate --noinput
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${WEB_CONCURRENCY:-3}" \
  --timeout 90 \
  --access-logfile - \
  --error-logfile -
