"""Add notifications and notification_reads tables

Revision ID: d6e7f8a9b0c1
Revises: c3d4e5f6a7b8
Create Date: 2026-03-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'd6e7f8a9b0c1'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    if not inspector.has_table('notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('type', sa.String(30), server_default='general'),
            sa.Column('target', sa.String(20), server_default='all'),
            sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id'), nullable=True),
            sa.Column('link', sa.String(255), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('players.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_notification_target_created', 'notifications', ['target', 'created_at'])
        op.create_index('idx_notification_player', 'notifications', ['player_id', 'created_at'])

    if not inspector.has_table('notification_reads'):
        op.create_table(
            'notification_reads',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('notification_id', sa.Integer(), sa.ForeignKey('notifications.id'), nullable=False),
            sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id'), nullable=False),
            sa.Column('read_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('notification_id', 'player_id', name='unique_notification_read'),
        )


def downgrade():
    op.drop_table('notification_reads')
    op.drop_table('notifications')
