"""audit_append_only_trigger

Revision ID: b1a7c3d9e042
Revises: a1b2c3d4e5f6
Create Date: 2026-08-27 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1a7c3d9e042'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        # PostgreSQL trigger function
        op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'AuditLog is append-only: updates and deletes are prohibited';
        END;
        $$ LANGUAGE plpgsql;
        """)

        op.execute("""
        CREATE TRIGGER audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
        """)

        op.execute("""
        CREATE TRIGGER audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
        """)

    elif dialect_name == "sqlite":
        # SQLite triggers
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        BEGIN
            SELECT RAISE(FAIL, 'AuditLog is append-only: updates are prohibited');
        END;
        """)

        op.execute("""
        CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        BEGIN
            SELECT RAISE(FAIL, 'AuditLog is append-only: deletes are prohibited');
        END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs;")
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_modification();")
    elif dialect_name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update;")
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete;")
