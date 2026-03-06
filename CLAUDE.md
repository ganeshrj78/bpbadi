# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

BP Badminton is a Flask web application for managing a badminton club. It tracks players, court sessions, attendance, payments, shuttlecock inventory, and dropout refunds with automatic cost splitting.

## Commands

```bash
pip install -r requirements.txt   # Install dependencies
python3 app.py                    # Run on localhost:5050 (debug mode) — use python3, not python
python3 seed.py                   # Seed database with player data
```

**IMPORTANT:** `use_reloader=False` is set in `app.run()` to avoid Selenium conflicts. The server does NOT auto-reload on file changes — always restart manually after editing `app.py`.

## Technology Stack

- **Backend:** Flask 3.0, Flask-SQLAlchemy, Werkzeug, Flask-Migrate (Alembic)
- **Database:** SQLite (local `instance/bpbadi.db`), PostgreSQL (production on Render)
- **Frontend:** Jinja2, Tailwind CSS (CDN), Alpine.js 3.x
- **Theme:** Wimbledon — Purple (#44005C), Green (#006633), Gold (#C4A747), Cream (#F5F5DC)
- **Deploy:** Render — `start.sh` runs `flask db upgrade` then `gunicorn app:app`
- **Scraping:** Selenium (Chrome) via `ezf_scrape.py` subprocess for Royal Facility court sync

## Project Structure

```
dpbadi/
├── app.py                  # All routes + API endpoints (~2970 lines)
├── models.py               # SQLAlchemy models
├── config.py               # Configuration management
├── ezf_scrape.py           # Selenium scraper for Royal Facility court bookings
├── start.sh                # Render startup: runs migrations then gunicorn
├── templates/
│   ├── base.html           # Base layout (Tailwind CDN + Alpine.js 3.x)
│   ├── dashboard.html      # Admin dashboard with monthly summary
│   ├── sessions.html       # Session matrix + monthly summary (~1360 lines)
│   ├── session_detail.html # Session detail: attendance+payments+refunds (~900 lines)
│   ├── session_form.html   # Add/edit session with per-court fields
│   ├── month_sessions.html # Monthly drill-down + Royal Facility sync modal
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
| `Attendance` | Player status per session: YES/NO/TENTATIVE/DROPOUT/FILLIN/STANDBY + payment_status |
| `Payment` | Global payment records (not session-specific); negative amounts = refund credits |
| `DropoutRefund` | Refunds for dropouts: pending/processed/cancelled + processed_date + refund_amount |
| `ExternalIntegration` | Encrypted credentials for Royal Facility (name, url, username, password, session_cookie) |
| `BirdieBank` | Shuttlecock inventory: purchase/usage transactions |
| `SiteSettings` | Key/value config store |

## Cost Calculation

**Shared pool model:**
- `Total Pool = sum(all court costs) + session.credits`
- `Per non-kid player = Total Pool / non_kid_count + birdie_cost`
- **Kids:** flat $11 (no birdie, no court share)
- **Regular and Adhoc players pay the same rate** — all share one pool equally
- **Balance** = total charges − total actual payments (refund payments excluded from balance calc)

Key model methods:
- `session.get_cost_per_regular_player()` — shared pool / non-kid count + birdie
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

`payment_status` values: `unpaid` | `paid` | `pending_refund`
- Set to `pending_refund` when dropout processed via `process_dropout` endpoint
- Reverts to `paid` when refund settled via `update_dropout_refund` (process action)
- `pending_refund` detection for OLD data: sessions route patches `attendance_details` by cross-referencing `DropoutRefund.status == 'pending'`

Session detail only shows YES/FILLIN/STANDBY/DROPOUT (hides NO/TENTATIVE).

## Dropout / Refund Flow

1. Status dropdown changes to DROPOUT → JS intercepts → opens modal
2. Modal shows standby players sorted by `updated_at` (earliest = highest priority)
3. Admin picks fill-in + sets refund amount → POST `/api/attendance/process-dropout`
4. `process_dropout` endpoint:
   - Sets DROPOUT `payment_status = 'pending_refund'`
   - Creates `DropoutRefund(status='pending')`
   - Promotes STANDBY → FILLIN
   - Appends comments to both players: "Dropped out on MM/DD, filled by X"
5. Pending Refunds card appears on session_detail above Financial Summary
6. Admin clicks "Process" → POST to `update_dropout_refund` with `action=process`
7. Sets `refund.status = 'processed'`, creates negative Payment record, sets `dropout_att.payment_status = 'paid'`
8. Form includes `from_session=1` hidden field → redirects back to session_detail (not session_refunds)

**Key gotcha:** Use `DropoutRefund.query.filter_by(session_id=id).all()` in session_detail route — NOT `sess.dropout_refunds` (backref gets expired after `db.session.commit()`).

## Sessions Page Architecture (sessions.html)

Columns: Player (sticky) | [session dropdowns] | Add'l Charges | Total | Status | Refund | Comments

- **Status badge:** `unpaid` (red) > `pending_refund` (yellow, 2-line with amount) > `paid` (green)
- **Refund column:** shows pending amount in yellow or settled in gray (2 lines)
- **Comments column:** shows aggregated `att.comments` from active sessions as editable input value; falls back to `player.admin_comments`
- **"Not Playing" label:** shown when player has no active session participation
- Colspan for section headers = `active_sessions|length + 5`
- `attendance_details[session_id][player_id]` = dict with status, payment_status, additional_cost, comments
- Sessions route patches `attendance_details` for existing dropout records with pending refunds

## Session Detail Architecture (session_detail.html)

Columns: checkbox | Player | Category | Status | Session Cost | Extra | **Refund** | Payment | Amount | Comments

- **Refund column:** driven by `refund_by_player` dict (player_id → DropoutRefund object)
- **Payment column:** shows "Pending Refund" read-only badge (yellow) when `payment_status == 'pending_refund'`; normal dropdown otherwise
- `pending_refund_pids` passed from route = set of player_ids with pending refunds
- Template uses `| default({})` / `| default([])` guards for both vars (defensive)
- `colspan="10"` for Participants/Waitlisted section headers

## Key Routes

| Route | Description |
|-------|-------------|
| `/` | Dashboard with monthly summary |
| `/sessions` | Session matrix + monthly summary |
| `/sessions/month/<YYYY-MM>` | Monthly drill-down page |
| `/sessions/<id>` | Session detail: merged attendance+payments |
| `/sessions/<id>/edit` | Edit session with per-court fields |
| `/sessions/add` | Create new session |
| `/players` | Player list |
| `/player/<id>` | Player detail |
| `/refunds/<id>` | Update/process/cancel a dropout refund |

## Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/attendance` | POST | Update attendance status (admin) |
| `/api/attendance/process-dropout` | POST | Atomic: mark DROPOUT + create refund + promote STANDBY |
| `/api/attendance/payment-status` | POST | Mark attendance paid/unpaid (validates: only unpaid/paid) |
| `/api/attendance/additional-cost` | POST | Set extra charge for player |
| `/api/attendance/comments` | POST | Set attendance comment (per-session att.comments) |
| `/api/attendance/category` | POST | Override player category for session |
| `/api/bulk-session-payment` | POST | Record payments for multiple players |
| `/api/ezfacility/fetch-bookings` | POST | Run Selenium scraper, return courts grouped by date |

All JSON APIs use `@csrf.exempt`. Admin APIs use `@admin_required`.

## Migrations — Critical Pattern

All migrations MUST be idempotent. Always check before creating:
```python
inspector = Inspector.from_engine(op.get_bind())
if 'table_name' not in inspector.get_table_names():
    op.create_table(...)
existing_cols = [c['name'] for c in inspector.get_columns('table_name')]
if 'col_name' not in existing_cols:
    op.add_column(...)
```
Render deploys run `flask db upgrade` — if a table already exists from `db.create_all()`, a non-idempotent migration will throw `DuplicateTable`.

## Payment Calculation — Critical

`player_payments` in the sessions route filters `Payment.amount > 0` — excludes refund payments (negative) so processed refunds don't distort the balance display. Refunds are shown in a separate Refund column.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `dev-secret-key...` |
| `DATABASE_URL` | Database connection URL | `sqlite:///bpbadi.db` |
| `APP_PASSWORD` | Master admin password | `bpbadi2024` |
| `RF_USERNAME` | Royal Facility login (passed to ezf_scrape.py) | from DB |
| `RF_PASSWORD` | Royal Facility password (passed to ezf_scrape.py) | from DB |

## Common Jinja2 Patterns

```jinja2
{# Loop variable mutation #}
{% set ns = namespace(val=false) %}
{% set ns.val = true %}

{# Defensive undefined guard #}
{% set r = (refund_by_player | default({})).get(player.id) %}
{% if player.id in (pending_refund_pids | default([])) %}

{# Aggregate session comments #}
{% set ns_ac = namespace(val='') %}
{% for _sess in active_sessions %}
    {% set _c = attendance_details.get(_sess.id, {}).get(player.id, {}).get('comments', '') %}
    {% if _c %}{% set ns_ac.val = ns_ac.val + (' | ' if ns_ac.val else '') + _c %}{% endif %}
{% endfor %}
```

## Additional Documentation

- Database schema + ER diagram: `docs/CLAUDE.md`
- Template conventions: `templates/CLAUDE.md`
