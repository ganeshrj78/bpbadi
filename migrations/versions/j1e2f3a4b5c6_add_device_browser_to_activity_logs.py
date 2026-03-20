"""Add device_type, os, and browser to activity_logs

Revision ID: j1e2f3a4b5c6
Revises: i0d1e2f3a4b5
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision = 'j1e2f3a4b5c6'
down_revision = 'i0d1e2f3a4b5'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa_inspect(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('activity_logs')]
    if 'device_type' not in existing_cols:
        op.add_column('activity_logs', sa.Column('device_type', sa.String(10), nullable=True))
    if 'os' not in existing_cols:
        op.add_column('activity_logs', sa.Column('os', sa.String(50), nullable=True))
    if 'browser' not in existing_cols:
        op.add_column('activity_logs', sa.Column('browser', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('activity_logs', 'browser')
    op.drop_column('activity_logs', 'os')
    op.drop_column('activity_logs', 'device_type')
