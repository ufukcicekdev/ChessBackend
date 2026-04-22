#!/bin/sh
set -e

PORT_TO_BIND="${PORT:-8000}"

echo "Running migrations (with retries)..."
i=1
until python manage.py migrate --noinput; do
  if [ "$i" -ge 20 ]; then
    echo "Migrations failed after $i attempts. Exiting."
    exit 1
  fi
  echo "Migrations failed (attempt $i). Retrying in 3s..."
  i=$((i + 1))
  sleep 3
done

echo "Collecting static files..."
python manage.py collectstatic --noinput || true

echo "Starting Daphne on port ${PORT_TO_BIND}..."
exec daphne -b 0.0.0.0 -p "${PORT_TO_BIND}" config.asgi:application
