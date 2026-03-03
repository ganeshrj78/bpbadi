# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

BP Badminton is a Flask web application for managing a badminton club. It tracks players, court sessions, attendance, payments, and shuttlecock inventory with automatic cost splitting.

## Commands

```bash
pip install -r requirements.txt   # Install dependencies
python app.py                     # Run on localhost:5050 (debug mode)
python seed.py                    # Seed database with player data
```

## Technology Stack

- **Backend:** Flask 3.0, Flask-SQLAlchemy, Werkzeug, Flask-Migrate (Alembic)
- **Database:** SQLite (local `instance/bpbadi.db`), PostgreSQL (production on Render)
- **Frontend:** Jinja2, Tailwind CSS (CDN), Alpine.js 3.x
- **Theme:** Wimbledon — Purple (#44005C), Green (#006633), Gold (#C4A747), Cream (#F5F5DC)
- **Deploy:** Render — `start.sh` runs `flask db upgrade` then `gunicorn app:app`

## Project Structure

```
dpbadi/
├── app.py                  # All routes + API endpoints (~1950 lines)
├── models.py               # SQLAlchemy models
├── config.py               # Configuration management
├── start.sh                # Render startup: runs migrations then gunicorn
├── templates/              # Jinja2 templates
│   ├── base.html           # Base layout (Tailwind CDN + Alpine.js 3.x)
│   ├── dashboard.html      # Admin dashboard with monthly summary
│   ├── sessions.html       # Session matrix + monthly summary
│   ├── session_detail.html # Session detail: merged attendance+payments
│   ├── session_form.html   # Add/edit session with per-court fields
│   ├── month_sessions.html # Monthly drill-down: all sessions for a month
│   └── ...
├── migrations/versions/    # Alembic migration files
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
| `Payment` | Global payment records (not session-specific) |
| `DropoutRefund` | Refunds for dropouts: pending/processed/cancelled + processed_date |
| `BirdieBank` | Shuttlecock inventory: purchase/usage transactions |
| `SiteSettings` | Key/value config store |

## Cost Calculation

**Shared pool model:**
- `Total Pool = sum(all court costs) + session.credits`
- `Per non-kid player = Total Pool / non_kid_count + birdie_cost`
- **Kids:** flat $11 (no birdie, no court share)
- **Regular and Adhoc players pay the same rate** — all share one pool equally
- Adhoc court costs are funded from the credit pool; credits carry forward to next month
- **Balance** = total charges − total payments

Key model methods:
- `session.get_cost_per_regular_player()` — shared pool / non-kid count + birdie
- `session.get_cost_per_adhoc_player()` — same as regular
- `session.get_total_collection()` — sum across all YES/DROPOUT/FILLIN attendees
- `session.get_total_cost()` — sum of all court costs
- `session.get_total_refunds()` — sum of processed DropoutRefunds

## Authentication

- **Master Admin:** `APP_PASSWORD` env var (default: `bpbadi2024`) — full access
- **Player Admin:** Player with `is_admin=True` — manage sessions, payments, attendance
- **Player:** Registered + approved player — view own data, vote attendance

## Attendance Statuses

| Status | Meaning | Charged? |
|--------|---------|---------|
| `YES` | Confirmed attending | Yes |
| `NO` | Not participating | No |
| `TENTATIVE` | Maybe attending | No |
| `DROPOUT` | Was yes, dropped out | Yes (refund possible) |
| `FILLIN` | Filled in for dropout | Yes |
| `STANDBY` | On waitlist | No |

Session detail only shows YES/FILLIN/STANDBY/DROPOUT (hides NO/TENTATIVE).

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

## Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/attendance` | POST | Update attendance status (admin) |
| `/api/player/attendance` | POST | Player updates own attendance |
| `/api/attendance/payment-status` | POST | Mark attendance paid/unpaid |
| `/api/attendance/additional-cost` | POST | Set extra charge for player |
| `/api/attendance/comments` | POST | Set attendance comment |
| `/api/attendance/category` | POST | Override player category for session |
| `/api/bulk-session-payment` | POST | Record payments for multiple players |
| `/api/bulk-assign-courts` | POST | Assign courts to multiple sessions |
| `/api/bulk-attendance` | POST | Bulk YES/NO attendance update |
| `/health` | GET | Health check for uptime monitoring |

All JSON APIs use `@csrf.exempt`. Admin APIs use `@admin_required`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `dev-secret-key...` |
| `DATABASE_URL` | Database connection URL | `sqlite:///bpbadi.db` |
| `APP_PASSWORD` | Master admin password | `bpbadi2024` |

## Additional Documentation

- Database schema + ER diagram: `docs/CLAUDE.md`
- Template conventions: `templates/CLAUDE.md`
