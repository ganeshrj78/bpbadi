"""Add apply_credits boolean to sessions

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-03-08

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
    existing_cols = [c['name'] for c in inspector.get_columns('sessions')]
    if 'apply_credits' not in existing_cols:
        op.add_column('sessions', sa.Column('apply_credits', sa.Boolean(), server_default='0', nullable=True))


def downgrade():
    inspector = Inspector.from_engine(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('sessions')]
    if 'apply_credits' in existing_cols:
        op.drop_column('sessions', 'apply_credits')
