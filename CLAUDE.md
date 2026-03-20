# CLAUDE.md

## Project Overview

BP Badminton — Flask web app for managing a badminton club. Tracks players, sessions, attendance, payments, shuttlecock inventory (Birdie Bank), dropout refunds, notifications, and activity logs.

## Commands

```bash
python3 app.py                    # Run on localhost:5050 (debug mode)
python3 seed.py                   # Seed database
```

**IMPORTANT:** `use_reloader=False` — restart server manually after editing `app.py`.

## Tech Stack

- **Backend:** Flask 3.0, SQLAlchemy, Flask-Migrate (Alembic)
- **DB:** SQLite (local), PostgreSQL (Render production)
- **Frontend:** Jinja2, Tailwind CSS (CDN), Alpine.js 3.x
- **Auth:** Password login + Google Sign-In (GIS) for @gmail.com accounts
- **Theme:** Wimbledon — Purple (#44005C), Green (#006633), Gold (#C4A747), Cream (#F5F5DC)
- **Caching:** FileSystemCache (shared across gunicorn workers), memoized expensive queries (60s TTL)
- **Deploy:** Render (Docker, paid tier) — `start.sh` runs `flask db upgrade`, seeds trivia, then gunicorn (3 workers, gthread)

## Key Models

- `Player` — members with auth, categories (regular/adhoc/kid), `managed_by` for family dependents
- `Session` — court bookings with date, birdie cost, credits, `voting_frozen`, `payment_released`, archived flag
- `Court` — per-court rows (name, type, cost, times)
- `Attendance` — player status + **per-session category** + payment_status + comments
- `Payment` — global payment records; negative amounts = refund credits
- `DropoutRefund` — pending/processed/cancelled refunds
- `BirdieBank` — shuttlecock inventory: purchase/usage/reimbursement, `purchased_by` FK to Player
- `ActivityLog` — audit trail for all admin/player actions
- `Notification` / `NotificationRead` — in-app notifications with read tracking
- `SiteSettings` — key/value store for app-wide settings (e.g. guidelines)
- `ExternalIntegration` — encrypted credentials for external services (e.g. EZFacility)
- `BadmintonTrivia` — 400+ badminton facts shown randomly on login

## Category System

**Category stored per-session in `attendance.category`, NOT from `player.category`.**
- `player.category` only used as default when creating attendance records
- Category changeable per-session via dropdown or toggle button
- API: `POST /api/attendance/category` accepts `session_id` or `session_ids` (bulk)

## Cost Calculation

- `Per non-kid player = regular_court_cost / regular_player_count + birdie_cost`
- Kids: flat $11 (no birdie, no court share)
- Regular and Adhoc pay same rate
- Balance = charges − payments (all payments including negative refunds)
- Balance can go negative (credit/overpayment)

## Payment Release Flow

1. Admin creates session → players vote attendance
2. Admin freezes voting (`voting_frozen = True`) → locks attendance
3. Admin releases for payment (`payment_released = True`) → charges appear on player payment screen
4. Player payment screen only shows charges from released or archived sessions (`frozen_only=True`)
5. Both freeze and release are toggle buttons (single button each, on session detail and bulk on sessions list)

## Attendance Statuses

YES (charged), NO, TENTATIVE, DROPOUT (charged, refund possible), FILLIN (charged), STANDBY, PENDING_DROPOUT, PENDING_STANDBY

`payment_status`: `unpaid` | `paid` | `pending_refund`

## Player Display Order

- **Sessions page:** Regular → Adhoc → Kids → Not Playing
- **Session detail:** Regular → Adhoc → Waitlisted → Not Playing

## Dropout Flow

1. DROPOUT → modal → `/api/attendance/process-dropout`
2. Creates `DropoutRefund(pending)`, promotes STANDBY → FILLIN
3. Process refund → `payment_status='paid'`, negative Payment created
4. Session deletion cleans up DropoutRefund and associated refund Payment records

## Standby Request Flow

1. Player requests standby on frozen session → `POST /api/player/request-standby` → status = `PENDING_STANDBY`
2. Admin sees request on dashboard + notification bell + session detail "Pending Standby Requests" card
3. Admin approves → `POST /api/admin/approve-standby` → status = `STANDBY` (added to waitlist)
4. Admin rejects → status reverts to `NO`

## Manual Refund Flow

1. Admin uses Record Payment form with Payment/Refund toggle
2. Refund stored as negative `Payment.amount`, `method='Refund'`
3. Refund reason dropdown: Duplicate, Paid Extra, Incorrect Payment, Other
4. Notes prefixed with "Adhoc Refund - {reason}"

## Payment Collector

- Admin assigns a payment collector per month via sessions page dropdown
- Collector name/Zelle shown in player sessions page (all months) and payment page (released months only)
- Player payment form shows per-month breakdown with dynamic "Pay to" banner

## Login Trivia

- Random badminton trivia from `BadmintonTrivia` table shown on every login (player and admin)
- 400+ facts across categories (history, speed, equipment, rules, fitness, etc.)
- Seeded automatically on Render deploy via `start.sh`

## Migrations — MUST be idempotent

```python
inspector = Inspector.from_engine(op.get_bind())
existing_cols = [c['name'] for c in inspector.get_columns('table_name')]
if 'col_name' not in existing_cols:
    op.add_column(...)
```

## Performance

- **Gunicorn:** 3 workers × 2 threads (`gthread`), 60s timeout, `max-requests 1000` for memory leak prevention
- **Caching:** `FileSystemCache` in `.flask_cache/` — shared across workers (not `SimpleCache` which is per-process)
- **Cache invalidation:** `clear_session_cache()` clears `get_cached_monthly_summary`, `get_cached_player_stats`, `get_cached_session_costs`
- **N+1 prevention:** Routes MUST pre-compute all session/player stats and pass them as dicts to templates. Never call model methods like `sess.get_cost_per_player()` in template loops.
- **Batch session stats:** Use `compute_session_display_stats(session_ids)` to batch-compute `time_range`, `court_count`, `attendee_count`, `cost_per_player`, `birdie_total`, `total_collection` for any list of sessions in 3 queries.
- **Pre-computed cost maps:** `get_cached_player_stats()` returns `session_cost_map` for per-attendance cost lookups. Use `att_cost_map[att.id]` in templates instead of `att.session.get_cost_per_player()`.
- **Bulk operations:** Always batch-load sessions with `Session.query.filter(Session.id.in_(ids))` instead of per-item `Session.query.get()` in loops.
- **Connection pool:** `pool_size=5, max_overflow=5` per worker — total max 30 connections across 3 workers
- **Indexes:** Composite indexes on hot query paths (attendance session+status+category, payment date+player, refund player+status)
- **Deferred loading:** `profile_photo_data` uses `db.deferred()` — never loaded unless explicitly accessed. Templates use `profile_photo_mime` for existence checks.
- **ETag caching:** All HTML responses get ETag + `Cache-Control: no-cache` for browser/edge 304 revalidation. Static files cached 1 week. Player photo route returns ETag + Cache-Control headers.
- **Jinja2 bytecode caching:** Templates compiled once, reused across requests via `FileSystemBytecodeCache`
- **Gzip compression:** `Flask-Compress` reduces HTML response size ~70%

## Critical Gotchas

- **DropoutRefund backref expires** after commit → use direct query
- **HTML escaping** — never `{{ value | tojson }}` inside `onchange`. Use `data-attr` + `dataset`
- **Jinja2 loops** — use `namespace()` for mutation
- **Template safety** — guard new vars with `| default({})`
- All JSON APIs use `@csrf.exempt`. Admin APIs use `@admin_required`.
- **Encryption** — `ExternalIntegration` columns encrypted via Fernet derived from `SECRET_KEY`
- **Cache sharing** — never use `SimpleCache` with multi-worker gunicorn; use `FileSystemCache` or Redis

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session secret + encryption key |
| `DATABASE_URL` | No | DB connection (default: SQLite) |
| `APP_PASSWORD` | No | Master admin password (default: `bpbadi2024`) |
| `GOOGLE_CLIENT_ID` | No | Google OAuth client ID for Sign-In |
| `RENDER` | Auto | Set to `true` by Render for production detection |

## Additional Docs

- DB schema + ER diagram: `docs/CLAUDE.md`
- Template conventions: `templates/CLAUDE.md`
