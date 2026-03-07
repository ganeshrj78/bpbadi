#!/bin/bash
set -e

echo "Running database migration check..."

python3 - <<'PYEOF'
from app import app, db
from flask_migrate import upgrade, stamp
from sqlalchemy import inspect, text

with app.app_context():
    inspector = inspect(db.engine)
    has_alembic = inspector.has_table('alembic_version')
    has_players = inspector.has_table('players')

    if not has_alembic:
        if not has_players:
            print("Fresh database detected. Creating all tables...")
            db.create_all()
            stamp()
            print("Tables created and migration baseline set.")
        else:
            print("Existing database detected (no migration history). Stamping as current head...")
            stamp()
            print("Migration baseline set. Future schema changes will be tracked.")
    else:
        print("Applying pending migrations...")
        upgrade()
        print("Migrations applied.")
PYEOF

echo "Starting gunicorn..."
exec gunicorn -w 1 --threads 2 --timeout 180 --preload --bind 0.0.0.0:${PORT:-8080} app:app
