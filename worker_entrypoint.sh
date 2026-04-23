#!/bin/sh
set -e

echo "Starting Celery worker..."
exec celery -A config worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=celery \
  --max-tasks-per-child=200
