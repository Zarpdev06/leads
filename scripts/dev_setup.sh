#!/usr/bin/env bash
# Local development bootstrap (no Docker required).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "==> Python environment"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements-dev.txt

echo "==> Node environment"
(cd frontend && npm install)

echo "==> Environment file"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    created .env - edit your SMTP credentials before sending real email"
fi

echo "==> Database + reference data"
(cd backend && \
  python manage.py migrate --noinput && \
  python manage.py bootstrap_admin --email "${ADMIN_EMAIL:-admin@example.com}" \
      --password "${ADMIN_PASSWORD:-AdminPass123!}" && \
  python manage.py seed_demo)

cat <<'TXT'

Done. Start the stack with two terminals:

  # terminal 1 - API
  cd backend && python manage.py runserver 0.0.0.0:8000

  # terminal 2 - SPA
  cd frontend && npm run dev

  # terminal 3 (optional) - worker for real async imports/sending
  cd backend && celery -A config worker -Q imports,email,analytics,ai,default -l info
  cd backend && celery -A config beat -l info

Open http://localhost:5173 and sign in with the administrator account above.
TXT
