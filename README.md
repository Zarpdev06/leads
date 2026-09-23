# B2B Lead Intelligence · Email Outreach · CRM

A production-grade platform for importing messy B2B datasets, cleaning and
de-duplicating them, scoring leads, recommending one of **12 services**, and
running **SMTP-only, quota-limited, fully tracked** email outreach with follow-ups,
a CRM pipeline and analytics.

Built for a software/technology business selling:

AI Development · AI Automation · Business Process Automation · Custom Software
Development · ERP · CRM · Website Development · Web Application Development ·
API Integrations · Business Dashboards · Workflow Automation · Custom SaaS
(+ AI Receptionist, AI Chatbot, Appointment Automation, Client Portal, Document
Automation and more).

---

## Table of contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture) (`docs/ARCHITECTURE.md`)
3. [Quick start (no Docker)](#quick-start-no-docker)
4. [Run with Docker](#run-with-docker)
5. [Configuration (SMTP, limits, AI)](#configuration)
6. [Safety rules that are enforced in code](#safety-rules-that-are-enforced-in-code)
7. [Importing data](#importing-data)
8. [Campaigns, follow-ups and the CRM](#campaigns-follow-ups-and-the-crm)
9. [AI personalization](#ai-personalization)
10. [API reference](#api-reference)
11. [Frontend routes](#frontend-routes)
12. [Tests](#tests)
13. [Project layout](#project-layout)
14. [Implementation phases](#implementation-phases)

---

## What it does

| Area | Capability |
|---|---|
| **Import** | CSV/XLSX from inconsistent sources, streamed in chunks (constant memory), automatic column mapping (exact → alias → fuzzy → value-shape inference), 50-row preview, quality statistics, import all / valid only / cancel |
| **Clean** | Email, phone, website, company-name, person-name, address, state and employee-count normalization; per-row validation errors |
| **Dedupe** | Email (100%), company+website (95%), company+phone (90%), company+address (80%), company+city+state (70%), name-only fuzzy (55%); review screen with merge / keep both / ignore; source history preserved on merge |
| **Missing emails** | Rows without an email are imported and listed under *Missing Email Leads* with enrichment statuses (`NOT_PROCESSED → PROCESSING → FOUND / NOT_FOUND / FAILED`). Addresses are **never guessed** — only publicly listed website addresses are used |
| **Scoring** | Configurable signal weights (+valid email, +website, +contact person, +phone, +category, +location, +accessible website; −invalid email, −unsubscribed, −bounced, −contacted recently) → `HOT / WARM / COLD / UNQUALIFIED` |
| **Service matching** | Admin-configurable industry → service rules, re-ranked by the AI provider when one is configured |
| **Campaigns** | Audience filters (industry, sub-industry, state, city, source, score, required fields), daily limit, send window, follow-up sequence, preview, start/pause/stop |
| **Eligibility gate** | Valid email, not suppressed/unsubscribed/bounced, not blocked, contact-frequency respected, campaign criteria matched, daily capacity available |
| **Sending** | SMTP only, credentials from the environment, **hard daily cap**, row-locked daily counter (concurrency-safe), retry-safe idempotent messages, pacing inside the send window |
| **Tracking** | Sent / delivered / opened / clicked / replied / bounced / unsubscribed, with per-message tokens; opens are only recorded when the tracking pixel is actually fetched |
| **Follow-ups** | Day 0 / +3 / +7 / +14 (configurable), stopping on reply, unsubscribe, bounce, conversion, manual stop or campaign stop |
| **CRM** | `NEW → QUALIFIED → CONTACTED → REPLIED → MEETING → PROPOSAL → NEGOTIATION → WON / LOST / DO_NOT_CONTACT`, kanban, activity timeline, notes |
| **Analytics** | Funnel, rates, per-industry / per-location / per-service performance, AI-vs-template comparison, data quality per source |
| **Governance** | Global suppression list, per-message unsubscribe links, audit log, RBAC (Admin / Manager / Agent / Viewer) |

---

## Architecture

The full architecture document — request lifecycle, database schema, API
conventions, Celery queues/beat schedule, import pipeline, email architecture,
AI provider abstraction, folder structure and Docker topology — lives in
**[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**.

Stack: **Python 3.12 / Django 5 / DRF / PostgreSQL 16 / Celery 5 / Redis 7 /
Pandas + openpyxl / httpx / BeautifulSoup / email-validator** on the backend and
**React 18 + Vite + Tailwind CSS + Recharts** on the frontend.

---

## Quick start (no Docker)

Requires Python 3.11+ and Node 20+.

```bash
git clone <your-fork> leads && cd leads
./scripts/dev_setup.sh          # venv, npm, .env, migrations, admin user, reference data
```

Or manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cp .env.example .env            # fill in SMTP credentials later
cd backend
python manage.py migrate
python manage.py seed_demo --with-demo-leads 1000
python manage.py bootstrap_admin --email admin@example.com --password 'AdminPass123!'
python manage.py runserver 0.0.0.0:8000
```

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

The Vite dev server proxies `/api`, `/admin`, `/media` and `/t` to Django, so
the SPA never needs to know the backend host.

Optional (real asynchronous imports and sending — otherwise Celery runs eagerly
in-process):

```bash
# needs Redis
cd backend && celery -A config worker -Q imports,email,analytics,ai,default -l info
cd backend && celery -A config beat -l info
```

Sign in at `http://localhost:5173` with the administrator you created.

---

## Run with Docker

```bash
cp .env.example .env            # set POSTGRES_PASSWORD (required) and SMTP settings
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
docker compose exec backend python manage.py bootstrap_admin --email admin@example.com
```

| Service | URL | Notes |
|---|---|---|
| nginx | `http://localhost` | edge proxy → frontend + `/api` |
| frontend | internal | built SPA served by nginx |
| backend | internal | gunicorn, 3 workers |
| worker | – | Celery worker (queues `imports,email,analytics,ai,default`) |
| beat | – | Celery beat schedule (defined in `config/celery.py`) |
| db | – | PostgreSQL 16 |
| redis | – | broker, result backend and cache |

---

## Configuration

All operational values come from the environment (`.env`, see `.env.example`).
**SMTP credentials are never stored in the database and never returned by the
API.**

```env
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=outreach@yourcompany.com
EMAIL_HOST_PASSWORD=app-specific-password
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=outreach@yourcompany.com
DEFAULT_REPLY_TO=hello@yourcompany.com
```

Daily sending limits (Settings → Sending):

```
effective_daily_limit = min(marketing limit, SMTP limit, EMAIL_HARD_DAILY_CAP)
```

With the defaults (marketing 90, SMTP 100, hard cap 90) the platform will never
send email #91 on any calendar day. The marketing limit is configurable in the
UI but is clamped to the SMTP limit and to the hard cap; `EMAIL_HARD_DAILY_CAP`
can only be changed in the environment.

AI (optional — everything works offline without it):

```env
AI_PROVIDER=rules        # rules | openai | anthropic | ollama
AI_API_KEY=              # stored encrypted in the DB when entered in the UI
AI_MODEL=
AI_BASE_URL=
```

---

## Safety rules that are enforced in code

1. **Daily quota.** One `DailyEmailUsage` row per day. A slot is reserved with a
   single conditional `UPDATE … WHERE sent_count < limit` (plus
   `SELECT … FOR UPDATE` when the backend supports it), so concurrent workers
   can never overshoot. `tests/test_daily_limit.py` runs 12–20 threads against
   the real code path and asserts the counter stops exactly at the limit.
2. **Eligibility gate.** A lead must have a valid email, must not be
   suppressed/unsubscribed/bounced/blocked, must respect the contact-frequency
   rule, must match the campaign criteria, and capacity must exist.
3. **Retries are idempotent.** `EmailMessage` has a unique
   `(campaign_lead, step_number)` constraint and `send_message()` returns early
   for messages already sent, cancelled or skipped.
4. **No invented data.** The AI receives only verified lead fields; every
   generated email is checked for invented revenue, employee counts, clients,
   awards, ratings, locations, services or technologies, and for numbers that do
   not appear in the lead record. Unsafe output is discarded and replaced.
5. **Unsubscribe and suppression.** Every marketing email carries a one-click
   unsubscribe link and your postal address; unsubscribing cancels queued
   messages, adds the address to the global suppression list and stops all
   follow-ups.
6. **No auto-send on score.** Scoring never triggers outreach; a human starts
   every campaign.

---

## Importing data

1. **Upload** a CSV or XLSX (drag & drop or `Choose file`). Large files are
   analysed by the Celery worker; small ones immediately.
2. **Review the mapping.** Each column shows the detected canonical field, the
   detection method (exact / alias / fuzzy / semantic) and a confidence score.
   Override anything, then save. The mapping is stored with the file.
3. **Preview & stats** for the first 50 rows: total, valid, invalid, with email,
   without email, duplicates, invalid emails, missing company names.
4. **Import** with your choice of: import all / valid rows only / skip invalid
   emails / keep or drop rows without an email / update existing records /
   re-detect duplicates / rescore.

Rows stream in chunks of 1,000 (configurable), so an 82-million-row file uses
the same memory as a 1,000-row file.

CLI equivalent:

```bash
python manage.py import_csv data/public_contacts.csv \
    --source "82 Million USA - Public Contacts File 01" \
    --category "Public Contacts" --chunk-size 1000
```

Generate a messy sample dataset with:

```bash
python scripts/seed_test_data.py --rows 3000 --out data/public_contacts.csv
```

---

## Campaigns, follow-ups and the CRM

* The campaign wizard counts the audience **before** anything is sent and shows
  the estimated number of days given the daily limit.
* `Start` materialises `CampaignLead` rows and schedules one `EmailMessage` per
  lead, spread over the send window **and over days** so no day exceeds the
  limit.
* Follow-ups (`day 0 / +3 / +7 / +14`) are created by the beat task and stop on
  reply, unsubscribe, bounce, conversion, manual stop or campaign stop.
* Every email event updates the lead, the campaign counters and the CRM
  timeline; replies move the pipeline stage automatically.

---

## AI personalization

Providers implement a single `AIProvider` interface (`apps/ai_engine/providers/`):
`rules` (offline, deterministic, default), `openai`, `anthropic`, `ollama`.
Add a provider by subclassing `AIProvider` and registering it — no other code
changes.

The AI only sees verified fields and must return strict JSON
(`subject`, `opening_sentence`, `personalization`, `value_proposition`, `cta`,
`body_html`). Output is validated by `AISafetyValidator`; when it fails — or the
provider is unreachable — the deterministic facts-only copy is used instead.

---

## API reference

All endpoints live under `/api/` and accept a JWT bearer token
(`POST /api/auth/login/`, `POST /api/auth/refresh/`). Lists are paginated
(`?page=&page_size=`) and support server-side filtering, search and ordering.

| Group | Examples |
|---|---|
| Auth | `/api/auth/login/`, `/api/auth/refresh/`, `/api/auth/me/`, `/api/auth/users/`, `/api/auth/change-password/` |
| Imports | `/api/imports/upload/`, `/api/imports/{id}/preview/`, `/api/imports/{id}/process/`, `/api/imports/jobs/{id}/cancel/`, `/api/sources/` |
| Leads | `/api/leads/`, `/api/leads/missing-email/`, `/api/leads/{id}/merge/`, `/api/leads/{id}/duplicates/`, `/api/leads/bulk-add-campaign/`, `/api/leads/export/`, `/api/duplicates/` |
| Companies / Contacts | `/api/companies/`, `/api/contacts/`, `/api/industries/tree/` |
| Campaigns | `/api/campaigns/`, `/api/campaigns/{id}/audience/`, `/start/`, `/pause/`, `/cancel/`, `/dispatch/`, `/stats/`, `/preview_email/`, `/api/campaign-leads/` |
| Email | `/api/email/templates/`, `/api/email/messages/`, `/api/email/send-now/`, `/api/email/smtp-test/`, `/api/email-usage/` |
| Follow-ups | `/api/follow-ups/sequences/`, `/api/follow-ups/upcoming/` |
| CRM | `/api/crm/pipeline/`, `/api/crm/pipeline/{stage}/leads/`, `/api/crm/leads/{id}/move/`, `/api/crm/leads/{id}/timeline/`, `/api/crm/notes/` |
| Analytics | `/api/analytics/`, `/api/dashboard/summary/` |
| Suppression | `/api/suppression/`, `/api/suppression/bulk_add/`, `/api/leads/suppress/` |
| AI | `/api/ai/`, `/api/ai/generate/`, `/api/ai/match-service/`, `/api/ai/providers/{id}/test/` |
| Settings | `/api/settings/`, `/api/settings/update/`, `/api/settings/seed/` |
| Public | `/t/o/{uid}.png` (open pixel), `/t/c/{uid}?u=` (click), `/unsubscribe/{token}/` |

---

## Frontend routes

`/login` · `/dashboard` · `/leads` · `/leads/:id` · `/leads/missing-email` ·
`/companies` · `/contacts` · `/imports` · `/imports/:id` · `/campaigns` ·
`/campaigns/new` · `/campaigns/:id` · `/follow-ups` · `/email` · `/crm` ·
`/analytics` · `/suppression` · `/ai` · `/settings` · `/audit-logs` ·
`/unsubscribe/:token`

Every table is server-side paginated and filtered; nothing renders a full
dataset in the browser.

---

## Tests

```bash
cd backend
pytest                     # 163 tests
pytest tests/test_daily_limit.py -v     # the quota guarantee, incl. concurrency
```

The suite uses SQLite and eager Celery (see `config/settings_test.py`), so it
needs no external services. Covered: normalizers, column mapping (aliases, typos,
value-shape inference), CSV/XLSX imports (including padded headers, invalid
emails, missing emails, duplicates, chunking, idempotent re-import), dedupe
confidences, merging, scoring and thresholds, campaign filtering, dispatch and
lifecycle, follow-ups and stop conditions, SMTP success/failure/bounce/retry,
unsubscribe and suppression, tracking, AI generation + safety fallback, auth,
permissions and the main REST endpoints.

---

## Project layout

```
backend/
  config/          settings, urls, celery, wsgi/asgi
  apps/
    core/          base models, encrypted fields, normalizers, permissions, audit log
    accounts/      custom user (email login), roles, JWT auth
    companies/     Company + Industry taxonomy
    contacts/      Contact
    leads/         Lead, duplicates, scoring, classifier, dedupe, merge, eligibility
    imports/       LeadSource, ImportFile/Job/RowError, mapping engine, streaming readers, pipeline
    campaigns/     Service catalogue, service↔industry rules, Campaign, CampaignLead
    email_engine/  templates, messages, events, follow-ups, daily quota, SMTP sender
    ai_engine/     provider interface + adapters, safety validator, service matching
    crm/           pipeline stages, activities, notes
    analytics/     aggregated metrics + read-side services
    suppression/   global suppression list
    settings/      typed configuration keyed by name with change log
  tests/           163 tests
frontend/
  src/lib          API client (JWT + refresh), formatters, status colours
  src/components   UI primitives, layout, page header
  src/pages        one file per route
nginx/, worker/, scripts/, docs/, docker-compose.yml
```

---

## Implementation phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture document, Docker/Nginx topology, repo layout | ✅ |
| 2 | Django project, settings, Celery app + beat schedule, health checks | ✅ |
| 3 | Database schema and migrations for all 13 apps | ✅ |
| 4 | Data import: chunked CSV/XLSX readers, column-mapping engine, preview, statistics | ✅ |
| 5 | Data normalization, validation and per-row error reporting | ✅ |
| 6 | Dedupe detection (confidence ladder) and merge tooling with provenance | ✅ |
| 7 | Lead model (all statuses, enrichment), scoring, industry classification, missing-email workflow | ✅ |
| 8 | Campaigns, service catalogue, service↔industry rules, audience filtering | ✅ |
| 9 | Email engine: SMTP sender, daily quota, tracking, unsubscribe, suppression, retries | ✅ |
| 10 | AI personalization behind a provider interface + safety validation + service matching | ✅ |
| 11 | Templates, scheduling, follow-up sequences and stop conditions | ✅ |
| 12 | CRM pipeline, activities, notes, timelines | ✅ |
| 13 | Analytics and dashboards | ✅ |
| 14 | Settings, RBAC, audit log, admin dashboard | ✅ |
| 15 | React UI: all screens, server-side pagination, dark mode, responsive | ✅ |
| 16 | Background workers, management commands, seed/demo data, import CLI | ✅ |
| 17 | Tests (163), documentation, end-to-end verification | ✅ |

Each phase ships working code, migrations and tests — no placeholder TODOs in
core functionality.
