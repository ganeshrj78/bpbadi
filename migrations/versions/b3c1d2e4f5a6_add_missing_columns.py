"""add missing columns to existing tables

Revision ID: b3c1d2e4f5a6
Revises: 4a4952489ae7
Create Date: 2026-02-27 16:00:00.000000

Adds columns that were introduced after the original db.create_all() ran on
the Render PostgreSQL database. All statements use ADD COLUMN IF NOT EXISTS
so they are safe to run on both fresh and existing databases.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'b3c1d2e4f5a6'
down_revision = '4a4952489ae7'
branch_labels = None
depends_on = None


def _is_postgresql():
    return op.get_bind().dialect.name == 'postgresql'


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # ── sessions ──────────────────────────────────────────────────────────────
    session_cols = {c['name'] for c in inspector.get_columns('sessions')}
    if 'hours' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN hours FLOAT DEFAULT 3")
    if 'start_time' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN start_time VARCHAR(10) DEFAULT '06:30'")
    if 'end_time' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN end_time VARCHAR(10) DEFAULT '09:30'")
    if 'court_cost' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN court_cost FLOAT DEFAULT 105")
    if 'voting_frozen' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN voting_frozen BOOLEAN DEFAULT FALSE")
    if 'credits' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN credits FLOAT DEFAULT 0")
    if 'is_archived' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN is_archived BOOLEAN DEFAULT FALSE")
    if 'created_by' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN created_by INTEGER")
    if 'created_at' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if 'updated_by' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN updated_by INTEGER")
    if 'updated_at' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # ── players ───────────────────────────────────────────────────────────────
    player_cols = {c['name'] for c in inspector.get_columns('players')}
    if 'date_of_birth' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN date_of_birth DATE")
    if 'gender' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN gender VARCHAR(10) DEFAULT 'male'")
    if 'profile_photo' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN profile_photo VARCHAR(255)")
    if 'managed_by' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN managed_by INTEGER")
    if 'is_admin' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
    if 'is_active' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
    if 'is_approved' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN is_approved BOOLEAN DEFAULT FALSE")
    if 'additional_charges' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN additional_charges FLOAT DEFAULT 0")
    if 'admin_comments' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN admin_comments TEXT")
    if 'zelle_preference' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN zelle_preference VARCHAR(10) DEFAULT 'email'")
    if 'created_by' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN created_by INTEGER")
    if 'created_at' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if 'updated_by' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN updated_by INTEGER")
    if 'updated_at' not in player_cols:
        op.execute("ALTER TABLE players ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # ── attendances ───────────────────────────────────────────────────────────
    att_cols = {c['name'] for c in inspector.get_columns('attendances')}
    if 'payment_status' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN payment_status VARCHAR(20) DEFAULT 'unpaid'")
    if 'additional_cost' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN additional_cost FLOAT DEFAULT 0")
    if 'comments' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN comments TEXT")
    if 'created_by' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN created_by INTEGER")
    if 'created_at' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if 'updated_by' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN updated_by INTEGER")
    if 'updated_at' not in att_cols:
        op.execute("ALTER TABLE attendances ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # ── attendances composite index ───────────────────────────────────────────
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('attendances')}
    if 'idx_attendance_session_status_cat' not in existing_indexes:
        op.execute(
            "CREATE INDEX idx_attendance_session_status_cat "
            "ON attendances (session_id, status, category)"
        )

    # ── courts ────────────────────────────────────────────────────────────────
    court_cols = {c['name'] for c in inspector.get_columns('courts')}
    if 'name' not in court_cols:
        op.execute("ALTER TABLE courts ADD COLUMN name VARCHAR(50) DEFAULT 'Court'")
    if 'court_type' not in court_cols:
        op.execute("ALTER TABLE courts ADD COLUMN court_type VARCHAR(20) DEFAULT 'regular'")
    if 'created_by' not in court_cols:
        op.execute("ALTER TABLE courts ADD COLUMN created_by INTEGER")
    if 'created_at' not in court_cols:
        op.execute("ALTER TABLE courts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if 'updated_by' not in court_cols:
        op.execute("ALTER TABLE courts ADD COLUMN updated_by INTEGER")
    if 'updated_at' not in court_cols:
        op.execute("ALTER TABLE courts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # ── payments ──────────────────────────────────────────────────────────────
    pay_cols = {c['name'] for c in inspector.get_columns('payments')}
    if 'notes' not in pay_cols:
        op.execute("ALTER TABLE payments ADD COLUMN notes TEXT")
    if 'created_by' not in pay_cols:
        op.execute("ALTER TABLE payments ADD COLUMN created_by INTEGER")
    if 'created_at' not in pay_cols:
        op.execute("ALTER TABLE payments ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if 'updated_by' not in pay_cols:
        op.execute("ALTER TABLE payments ADD COLUMN updated_by INTEGER")
    if 'updated_at' not in pay_cols:
        op.execute("ALTER TABLE payments ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # ── dropout_refunds (create if missing) ───────────────────────────────────
    if not inspector.has_table('dropout_refunds'):
        op.execute("""
            CREATE TABLE dropout_refunds (
                id SERIAL PRIMARY KEY,
                player_id INTEGER NOT NULL REFERENCES players(id),
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                refund_amount FLOAT NOT NULL DEFAULT 0,
                suggested_amount FLOAT DEFAULT 0,
                instructions TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                processed_date TIMESTAMP,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        dr_cols = {c['name'] for c in inspector.get_columns('dropout_refunds')}
        if 'suggested_amount' not in dr_cols:
            op.execute("ALTER TABLE dropout_refunds ADD COLUMN suggested_amount FLOAT DEFAULT 0")
        if 'created_by' not in dr_cols:
            op.execute("ALTER TABLE dropout_refunds ADD COLUMN created_by INTEGER")
        if 'created_at' not in dr_cols:
            op.execute("ALTER TABLE dropout_refunds ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if 'updated_by' not in dr_cols:
            op.execute("ALTER TABLE dropout_refunds ADD COLUMN updated_by INTEGER")
        if 'updated_at' not in dr_cols:
            op.execute("ALTER TABLE dropout_refunds ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # ── birdie_bank (create if missing) ───────────────────────────────────────
    if not inspector.has_table('birdie_bank'):
        op.execute("""
            CREATE TABLE birdie_bank (
                id SERIAL PRIMARY KEY,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                transaction_type VARCHAR(20) NOT NULL,
                quantity INTEGER NOT NULL,
                cost FLOAT DEFAULT 0,
                notes TEXT,
                session_id INTEGER REFERENCES sessions(id),
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # ── site_settings (create if missing) ─────────────────────────────────────
    if not inspector.has_table('site_settings'):
        op.execute("""
            CREATE TABLE site_settings (
                id SERIAL PRIMARY KEY,
                key VARCHAR(50) UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def downgrade():
    # Intentionally left empty — column removal is destructive
    pass
