"""Add activity_logs table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    if 'activity_logs' not in inspector.get_table_names():
        op.create_table('activity_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('timestamp', sa.DateTime(), nullable=True, index=True),
            sa.Column('user_type', sa.String(20), nullable=False),
            sa.Column('user_name', sa.String(100), nullable=False),
            sa.Column('action', sa.String(50), nullable=False, index=True),
            sa.Column('entity_type', sa.String(50), nullable=True),
            sa.Column('entity_id', sa.Integer(), nullable=True),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('ip_address', sa.String(45), nullable=True),
        )
        op.create_index('idx_activity_log_ts_action', 'activity_logs', ['timestamp', 'action'])


def downgrade():
    inspector = Inspector.from_engine(op.get_bind())
    if 'activity_logs' in inspector.get_table_names():
        op.drop_table('activity_logs')
