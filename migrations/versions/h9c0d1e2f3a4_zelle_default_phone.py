"""Set zelle_preference default to phone for all players

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
Create Date: 2026-03-19

"""
from alembic import op

revision = 'h9c0d1e2f3a4'
down_revision = 'g8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE players SET zelle_preference = 'phone' WHERE zelle_preference = 'email' OR zelle_preference IS NULL")


def downgrade():
    pass
