"""Add BadmintonTrivia table

Revision ID: 9e4f33afbfce
Revises: h9c0d1e2f3a4
Create Date: 2026-03-19 21:33:47.456483

"""
from alembic import op
import sqlalchemy as sa
from alembic.operations import ops
from sqlalchemy import inspect as sa_inspect


# revision identifiers, used by Alembic.
revision = '9e4f33afbfce'
down_revision = 'h9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa_inspect(op.get_bind())
    existing_tables = inspector.get_table_names()
    if 'badminton_trivia' not in existing_tables:
        op.create_table('badminton_trivia',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('trivia', sa.Text(), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    op.drop_table('badminton_trivia')
