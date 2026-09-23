# Lead Intelligence, Outreach & CRM Platform — Architecture

Version 1.0 · Status: implemented incrementally (Phase 1 → 17)

This document is the single source of truth for the system. Everything in
`backend/`, `frontend/`, `worker/`, `nginx/` and `docker-compose.yml` is built
to match it.

---

## 0. Design principles

| Principle | Consequence in the code |
|---|---|
| **Real functionality, no mock data** | Every screen reads/writes the Postgres database through DRF. No fixture-backed "demo mode". |
| **Never exceed SMTP capacity** | A single, concurrency-safe, row-locked `DailyEmailUsage` counter is the *only* gate for marketing sends. |
| **Never email blindly** | Eligibility has two implementations that must agree: the per-lead `evaluate_lead_eligibility()` (used by follow-ups and "send now") and the DB-level `eligible_queryset()` / `apply_campaign_filters()` (used to select audiences server-side). Shared decision helpers such as `state_target_values()` keep the two in step — a campaign whose audience filter and eligibility check disagree will select leads and then silently send nothing. |
| **Provider agnostic** | AI is behind an `AIProvider` interface; email is behind SMTP config from env; the fallback AI provider is deterministic and testable with zero API keys. |
| **Idempotent background work** | Celery tasks are safe to retry: unique constraints on (`campaign_lead`, `step_number`) for messages, `select_for_update()` on the daily counter, `ImportJob` status guards. |
| **Streaming, never `read_excel()` on huge files** | CSV is streamed with `pandas.read_csv(..., chunksize=…)`; XLSX is streamed with `openpyxl` read-only + `iter_rows(values_only=True)` in batches. Memory is O(batch), not O(file). |
| **Config in the DB, secrets in env** | SMTP credentials *only* come from environment variables. Tunables (limits, windows, scoring, dedupe rules) live in `SystemSetting` and are editable in Settings → admin UI. |
| **Server-side everything for large data** | All list endpoints paginate and filter in the database; the UI never renders more than one page. |

---

## 1. Complete architecture

```
                       ┌──────────────────────────────────────────────┐
   Browser ───────────▶│  Nginx  (:80/:443)                            │
                       │  /            → static SPA bundle             │
                       │  /api, /admin → proxy_pass backend:8000        │
                       │  /t/…         → proxy_pass backend (tracking)  │
                       └───────────────┬──────────────────────────────┘
                                       │
                       ┌───────────────▼──────────────────────────────┐
                       │  Django 5 + DRF  (gunicorn, stateless)        │
                       │  config/urls.py → apps/*/urls.py              │
                       │  Auth: JWT (simplejwt) + session (admin)      │
                       └───┬───────────────┬───────────────┬──────────┘
                           │               │               │
              ┌────────────▼──┐   ┌────────▼──────┐  ┌─────▼──────────┐
              │ PostgreSQL 16 │   │ Redis 7       │  │ SMTP (yours)   │
              │ OLTP + queue  │   │ Celery broker │  │ TLS/SSL, quota │
              │ result backend│   │ cache, locks  │  └────────────────┘
              └───────────────┘   └───────┬───────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
┌───────▼────────┐              ┌─────────▼─────────┐            ┌──────────▼─────────┐
│ worker (imports│              │ worker (outreach) │            │ beat (scheduler)   │
│  & analytics)  │              │ email/follow-ups  │            │ crontab schedule   │
│ queue: imports │              │ queue: email      │            │                    │
│         ai     │              │ queue: default    │            │                    │
└────────────────┘              └───────────────────┘            └────────────────────┘
```

### Request lifecycle for a marketing email (the critical path)

1. **Campaign launch** (`POST /api/campaigns/{id}/start/`) selects eligible leads with one
   filtered queryset and creates `CampaignLead` rows. No email rows yet.
2. **Dispatch** (`campaigns.tasks.dispatch_campaign`) creates `EmailMessage` rows with
   `scheduled_at` spread across the configured send window and across *days* so that no day
   exceeds `min(campaign.daily_limit, remaining global capacity)`.
3. **Scheduler** (`email_engine.tasks.send_due_emails`, beat every minute) picks
   `status=QUEUED AND scheduled_at <= now` limited by the free capacity for today.
4. **Send** (`email_engine.tasks.send_email_message`) — inside `transaction.atomic()`:
   `DailyEmailQuota.reserve()` (row lock) → SMTP send → status `SENT` → `EmailEvent('SENT')`
   → `CRM` activity → counter `sent_count += 1`. On SMTP failure: status `FAILED`, retry with
   exponential backoff (max 3 attempts), permanent failure creates a suppression on hard bounce.
5. **Tracking** pixel `/t/o/{uid}.png` and click redirect `/t/c/{uid}` write `EmailEvent` rows.
   Reply/bounce detection via optional IMAP poller or inbound webhook.
6. **Follow-ups** (`email_engine.tasks.process_follow_ups`, beat hourly) create the next
   `EmailMessage` for a `CampaignLead` if the elapsed days match the sequence *and* no stop
   condition fired (reply / unsubscribe / bounce / converted / campaign stopped / lead blocked).

### Multi-tenancy & safety notes
* Single-tenant per deployment (your own business), with role-based access
  (`ADMIN`, `MANAGER`, `AGENT`, `VIEWER`) enforced in DRF permission classes.
* Writes that matter (import, merge, suppress, campaign start, settings change, AI generation)
  write an `AuditLog` row.
* Legal compliance: every marketing email carries a real one-click unsubscribe link + physical
  address placeholder, suppression is global and checked *before* the daily quota is consumed.

---

## 2. Database schema (see `docs/DATABASE_SCHEMA.md` for the field-level version)

```
accounts.User ──────────────────────────────┐ (actor on everything)
        │                                   │
        ▼                                   ▼
  imports.LeadSource ──< imports.ImportFile ──< imports.ImportJob ──< imports.ImportRowError
        │                                            │
        │  source_file                               │  created/updated rows
        ▼                                            ▼
  companies.Company ──< contacts.Contact ──< leads.Lead ──< leads.LeadDuplicate
        │                                        │  ▲
        │ industry/sub_industry                  │  │ duplicate_of / merged_into
        ▼                                        │  │
  companies.Industry (self-referencing tree)     │  │
                                                 │  │
  campaigns.Service ──< campaigns.ServiceIndustryMapping >── Industry
        ▲                                        │
        │ recommended_service                    │
  campaigns.Campaign ──< campaigns.CampaignLead >┘
        │  template, follow_up_sequence
        ▼
  email_engine.EmailTemplate        email_engine.FollowUpSequence ──< FollowUpStep
        │                                        │
        ▼                                        ▼
  email_engine.EmailMessage ──< email_engine.EmailEvent
        │  lead, campaign, campaign_lead, unsubscribe_token (unique)
        ▼
  suppression.Suppression (unique email_normalized) ──< SuppressionLog
  email_engine.DailyEmailUsage (unique date)   ← the hard quota gate

  crm.CRMActivity / crm.LeadNote ──< Lead
  ai_engine.AIRecommendation ──< Lead ──> Service
  analytics.DailyMetric, analytics.CampaignDailyStat, analytics.ImportDailyStat
  settings.SystemSetting (key/value JSON, secret-aware)
  core.AuditLog (polymorphic: entity_type + entity_id)
```

Canonical lead row: `apps/leads/models.py::Lead` mirrors the canonical schema you specified
one-for-one (`company_id, contact_id, source_id, source_file, source_row_number, company_name,
industry, sub_industry, contact_name, first_name, last_name, job_title, email,
email_normalized, email_status, phone, phone_normalized, phone_type, website,
website_normalized, street_address, city, state, zip_code, country, employee_count,
lead_status, lead_score, source, source_category, source_city, created_at, updated_at`) plus the
operational fields needed later (CRM stage, follow-up bookkeeping, dedupe pointers, enrichment
state, AI cache).

### Indexes (created in migrations)
`Lead`: `email_normalized`, `website_normalized`, `phone_normalized`, `company_name`,
`industry`, `sub_industry`, `city`, `state`, `lead_status`, `lead_score`, `crm_stage`,
`source`, `created_at`, composite `(state, city)`, composite `(industry, lead_score)`,
composite `(lead_status, email_status)`, trigram-capable `company_name` (GIN on Postgres).
`EmailMessage`: `scheduled_at`, `status`, `campaign`, `lead`, `unsubscribe_token` (unique),
`unique (campaign_lead, step_number)` — the idempotency guard.
`Company`: `name_normalized`, `website_normalized`, `domain`, `city`, `state`, `industry`.
`Contact`: `email_normalized`, `last_name`, `company`.
`Suppression`: unique `email_normalized`, index on `reason`, `is_active`.
`DailyEmailUsage`: unique `date`.

---

## 3. API architecture

* Style: REST, JSON, `/api/…` prefix, versioned namespace ready (`/api/v1/` alias).
* Auth: `Authorization: Bearer <JWT>` (access 60 min, refresh 7 days, rotation on). Session
  auth stays enabled for `/admin/` and for the browser dev tools.
* Conventions: `GET` list (paginated `{count, next, previous, results}`), `POST` create,
  `PATCH` partial update, `DELETE` (soft where history matters). Bulk actions are explicit
  sub-routes (`POST /api/leads/bulk-add-campaign/`) taking `{ids: [...], ...}`.
* Filtering: `django-filter` `FilterSet` classes on every list endpoint (industry,
  sub-industry, state, city, has_email, has_website, min/max score, campaign, email_status,
  crm_stage, source, imported date range) + `search` (business, contact, email, phone,
  website, city, state, industry) via a single `GlobalSearchView`.
* Throttling: DRF scoped rates — `anon` 60/h, `user` 5000/h, `ai` 60/h, `import` 60/h.
* Errors: uniform `{detail | field_errors, code}` envelope via `core.exceptions.handler`.
* Public (unauthenticated, token-based) endpoints for tracking & unsubscribe:
  `/t/o/{uid}.png`, `/t/c/{uid}`, `/api/unsubscribe/{token}/` (GET + POST), `/api/t/health/`.

Full endpoint inventory: `docs/API.md`.

---

## 4. Frontend route structure

```
/                       Dashboard (KPI cards, capacity meter, charts)
/login                  Login
/leads                  Lead Explorer (server-side filters, bulk actions, export)
/leads/:id              Lead Detail (business, contact, AI rec, email history, CRM, notes, timeline)
/companies              Companies
/contacts               Contacts
/imports                Import console (drag & drop, jobs list)
/imports/:id            Mapping + preview + import (wizard)
/campaigns              Campaign list
/campaigns/new          Campaign wizard (5 steps)
/campaigns/:id          Campaign detail (audience, queue, stats, controls)
/email                  Email messages (status, retries, preview)
/follow-ups             Follow-up sequences + queue
/crm                    Pipeline board (drag between stages) + activities
/analytics              Analytics (charts, funnels, leaderboards)
/suppression            Suppression list
/templates              Email templates
/ai                     AI console (providers, generate, review safety)
/settings               Settings (SMTP status, limits, scoring, dedupe, AI, sender identity)
/audit-logs             Audit log
/unsubscribe/:token     Public unsubscribe page
```

Layout: `AppLayout` (collapsible sidebar + topbar + command palette-ish global search) and
`AuthLayout`. Data fetching: thin `apiFetch` wrapper + `useApi`/`useMutation` hooks, React
Router v6, Tailwind, Recharts, lucide icons, dark/light theme persisted in `localStorage`.

---

## 5. Celery architecture

Queues (separate workers so a 40M-row import can never starve the email scheduler):

| Queue | Tasks | Concurrency |
|---|---|---|
| `imports` | `imports.tasks.run_import_job`, `…finalize_import_job`, `leads.tasks.rebuild_duplicates`, `leads.tasks.rescore_leads`, `leads.tasks.enrich_lead_website` | 2 (memory-heavy) |
| `ai` | `ai_engine.tasks.generate_lead_recommendation`, `…generate_campaign_copy` | 4 |
| `email` | `email_engine.tasks.send_due_emails`, `send_email_message`, `process_follow_ups`, `dispatch_campaign` | 4 |
| `analytics` | `analytics.tasks.build_daily_metrics`, `email_engine.tasks.poll_mailbox` | 2 |
| `default` | misc, maintenance, `purge_old_files` | 2 |

Beat schedule: `send_due_emails` every 60s · `process_follow_ups` every 15 min ·
`release_stuck_messages` every 10 min · `build_daily_metrics` at 00:10 ·
`poll_mailbox` every 15 min (only if IMAP configured) · `purge_old_files` daily.

Idempotency: every task takes a primary key (never a queryset), re-reads state, and short
circuits if the work is already done (`EmailMessage.status in (SENT, ...)` → return). Retries
use `autoretry_for` + `retry_backoff`, and `EmailMessage.attempt_count` caps retries.
Late acks + `acks_late=True, worker_prefetch_multiplier=1` on the email queue.

---

## 6. Import architecture

```
Upload (multipart) ─▶ ImportFile (stored, checksummed) ─▶ detect headers ─▶ auto-map columns
        │                                                                        │
        │                                                             STEP 6: user reviews
        ▼                                                                        ▼
  XLSX: sheet discovery (openpyxl read_only)                    PATCH mapping (manual override)
  CSV: sniff delimiter/encoding/chunk                                            │
        │                                                                        ▼
        └────────────▶ POST /process/ ─▶ ImportJob (PENDING) ─▶ Celery (queue:imports)
                                              │
                    ┌─────────────────────────┴──────────────────────────┐
                    │  streaming reader (chunk = 1000 rows)              │
                    │  per row: normalize → validate email → score       │
                    │           → dedupe (blocking keys) → bulk upsert   │
                    │  every chunk: job.processed_rows += n (own txn)    │
                    └─────────────────────────┬──────────────────────────┘
                                              ▼
                             ImportJob COMPLETED + source stats recomputed
```

* **Column mapping engine** (`apps/imports/mapping.py`): 5 passes — exact → normalized
  (lowercase, punctuation-stripped) → alias dictionary (~40 aliases per popular field) →
  fuzzy (`difflib` token-set ratio ≥ 0.82) → semantic (token overlap + value-shape sniffing:
  a column whose values look like emails *is* an email column regardless of its name).
  Every suggestion carries `{field, confidence, method}` so the UI can show low-confidence
  mappings in amber for human confirmation.
* **Never loads the whole file**: CSV via `pandas.read_csv(chunksize=1000, dtype=str)`;
  XLSX via `openpyxl.load_workbook(read_only=True, data_only=True)` + `iter_rows`.
  Upload size is capped (`IMPORT_MAX_FILE_MB`, default 500) and validated by extension,
  MIME sniff and magic bytes.
* **Row-level errors** are persisted (`ImportRowError`, capped per job) instead of aborting.

---

## 7. Email architecture

```
CampaignLead ──dispatch──▶ EmailMessage(QUEUED, scheduled_at) ──▶ send_due_emails (beat)
                                                                        │
                                       ┌────────────────────────────────┴─────────────┐
                                       ▼                                              ▼
                         DailyEmailQuota.reserve()                       suppression / eligibility
                         SELECT … FOR UPDATE on DailyEmailUsage           (re-check, cheap, before send)
                         if sent_count >= effective_limit → SKIP
                                       │
                                       ▼
                            SMTP send (django.core.mail backends, keep-alive connection reuse)
                                       │
                  ┌────────────────────┼────────────────────┐
                  ▼                    ▼                    ▼
              SENT                 FAILED (retry)      hard bounce → Suppression(BOUNCED)
              +EmailEvent          attempt_count<3     + lead.email_status = BOUNCED
```

**Quota maths.** `effective_daily_limit = min(marketing_limit, smtp_daily_limit, HARD_CAP)`.
`HARD_CAP` (`EMAIL_HARD_DAILY_CAP`, default 90) can never be raised from the UI — it is an
environment-level guard. `DailyEmailUsage` has columns `(date, sent_count, failed_count,
limit, smtp_limit)`; reservation is a `SELECT … FOR UPDATE` on the row for today inside the
same transaction as the send, so N workers can never overshoot. Transactional emails
(password resets, etc.) use a separate flag and do **not** consume the marketing quota.

**Throttling shape.** Emails are spread over the send window (`SEND_WINDOW_START` 09:30 →
`SEND_WINDOW_END` 17:30) with jitter, and every send sleeps `EMAIL_MIN_SECONDS_BETWEEN_SENDS`
(configurable, default 20s) to stay inside typical SMTP rate limits. The system never opens
parallel SMTP connections to dodge provider limits; the goal is *compliance*, not evasion.

**Tracking.** Open: 1×1 transparent PNG (`/t/o/{uid}.png`) — only recorded when the pixel is
actually fetched, so "opened" is never claimed without evidence (and it stays null when the
recipient blocks remote images). Click: signed redirect `/t/c/{uid}?u=<url>`. Reply/bounce:
optional IMAP poller or inbound webhook → `EmailEvent` + `CampaignLead.status`. Every
marketing email contains `List-Unsubscribe` / `List-Unsubscribe-Post` headers and a visible
unsubscribe link with a per-message token.

---

## 8. AI architecture

```
            ┌──────────────────────── AIProvider (abstract) ────────────────────────┐
            │ generate_email(context: AIEmailContext) -> AIEmailResult              │
            │ recommend_service(context) -> AIServiceResult                         │
            │ test_connection() -> bool                                             │
            └───▲───────────────▲───────────────▲────────────────▲─────────────────┘
                │               │               │                │
        OpenAIAdapter    AnthropicAdapter   OllamaAdapter   RuleBasedProvider (offline,
        (httpx)          (httpx)            (httpx/local)   deterministic, no key, used in
                                                             tests + when no key configured)
```

* Selection is by `AIProviderConfig` / `SystemSetting` (`ai.provider`, `ai.model`); adding a
  provider = one subclass + an entry in the registry. API keys are stored encrypted
  (`core.fields.EncryptedCharField`, Fernet, key from `ENCRYPTION_KEY` / derived from
  `SECRET_KEY`) and are **never** returned by the API.
* **Grounding & safety**: the prompt is assembled from verified lead fields only; unknown
  fields are sent as `"unknown"` with an explicit instruction to omit them. After generation,
  `AISafetyValidator` rejects/rewrites output containing fabricated facts (revenue figures,
  employee counts, awards, ratings, invented locations/services, numbers not present in the
  input context, unverifiable superlatives). Failed validation → fall back to the templated,
  facts-only version and record the failure.
* **Caching**: `AIRecommendation` rows are keyed by (lead, provider, model, template, context
  hash) so a re-run or a retry never re-bills or changes an approved email.
* **Service matching** is a rules + AI hybrid: `ServiceIndustryMapping` (configurable in
  admin) scores candidate services by industry/sub-industry/keyword; the AI re-ranks and
  writes the rationale; the rules always win on hard API-safety failure.

---

## 9. Folder structure

```
project/
├── backend/
│   ├── manage.py
│   ├── config/                 # settings package, urls, celery, asgi/wsgi
│   ├── apps/
│   │   ├── core/               # base models, audit, permissions, pagination, utils
│   │   ├── accounts/           # custom User, roles, JWT views
│   │   ├── companies/          # Company, Industry (tree)
│   │   ├── contacts/           # Contact
│   │   ├── leads/              # Lead (canonical), duplicates, scoring, eligibility
│   │   ├── imports/            # LeadSource, ImportFile, ImportJob, mapping engine
│   │   ├── campaigns/          # Campaign, CampaignLead, Service, ServiceIndustryMapping
│   │   ├── email_engine/       # Template, EmailMessage, EmailEvent, quota, SMTP, follow-ups
│   │   ├── ai_engine/          # providers, service matching, safety validator
│   │   ├── crm/                # CRMActivity, LeadNote, pipeline
│   │   ├── analytics/          # metrics aggregation + read API
│   │   ├── suppression/        # Suppression, SuppressionLog
│   │   └── settings/           # SystemSetting + typed settings service
│   ├── requirements.txt, requirements-dev.txt, pytest.ini, Dockerfile
├── frontend/                   # Vite + React + Tailwind SPA
├── worker/                     # Celery worker/beat image
├── nginx/                      # reverse proxy config
├── docs/                       # this file + API/schema/phase docs
├── docker-compose.yml, docker-compose.prod.yml, .env.example
└── README.md
```

---

## 10. Docker architecture

Services (`docker-compose.yml`):

| Service | Image / build | Role | Healthcheck |
|---|---|---|---|
| `db` | `postgres:16-alpine` | primary datastore, `PERSISTENT` volume | `pg_isready` |
| `redis` | `redis:7-alpine` | Celery broker + result backend + cache | `redis-cli ping` |
| `backend` | `backend/Dockerfile` (python:3.12-slim, non-root) | gunicorn `:8000` | `/api/health/` |
| `worker` | `worker/Dockerfile` (same base image) | Celery worker, queues `imports,ai,email,analytics,default` | `celery inspect ping` |
| `beat` | same image | Celery beat (single instance, singleton lock file) | — |
| `frontend` | `frontend/Dockerfile` (node:22-alpine build → nginx serve) | SPA on `:8080` | — |
| `nginx` | `nginx:1.27-alpine` | public entrypoint `:80/:443`, proxies `/api`, `/admin`, `/t`, serves SPA | — |

* All stateful data on named volumes (`postgres_data`, `redis_data`, `media_data`, `static_data`).
* Backend waits for `db` + `redis` healthchecks, then runs `migrate --noinput` at start-up
  (idempotent) and, when `DJANGO_SUPERUSER_EMAIL` is set, creates the superuser if missing.
* Worker/beat share the backend image so there is exactly one dependency set to build.
* `docker-compose.prod.yml` adds: gunicorn workers/threads, whitenoise + collected static,
  TLS termination placeholders in nginx, `restart: unless-stopped`, resource limits, and
  `DEBUG=0` with strict security headers (HSTS, `X-Frame-Options`, CSP for the SPA).
* Secrets: never baked into images — `.env` only (see `.env.example`); `EMAIL_HOST_PASSWORD`
  and `ENCRYPTION_KEY` are read at runtime.

---

## Appendix — configuration surface

| Setting | Env var | Default | Notes |
|---|---|---|---|
| SMTP host/port/user/password/TLS | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | — | required for real sending |
| From / reply-to | `DEFAULT_FROM_EMAIL`, `DEFAULT_REPLY_TO` | — | per-campaign override allowed |
| SMTP daily limit | `SMTP_DAILY_LIMIT` | `100` | hard ceiling for marketing |
| Marketing daily limit | `DEFAULT_DAILY_MARKETING_LIMIT` | `90` | must be `< SMTP_DAILY_LIMIT` |
| Absolute safety cap | `EMAIL_HARD_DAILY_CAP` | `90` | cannot be raised from the UI |
| Send window | `SEND_WINDOW_START`, `SEND_WINDOW_END` | `09:30`, `17:30` | local timezone |
| Min seconds between sends | `EMAIL_MIN_SECONDS_BETWEEN_SENDS` | `20` | rate-limit friendliness |
| Import chunk size | `IMPORT_CHUNK_SIZE` | `1000` | memory ceiling O(chunk) |
| Max upload MB | `IMPORT_MAX_FILE_MB` | `500` | validated server-side |
| AI provider/model/key | `AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`, `AI_BASE_URL` | `rules` / — | `rules` = offline deterministic |
| DB | `POSTGRES_*` or `DATABASE_URL`, `DB_ENGINE` | postgres | `sqlite` for local test runs |


---

## 11. Implementation status (what exists in the repository)

| Component | Files | Notes |
|---|---|---|
| Request lifecycle, RBAC, audit log | `apps/core`, `apps/accounts` | JWT + refresh, roles ADMIN/MANAGER/AGENT/VIEWER, encrypted fields |
| Lead schema & statuses | `apps/leads/models.py` | `IMPORTED · VALID · INVALID · CONTACTED · REPLIED · UNSUBSCRIBED · BOUNCED · SUPPRESSED · MISSING_EMAIL · ARCHIVED`, `EmailStatus`, `EnrichmentStatus`, `CRMStage` |
| Scoring | `apps/leads/scoring.py` | Configurable weights + thresholds in `SystemSetting` |
| Industry classification | `apps/leads/classifier.py` | Seed taxonomy + keyword inference + source-metadata inference |
| Dedupe | `apps/leads/dedupe.py` | 100 / 95 / 90 / 80 / 70 / 55 confidence ladder, blocking keys |
| Merge | `apps/leads/merge.py` | Richest-record survivor, provenance union, related-object re-pointing |
| Eligibility | `apps/leads/eligibility.py` | Per-lead evaluation + DB-level `eligible_queryset()` |
| Imports | `apps/imports/*` | `readers.py` (chunked CSV/XLSX), `mapping.py` (5-pass mapper), `pipeline.py`, `tasks.py` |
| Campaigns | `apps/campaigns/*`, `apps/email_engine/services.py` | Audience filters, spread scheduling, dispatch, follow-ups |
| Daily quota | `apps/email_engine/quota.py` | Conditional UPDATE + `select_for_update`; tested with 12–20 threads |
| Sending | `apps/email_engine/sender.py`, `tasks.py` | SMTP only, bounce classification, retry with backoff, stuck-message release |
| Tracking | `apps/email_engine/views.py` + `tracking_urls.py` | `/t/o/{uid}.png`, `/t/c/{uid}?u=`, `/unsubscribe/{token}/` |
| AI | `apps/ai_engine/*` | Provider interface, rules/openai/anthropic/ollama adapters, safety validator, service matching |
| CRM | `apps/crm/*` | Stages, activities, notes, timeline, bulk moves |
| Analytics | `apps/analytics/*` | Read-side aggregations + nightly `DailyMetric` rollups |
| Settings | `apps/settings/*` | Typed key/value with schema, masking and change log |
| Frontend | `frontend/src/*` | 21 screens, server-side pagination everywhere, dark mode |
| Tests | `backend/tests/*` | 163 tests, no external services required |
