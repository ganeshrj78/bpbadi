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
        ('ix_attendance_session_id',        'attendances',     ['session_id']),
        ('ix_attendance_player_id',         'attendances',     ['player_id']),
        ('ix_attendance_status',            'attendances',     ['status']),
        ('ix_attendance_session_status',    'attendances',     ['session_id', 'status']),
        ('ix_payment_player_id',            'payments',        ['player_id']),
        ('ix_payment_amount',               'payments',        ['amount']),
        ('ix_dropout_refund_session',       'dropout_refunds', ['session_id']),
        ('ix_dropout_refund_player',        'dropout_refunds', ['player_id']),
        ('ix_dropout_refund_status',        'dropout_refunds', ['status']),
        ('ix_session_date',                 'sessions',        ['date']),
        ('ix_session_is_archived',          'sessions',        ['is_archived']),
        ('ix_court_session_id',             'courts',          ['session_id']),
    ]
    for name, table, cols in indexes:
        if not _index_exists(conn, name):
            op.create_index(name, table, cols)

    # Refresh planner statistics so new indexes are used immediately
    op.execute('ANALYZE attendances; ANALYZE payments; ANALYZE sessions; ANALYZE courts; ANALYZE dropout_refunds;')


def downgrade():
    indexes = [
        ('ix_attendance_session_id',        'attendances'),
        ('ix_attendance_player_id',         'attendances'),
        ('ix_attendance_status',            'attendances'),
        ('ix_attendance_session_status',    'attendances'),
        ('ix_payment_player_id',            'payments'),
        ('ix_payment_amount',               'payments'),
        ('ix_dropout_refund_session',       'dropout_refunds'),
        ('ix_dropout_refund_player',        'dropout_refunds'),
        ('ix_dropout_refund_status',        'dropout_refunds'),
        ('ix_session_date',                 'sessions'),
        ('ix_session_is_archived',          'sessions'),
        ('ix_court_session_id',             'courts'),
    ]
    for name, table in indexes:
        op.drop_index(name, table_name=table)
