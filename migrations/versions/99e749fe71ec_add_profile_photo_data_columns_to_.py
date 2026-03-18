"""Add profile photo data columns to players

Revision ID: 99e749fe71ec
Revises: 7ce55a73152e
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '99e749fe71ec'
down_revision = '7ce55a73152e'
branch_labels = None
depends_on = None


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    existing_cols = [c['name'] for c in inspector.get_columns('players')]
    with op.batch_alter_table('players', schema=None) as batch_op:
        if 'profile_photo_data' not in existing_cols:
            batch_op.add_column(sa.Column('profile_photo_data', sa.LargeBinary(), nullable=True))
        if 'profile_photo_mime' not in existing_cols:
            batch_op.add_column(sa.Column('profile_photo_mime', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_column('profile_photo_mime')
        batch_op.drop_column('profile_photo_data')
