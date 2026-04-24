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

# Number of gunicorn workers. Rule of thumb: 2 * CPU cores + 1
WORKERS="${WEB_WORKERS:-4}"
echo "Starting Gunicorn+Uvicorn on port ${PORT_TO_BIND} with ${WORKERS} workers..."
exec gunicorn config.asgi:application \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WORKERS}" \
  --bind "0.0.0.0:${PORT_TO_BIND}" \
  --timeout 120 \
  --keep-alive 5 \
  --forwarded-allow-ips="*"
