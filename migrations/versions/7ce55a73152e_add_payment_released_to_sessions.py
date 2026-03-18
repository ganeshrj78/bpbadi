"""Add payment_released to sessions

Revision ID: 7ce55a73152e
Revises: d6e7f8a9b0c1
Create Date: 2026-03-17 22:08:09.369603

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '7ce55a73152e'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('sessions')]
    if 'payment_released' not in existing_cols:
        with op.batch_alter_table('sessions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('payment_released', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_column('payment_released')
