"""Database resilience helpers.

PostgreSQL primary-key sequences can fall behind ``MAX(id)`` after a
dump/restore or any INSERT with an explicit id. Every subsequent ORM insert
then dies with ``duplicate key value violates unique constraint
"<table>_pkey"``. These helpers detect that exact failure, repair the
sequence in place, and retry once — instead of surfacing an opaque 500.
"""
import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def is_pk_collision(exc: IntegrityError, table: str) -> bool:
    """True when the IntegrityError is a duplicate-key hit on the table's PK."""
    msg = str(getattr(exc, "orig", None) or exc)
    return f'"{table}_pkey"' in msg or f"{table}.id" in msg


def resync_pk_sequence(db: Session, table: str) -> bool:
    """Advance a lagging PostgreSQL identity sequence to MAX(id)+1.

    Returns True if a resync was performed (PostgreSQL only; sequence
    changes are never rolled back, so this is safe mid-transaction).
    """
    if db.get_bind().dialect.name != "postgresql":
        return False
    db.execute(
        text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,
                false
            )
            WHERE pg_get_serial_sequence('{table}', 'id') IS NOT NULL
            """
        )
    )
    logger.warning("Resynced lagging primary-key sequence for table '%s'", table)
    return True


def save_with_pk_resync(db: Session, obj) -> None:
    """db.add + commit, self-healing a lagging PK sequence exactly once."""
    table = obj.__table__.name
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not (is_pk_collision(exc, table) and resync_pk_sequence(db, table)):
            raise
        db.add(obj)
        db.commit()
    db.refresh(obj)
