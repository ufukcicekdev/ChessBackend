#!/bin/sh
set -e

echo "Starting Celery Beat scheduler..."
exec celery -A config beat --loglevel=info
