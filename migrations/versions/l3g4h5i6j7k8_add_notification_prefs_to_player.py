"""add notify_sms and notify_email to players

Revision ID: l3g4h5i6j7k8
Revises: k2f3a4b5c6d7
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Inspector

# revision identifiers
revision = 'l3g4h5i6j7k8'
down_revision = 'k2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('players')]
    if 'notify_sms' not in existing_cols:
        op.add_column('players', sa.Column('notify_sms', sa.Boolean(), nullable=True, server_default='1'))
    if 'notify_email' not in existing_cols:
        op.add_column('players', sa.Column('notify_email', sa.Boolean(), nullable=True, server_default='1'))


def downgrade():
    op.drop_column('players', 'notify_sms')
    op.drop_column('players', 'notify_email')
