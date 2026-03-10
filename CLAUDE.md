# CLAUDE.md

## Project Overview

BP Badminton — Flask web app for managing a badminton club. Tracks players, court sessions, attendance, payments, shuttlecock inventory, and dropout refunds with automatic cost splitting.

## Commands

```bash
pip install -r requirements.txt   # Install dependencies
python3 app.py                    # Run on localhost:5050 (debug mode) — use python3, not python
python3 seed.py                   # Seed database with player data
```

**IMPORTANT:** `use_reloader=False` is set — server does NOT auto-reload. Always restart manually after editing `app.py`.

## Technology Stack

- **Backend:** Flask 3.0, Flask-SQLAlchemy, Werkzeug, Flask-Migrate (Alembic)
- **Database:** SQLite (local `instance/bpbadi.db`), PostgreSQL (production on Render)
- **Frontend:** Jinja2, Tailwind CSS (CDN), Alpine.js 3.x
- **Theme:** Wimbledon — Purple (#44005C), Green (#006633), Gold (#C4A747), Cream (#F5F5DC)
- **Deploy:** Render (Docker runtime) — `start.sh` runs `flask db upgrade` then `gunicorn app:app`
- **Scraping:** Playwright via `ezf_scrape.py` subprocess + remote Browserless for Royal Facility court sync

## Project Structure

```
dpbadi/
├── app.py                  # All routes + API endpoints (~3100 lines)
├── models.py               # SQLAlchemy models
├── config.py               # Configuration management
├── ezf_scrape.py           # Playwright scraper for Royal Facility court bookings
├── start.sh                # Render startup: runs migrations then gunicorn
├── templates/
│   ├── base.html           # Base layout (Tailwind CDN + Alpine.js 3.x)
│   ├── dashboard.html      # Admin dashboard with monthly summary
│   ├── sessions.html       # Session matrix + monthly summary (~1400 lines)
│   ├── session_detail.html # Session detail: attendance+payments+refunds (~950 lines)
│   ├── session_form.html   # Add/edit session with per-court fields
│   ├── month_sessions.html # Monthly drill-down + Royal Facility sync modal
│   ├── activity_logs.html  # Activity logs with client-side filtering/sorting
│   ├── player_payments.html# Player payment recording (player landing page)
│   ├── player_profile.html # Player self-service profile
│   ├── player_sessions.html# Player session voting
│   └── ezfacility_settings.html  # Royal Facility credentials settings
├── migrations/versions/    # Alembic migrations (all idempotent — check before create)
├── static/uploads/         # Profile photo uploads
├── docs/CLAUDE.md          # DB schema + ER diagram
└── instance/bpbadi.db      # SQLite database (local)
```

## Key Models

| Model | Purpose |
|-------|---------|
| `Player` | Members with auth, categories (regular/adhoc/kid), managed_by for dependents |
| `Session` | Court bookings with date, birdie cost, credits, archived/frozen flags |
| `Court` | Per-court rows within a session (name, type, cost, start/end time) |
| `Attendance` | Player status + **per-session category** + payment_status + comments |
| `Payment` | Global payment records (not session-specific); negative amounts = refund credits |
| `DropoutRefund` | Refunds for dropouts: pending/processed/cancelled + processed_date + refund_amount |
| `ExternalIntegration` | Encrypted credentials for Royal Facility |
| `BirdieBank` | Shuttlecock inventory: purchase/usage transactions |
| `SiteSettings` | Key/value config store |
| `ActivityLog` | Audit trail: user, action, description, IP, timestamp |

## Category System — Per-Session

**Category is stored per-session in `attendance.category`, NOT read from `player.category` at display time.**

- Both sessions matrix and session detail read from `att.category` (Attendance table)
- `player.category` is only used as the initial default when creating attendance records
- Changing `player.category` does NOT retroactively update existing attendance records
- Category can be changed per-session via dropdown (session detail) or toggle button (sessions matrix)
- Bulk category moves available on both pages (select players → →Regular / →Adhoc)
- API: `POST /api/attendance/category` accepts `session_id` (single) or `session_ids` (bulk array)

## Cost Calculation

**Shared pool model:**
- `Per non-kid player = regular_court_cost / regular_player_count + birdie_cost`
- **Kids:** flat $11 (no birdie, no court share)
- **Regular and Adhoc players pay the same rate**
- **Balance** = total charges − total actual payments (refund payments excluded via `Payment.amount > 0` filter)

Key model methods:
- `session.get_cost_per_regular_player()` — regular court cost / regular count + birdie
- `session.get_cost_per_adhoc_player()` — same as regular
- `session.get_total_collection()` — sum across all YES/DROPOUT/FILLIN attendees
- `session.get_total_cost()` — sum of all court costs
- `session.get_total_refunds()` — sum of processed DropoutRefunds

## Attendance Statuses & payment_status

| Status | Meaning | Charged? |
|--------|---------|---------|
| `YES` | Confirmed attending | Yes |
| `NO` | Not participating | No |
| `TENTATIVE` | Maybe attending | No |
| `DROPOUT` | Was yes, dropped out | Yes (refund possible) |
| `FILLIN` | Filled in for dropout | Yes |
| `STANDBY` | On waitlist | No |

`payment_status`: `unpaid` | `paid` | `pending_refund`

Session detail only shows YES/FILLIN/STANDBY/DROPOUT (hides NO/TENTATIVE).

## Dropout / Refund Flow

1. Status dropdown → DROPOUT → JS modal → POST `/api/attendance/process-dropout`
2. Sets `payment_status='pending_refund'`, creates `DropoutRefund(pending)`, promotes STANDBY → FILLIN
3. Comments auto-appended: "Dropped out on MM/DD, filled by X"
4. Pending Refunds card on session_detail — "Process" → `update_dropout_refund`
5. On process: `payment_status → 'paid'`, negative Payment record created
6. `from_session=1` hidden field → redirects back to session_detail

## Fill-In Payment Tracking

When a FILLIN player's payment is recorded (player portal, admin bulk, or individual):
- `attendance.payment_status` set to `paid`
- Comment appended: "Fill-in cost $X.XX paid on MM/DD"
- Sessions matrix shows `+$X.XX settled` (gray) when paid, bold blue amount when unpaid
- `fillin_paid` tracked in `player_stats` and scoped to active sessions monthly

## Player Portal

- **Landing page:** My Payments (balance + payment form, amount auto-populated with balance owed)
- **Nav order:** Sessions → My Payments
- **My Profile:** dropdown near logout with sub-items (Profile Info, Zelle, Password, Photo, Session History, Payment History)
- Player login redirects to `player_payments`, not `player_profile`

## Sessions Page Architecture (sessions.html)

Columns: Player (sticky) | [session dropdowns] | Add'l Charges | Total | Status | Refund | Comments

- Players grouped by `att.category` from attendance records (same source as session detail)
- Per-player buttons: Y (bulk YES), N (bulk NO), →A or →R (category toggle)
- Bulk actions (checkbox selection): Mark Paid, Mark Unpaid, →Regular, →Adhoc
- `attendance_details[session_id][player_id]` includes `category` field
- Colspan for section headers = `active_sessions|length + 5`

## Session Detail Architecture (session_detail.html)

Columns: checkbox | Player | Category | Status | Session Cost | Extra | Refund | Payment | Amount | Comments

- Category dropdown per player (reads/writes `att.category`)
- Bulk actions: Record Payment, →Regular, →Adhoc
- `refund_by_player` = `{player_id: DropoutRefund}` — built with direct query NOT backref
- `pending_refund_pids` = set of player_ids with pending refunds
- Template uses `| default({})` / `| default([])` guards
- `colspan="10"` for section headers

## Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/attendance` | POST | Update attendance status |
| `/api/attendance/process-dropout` | POST | Atomic: DROPOUT + refund + promote STANDBY |
| `/api/attendance/payment-status` | POST | Mark paid/unpaid (validated) |
| `/api/attendance/additional-cost` | POST | Set extra charge |
| `/api/attendance/comments` | POST | Set per-session comment |
| `/api/attendance/category` | POST | Change category (single `session_id` or bulk `session_ids`) |
| `/api/bulk-session-payment` | POST | Record payments for multiple players |
| `/api/bulk-attendance` | POST | Bulk YES/NO |
| `/api/bulk-assign-courts` | POST | Assign courts to sessions |
| `/api/ezfacility/fetch-bookings` | POST | Run Playwright scraper |

All JSON APIs use `@csrf.exempt`. Admin APIs use `@admin_required`.

## Migrations — Critical Pattern

All migrations MUST be idempotent:
```python
inspector = Inspector.from_engine(op.get_bind())
if 'table_name' not in inspector.get_table_names():
    op.create_table(...)
existing_cols = [c['name'] for c in inspector.get_columns('table_name')]
if 'col_name' not in existing_cols:
    op.add_column(...)
```

## Critical Gotchas

- **DropoutRefund backref expires** after `db.session.commit()` → use `DropoutRefund.query.filter_by(session_id=id).all()`
- **HTML attribute escaping** — never use `{{ value | tojson }}` inside `onchange="..."`. Use `data-attr` + `dataset`
- **Jinja2 loop vars** — use `{% set ns = namespace(val=x) %}` for mutation inside loops
- **Template undefined safety** — guard new vars with `| default({})` in case old server serves page

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `dev-secret-key...` |
| `DATABASE_URL` | Database connection URL | `sqlite:///bpbadi.db` |
| `APP_PASSWORD` | Master admin password | `bpbadi2024` |
| `BROWSERLESS_URL` | Remote browser for Playwright scraper | — |

## Additional Documentation

- Database schema + ER diagram: `docs/CLAUDE.md`
- Template conventions: `templates/CLAUDE.md`
