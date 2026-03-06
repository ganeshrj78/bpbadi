"""Add session_cookie column to external_integrations

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-03-05

"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('external_integrations',
        sa.Column('session_cookie', sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column('external_integrations', 'session_cookie')
