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
            # Fresh database: create all tables then stamp as current head
            print("Fresh database detected. Creating all tables...")
            db.create_all()
            stamp()
            print("Tables created and migration baseline set.")
        else:
            # Existing database without migration tracking: stamp as current head
            print("Existing database detected (no migration history). Stamping as current head...")
            stamp()
            print("Migration baseline set. Future schema changes will be tracked.")
    else:
        # Database already tracked by Alembic: apply any pending migrations
        print("Applying pending migrations...")
        upgrade()
        print("Migrations applied.")
PYEOF

echo "Starting gunicorn..."
exec gunicorn -w 3 --threads 2 --worker-class gthread --timeout 60 --max-requests 1000 --max-requests-jitter 100 --preload app:app
