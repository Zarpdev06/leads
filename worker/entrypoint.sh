#!/usr/bin/env bash
# Celery entrypoint.
#   MODE=worker (default) -> runs queues imports,email,analytics,ai,default
#   MODE=beat             -> runs celery beat with the schedule defined in config/celery.py
set -euo pipefail

MODE="${MODE:-worker}"
LOG_LEVEL="${LOG_LEVEL:-info}"

case "$MODE" in
  worker)
    exec celery -A config worker \
      --loglevel="$LOG_LEVEL" \
      --queues=imports,email,analytics,ai,default \
      --concurrency="${WORKER_CONCURRENCY:-4}" \
      --max-tasks-per-child=1000 \
      --time-limit="${CELERY_TASK_TIME_LIMIT:-3600}" \
      --soft-time-limit="${CELERY_TASK_SOFT_TIME_LIMIT:-3300}"
    ;;
  beat)
    exec celery -A config beat --loglevel="$LOG_LEVEL" --schedule=/tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
