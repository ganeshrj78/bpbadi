"""Add level field to players table

Revision ID: i0d1e2f3a4b5
Revises: h9c0d1e2f3a4
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision = 'i0d1e2f3a4b5'
down_revision = '9e4f33afbfce'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa_inspect(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('players')]
    if 'level' not in existing_cols:
        op.add_column('players', sa.Column('level', sa.Integer(), nullable=True, server_default='1'))


def downgrade():
    inspector = sa_inspect(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('players')]
    if 'level' in existing_cols:
        op.drop_column('players', 'level')
