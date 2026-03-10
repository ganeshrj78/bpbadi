# CLAUDE.md

## Project Overview

BP Badminton — Flask web app for managing a badminton club. Tracks players, sessions, attendance, payments, shuttlecock inventory (Birdie Bank), and dropout refunds.

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
- **Theme:** Wimbledon — Purple (#44005C), Green (#006633), Gold (#C4A747), Cream (#F5F5DC)
- **Deploy:** Render (Docker) — `start.sh` runs `flask db upgrade` then gunicorn

## Key Models

- `Player` — members with auth, categories (regular/adhoc/kid), `managed_by` for family dependents
- `Session` — court bookings with date, birdie cost, credits, archived/frozen flags
- `Court` — per-court rows (name, type, cost, times)
- `Attendance` — player status + **per-session category** + payment_status + comments
- `Payment` — global payment records; negative amounts = refund credits
- `DropoutRefund` — pending/processed/cancelled refunds
- `BirdieBank` — shuttlecock inventory: purchase/usage/reimbursement, `purchased_by` FK to Player

## Category System

**Category stored per-session in `attendance.category`, NOT from `player.category`.**
- `player.category` only used as default when creating attendance records
- Category changeable per-session via dropdown or toggle button
- API: `POST /api/attendance/category` accepts `session_id` or `session_ids` (bulk)

## Cost Calculation

- `Per non-kid player = regular_court_cost / regular_player_count + birdie_cost`
- Kids: flat $11 (no birdie, no court share)
- Regular and Adhoc pay same rate
- Balance = charges − payments (refunds excluded via `Payment.amount > 0`)

## Attendance Statuses

YES (charged), NO, TENTATIVE, DROPOUT (charged, refund possible), FILLIN (charged), STANDBY

`payment_status`: `unpaid` | `paid` | `pending_refund`

## Player Display Order

- **Sessions page:** Regular → Adhoc → Kids → Not Playing
- **Session detail:** Regular → Adhoc → Waitlisted → Not Playing

## Dropout Flow

1. DROPOUT → modal → `/api/attendance/process-dropout`
2. Creates `DropoutRefund(pending)`, promotes STANDBY → FILLIN
3. Process refund → `payment_status='paid'`, negative Payment created

## Migrations — MUST be idempotent

```python
inspector = Inspector.from_engine(op.get_bind())
existing_cols = [c['name'] for c in inspector.get_columns('table_name')]
if 'col_name' not in existing_cols:
    op.add_column(...)
```

## Critical Gotchas

- **DropoutRefund backref expires** after commit → use direct query
- **HTML escaping** — never `{{ value | tojson }}` inside `onchange`. Use `data-attr` + `dataset`
- **Jinja2 loops** — use `namespace()` for mutation
- **Template safety** — guard new vars with `| default({})`
- All JSON APIs use `@csrf.exempt`. Admin APIs use `@admin_required`.

## Environment Variables

`SECRET_KEY`, `DATABASE_URL` (default sqlite), `APP_PASSWORD`, `BROWSERLESS_URL`

## Additional Docs

- DB schema + ER diagram: `docs/CLAUDE.md`
- Template conventions: `templates/CLAUDE.md`
