"""Add purchased_by column to birdie_bank

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = 'a1b2c3d4e5f6'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    if 'birdie_bank' in inspector.get_table_names():
        existing_cols = [c['name'] for c in inspector.get_columns('birdie_bank')]
        if 'purchased_by' not in existing_cols:
            op.add_column('birdie_bank', sa.Column('purchased_by', sa.Integer(), sa.ForeignKey('players.id'), nullable=True))


def downgrade():
    inspector = Inspector.from_engine(op.get_bind())
    if 'birdie_bank' in inspector.get_table_names():
        existing_cols = [c['name'] for c in inspector.get_columns('birdie_bank')]
        if 'purchased_by' in existing_cols:
            op.drop_column('birdie_bank', 'purchased_by')
