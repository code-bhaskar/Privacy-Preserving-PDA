"""resync_pk_sequences

Repairs PostgreSQL primary-key sequences that have fallen behind MAX(id)
in their tables (e.g. after a dump/restore or rows inserted with explicit
ids). A lagging sequence makes every subsequent ORM INSERT fail with
`duplicate key value violates unique constraint "<table>_pkey"`, which
surfaced as a 500 on POST /api/v1/consent (the audit-log insert collided).

Revision ID: c2d8e4f1a933
Revises: b1a7c3d9e042
Create Date: 2026-09-02 04:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c2d8e4f1a933'
down_revision: Union[str, None] = 'b1a7c3d9e042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    'users',
    'consents',
    'calendar_events',
    'reminders',
    'messages',
    'audit_logs',
    'model_updates',
    'federated_rounds',
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite AUTOINCREMENT/rowid never desyncs this way

    for table in TABLES:
        op.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,
                false
            )
            WHERE pg_get_serial_sequence('{table}', 'id') IS NOT NULL;
            """
        )


def downgrade() -> None:
    # Sequence repair is idempotent and non-destructive; nothing to undo.
    pass
