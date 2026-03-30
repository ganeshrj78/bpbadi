"""add expense_category to birdie_bank

Revision ID: k2f3a4b5c6d7
Revises: j1e2f3a4b5c6
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Inspector

# revision identifiers
revision = 'k2f3a4b5c6d7'
down_revision = 'j1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('birdie_bank')]
    if 'expense_category' not in existing_cols:
        op.add_column('birdie_bank', sa.Column('expense_category', sa.String(50), nullable=True))


def downgrade():
    op.drop_column('birdie_bank', 'expense_category')
