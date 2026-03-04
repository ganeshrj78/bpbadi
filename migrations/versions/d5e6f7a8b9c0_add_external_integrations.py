"""Add external_integrations table for encrypted third-party credentials

Revision ID: d5e6f7a8b9c0
Revises: c4d2e3f6a7b8
Create Date: 2026-03-04

"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8b9c0'
down_revision = 'c4d2e3f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'external_integrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('password', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )


def downgrade():
    op.drop_table('external_integrations')
