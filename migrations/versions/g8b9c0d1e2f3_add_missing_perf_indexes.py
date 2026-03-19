"""Add missing performance indexes on managed_by, voting_frozen, payment_released

Revision ID: g8b9c0d1e2f3
Revises: 99e749fe71ec
Create Date: 2026-03-19

"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = 'g8b9c0d1e2f3'
down_revision = '99e749fe71ec'
branch_labels = None
depends_on = None


def _index_exists(conn, index_name):
    inspector = Inspector.from_engine(conn)
    for table in inspector.get_table_names():
        for idx in inspector.get_indexes(table):
            if idx['name'] == index_name:
                return True
    return False


def upgrade():
    conn = op.get_bind()
    indexes = [
        ('ix_player_managed_by',          'players',   ['managed_by']),
        ('ix_session_voting_frozen',      'sessions',  ['voting_frozen']),
        ('ix_session_payment_released',   'sessions',  ['payment_released']),
        ('ix_payment_date_player',        'payments',  ['date', 'player_id']),
    ]
    for name, table, cols in indexes:
        if not _index_exists(conn, name):
            op.create_index(name, table, cols)


def downgrade():
    indexes = [
        ('ix_player_managed_by',          'players'),
        ('ix_session_voting_frozen',      'sessions'),
        ('ix_session_payment_released',   'sessions'),
        ('ix_payment_date_player',        'payments'),
    ]
    for name, table in indexes:
        op.drop_index(name, table_name=table)
