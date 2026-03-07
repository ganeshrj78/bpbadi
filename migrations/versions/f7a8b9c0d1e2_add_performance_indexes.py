"""Add performance indexes on hot columns

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-03-06

"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
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
        ('ix_attendance_session_id',  'attendance',     ['session_id']),
        ('ix_attendance_player_id',   'attendance',     ['player_id']),
        ('ix_attendance_status',      'attendance',     ['status']),
        ('ix_payment_player_id',      'payment',        ['player_id']),
        ('ix_payment_amount',         'payment',        ['amount']),
        ('ix_dropout_refund_session',  'dropout_refund', ['session_id']),
        ('ix_dropout_refund_player',   'dropout_refund', ['player_id']),
        ('ix_dropout_refund_status',   'dropout_refund', ['status']),
        ('ix_session_date',           'session',        ['date']),
        ('ix_session_is_archived',    'session',        ['is_archived']),
        ('ix_court_session_id',       'court',          ['session_id']),
    ]
    for name, table, cols in indexes:
        if not _index_exists(conn, name):
            op.create_index(name, table, cols)


def downgrade():
    indexes = [
        ('ix_attendance_session_id',  'attendance'),
        ('ix_attendance_player_id',   'attendance'),
        ('ix_attendance_status',      'attendance'),
        ('ix_payment_player_id',      'payment'),
        ('ix_payment_amount',         'payment'),
        ('ix_dropout_refund_session',  'dropout_refund'),
        ('ix_dropout_refund_player',   'dropout_refund'),
        ('ix_dropout_refund_status',   'dropout_refund'),
        ('ix_session_date',           'session'),
        ('ix_session_is_archived',    'session'),
        ('ix_court_session_id',       'court'),
    ]
    for name, table in indexes:
        op.drop_index(name, table_name=table)
