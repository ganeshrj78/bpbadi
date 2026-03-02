"""add credits column to sessions

Revision ID: c4d2e3f6a7b8
Revises: b3c1d2e4f5a6
Create Date: 2026-03-02 18:30:00.000000
"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = 'c4d2e3f6a7b8'
down_revision = 'b3c1d2e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    session_cols = {c['name'] for c in inspector.get_columns('sessions')}
    if 'credits' not in session_cols:
        op.execute("ALTER TABLE sessions ADD COLUMN credits FLOAT DEFAULT 0")


def downgrade():
    pass
