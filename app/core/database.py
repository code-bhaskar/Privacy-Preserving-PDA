import os
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_migrated() -> None:
    """Verify that the database has been migrated to the head revision."""
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()

        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "alembic.ini",
        )
        cfg = Config(cfg_path)
        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        if current_rev != head_rev:
            raise RuntimeError(
                f"Database is not migrated to head revision (current={current_rev}, head={head_rev}). "
                f"Run 'alembic upgrade head' before starting the application."
            )


def init_db() -> None:
    check_db_migrated()
