#!/bin/sh
set -e

# Dedicated Celery service: runs the worker AND the beat scheduler (-B) so
# periodic tasks (tournament lifecycle, challenge expiry) fire. Run this as a
# SINGLE replica — with -B, multiple replicas would double-schedule beat tasks.
echo "Starting Celery worker + beat..."
exec celery -A config worker \
  --beat \
  --scheduler celery.beat.PersistentScheduler \
  --loglevel=info \
  --concurrency=4 \
  --queues=celery \
  --max-tasks-per-child=200
