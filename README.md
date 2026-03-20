# BP Badminton Club Manager

A web application for managing a badminton club — tracking players, court sessions, attendance, payments, shuttlecock inventory, and more.

## Features

- **Session management** — Create court sessions, assign courts, track costs per session
- **Attendance tracking** — Players vote YES/NO/TENTATIVE; admins manage FILLIN/DROPOUT/STANDBY
- **Automatic cost splitting** — Shared pool model divides court costs across all non-kid players equally; kids pay a flat $11
- **Payment tracking** — Record payments per player, track balances, mark sessions paid/unpaid
- **Payment release workflow** — Admins freeze voting, then release sessions for payment; players only see charges for released/archived sessions
- **Dropout & refund flow** — When a player drops out, the system assigns a fill-in from the standby list and tracks a pending refund
- **Shuttlecock (birdie) bank** — Track inventory purchases and usage per session
- **Monthly summaries** — Drill down by month to see charges, collections, refunds, and credits
- **Google Sign-In** — Players with Gmail accounts can log in via Google
- **Family management** — Parent players can vote and pay for managed dependents
- **Standby requests** — Players can request to join frozen sessions as standby; admin approves from dashboard or session detail
- **Manual refunds** — Admin can process ad-hoc refunds (duplicate, overpayment, incorrect) via Record Payment
- **Payment collector** — Admin assigns a collector per month; Zelle details shown on player sessions and payment screens
- **Login trivia** — Random badminton facts (400+) shown on every login for players and admins
- **Notifications** — In-app notifications for dropout requests, standby requests, registrations, and admin broadcasts
- **Activity logs** — Full audit trail of all admin and player actions
- **Royal Facility sync** — Imports court bookings from royalbadminton.ezfacility.com into sessions

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.0, Flask-SQLAlchemy, Flask-Migrate |
| Database | SQLite (local), PostgreSQL (production) |
| Frontend | Jinja2, Tailwind CSS (CDN), Alpine.js 3.x |
| Auth | Password + Google Identity Services (GIS) |
| Scraping | Selenium (Chrome) via EZFacility integration |
| Deployment | Render (gunicorn) |

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (port 5050)
python3 app.py

# Seed initial player data
python3 seed.py
```

Visit `http://localhost:5050` — log in with the admin password (default: `bpbadi2024`).

**Note:** The server runs with `use_reloader=False`. Restart manually after editing `app.py`.

## Cost Model

```
Total Pool = SUM(regular court costs) + credits (if apply_credits)
Cost per player = Total Pool / non-kid count + birdie cost
Kids = flat $11
```

Regular and adhoc players share one pool equally.

## Session Lifecycle

```
Open → Voting Frozen → Payment Released → Archived
```

| State | Voting | Charges on Player Screen |
|-------|--------|--------------------------|
| Open | Allowed | Hidden |
| Voting Frozen | Locked | Hidden |
| Payment Released | Locked | Visible |
| Archived | Locked | Visible |

## Key Roles

| Role | Access |
|------|--------|
| Master Admin | Full access via `APP_PASSWORD` env var |
| Player Admin | Manage sessions, payments, attendance |
| Player | View own data, vote attendance, record payments |

## Deployment

Hosted on Render. On deploy, `start.sh` runs:
```bash
flask db upgrade          # Apply any pending migrations
python3 seed_trivia.py    # Seed trivia table if empty
gunicorn app:app          # Start the production server (3 workers, gthread)
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SECRET_KEY` | Yes | Flask session secret + encryption key |
| `APP_PASSWORD` | No | Master admin password (default: `bpbadi2024`) |
| `GOOGLE_CLIENT_ID` | No | Google OAuth client ID for Sign-In |

## Project Structure

```
app.py                  # All routes and API endpoints
models.py               # Database models (Player, Session, Court, Attendance, Payment, BadmintonTrivia, etc.)
config.py               # App configuration and environment
seed.py                 # Seed initial player data
seed_trivia.py          # Seed 400+ badminton trivia facts
ezf_scrape.py           # Royal Facility court booking scraper
start.sh                # Production startup: migrations + trivia seed + gunicorn
templates/              # Jinja2 HTML templates (24 templates)
migrations/versions/    # Alembic database migrations (idempotent)
static/uploads/         # Player profile photos
docs/CLAUDE.md          # Database schema and ER diagram
templates/CLAUDE.md     # Template conventions
```
