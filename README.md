# BP Badminton Club Manager

A web application for managing a badminton club — tracking players, court sessions, attendance, payments, and shuttlecock inventory.

## What It Does

- **Session management** — Create court sessions, assign courts, track costs per session
- **Attendance tracking** — Players vote YES/NO/TENTATIVE; admins manage FILLIN/DROPOUT/STANDBY
- **Automatic cost splitting** — Shared pool model divides court costs across all non-kid players equally; kids pay a flat $11
- **Payment tracking** — Record payments per player, track balances, mark sessions paid/unpaid
- **Dropout & refund flow** — When a player drops out, the system assigns a fill-in from the standby list and tracks a pending refund; admin processes the refund when settled
- **Shuttlecock (birdie) bank** — Track inventory purchases and usage per session
- **Monthly summaries** — Drill down by month to see charges, collections, refunds, and credits
- **Royal Facility sync** — Scrapes court bookings from royalbadminton.ezfacility.com and imports them into sessions

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.0, Flask-SQLAlchemy, Flask-Migrate |
| Database | SQLite (local), PostgreSQL (production) |
| Frontend | Jinja2, Tailwind CSS, Alpine.js 3.x |
| Scraping | Selenium (Chrome) |
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

## Cost Model

```
Total Pool = sum(court costs) + session credits
Cost per player = Total Pool / non-kid count + birdie cost
Kids = flat $11
```

Regular and adhoc players share one pool equally. Credits carry forward to the next month.

## Key Roles

| Role | Access |
|------|--------|
| Master Admin | Full access via `APP_PASSWORD` env var |
| Player Admin | Manage sessions, payments, attendance |
| Player | View own data, vote attendance |

## Deployment

Hosted on Render. On deploy, `start.sh` runs:
```bash
flask db upgrade   # Apply any pending migrations
gunicorn app:app   # Start the production server
```

Set these environment variables on Render:
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — Flask session secret
- `APP_PASSWORD` — Master admin password

## Project Structure

```
app.py                  # All routes and API endpoints
models.py               # Database models
ezf_scrape.py           # Royal Facility court booking scraper
templates/              # Jinja2 HTML templates
migrations/versions/    # Alembic database migrations
static/uploads/         # Player profile photos
docs/CLAUDE.md          # Database schema and ER diagram
```
