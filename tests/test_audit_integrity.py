from datetime import datetime, timezone
import os
from unittest.mock import patch
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.consent import ConsentCategory
from app.repositories.audit_repository import audit_repository
from app.services.audit_service import audit_service


# Dedicated SQLite engine for migration & audit trigger tests
SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture
def migrated_db():
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    conn = engine.connect()

    cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic.ini",
    )
    cfg = Config(cfg_path)
    cfg.attributes["connection"] = conn

    # Run migrations to head
    command.upgrade(cfg, "head")

    Session = sessionmaker(autocommit=False, autoflush=False, bind=conn)
    session = Session()

    yield session, conn

    session.close()
    conn.close()
    engine.dispose()


@pytest.fixture
def client(migrated_db):
    session, _ = migrated_db

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with patch("app.main.init_db", lambda: None), \
         patch("app.main.start_scheduler", lambda: None), \
         patch("app.main.stop_scheduler", lambda: None), \
         patch("app.ml_models.model_inference.warm_up", lambda: None):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


def test_migrations_create_audit_table_and_triggers(migrated_db):
    session, conn = migrated_db
    # Verify triggers exist in sqlite_master
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='trigger'")
    ).fetchall()
    trigger_names = [r[0] for r in result]
    assert "audit_logs_no_update" in trigger_names
    assert "audit_logs_no_delete" in trigger_names


def test_audit_hash_chain_creation(migrated_db):
    session, _ = migrated_db
    e1 = audit_repository.create(
        session,
        user_id=1,
        action="USER_LOGIN",
        data_type="auth",
        reason="Login success",
    )
    assert e1.prev_hash == "GENESIS"
    assert len(e1.integrity_hash) == 64

    e2 = audit_repository.create(
        session,
        user_id=1,
        action="EVENT_CREATED",
        data_type="calendar",
        reason="Created meeting",
    )
    assert e2.prev_hash == e1.integrity_hash
    assert len(e2.integrity_hash) == 64

    # Verify chain
    res = audit_service.verify(session)
    assert res["valid"] is True
    assert res["total_records"] == 2
    assert res["broken_at_id"] is None


def test_audit_log_trigger_blocks_update(migrated_db):
    session, conn = migrated_db
    e1 = audit_repository.create(
        session,
        user_id=1,
        action="USER_LOGIN",
        data_type="auth",
        reason="Login success",
    )

    with pytest.raises(Exception) as exc_info:
        conn.execute(
            text(f"UPDATE audit_logs SET reason = 'Tampered' WHERE id = {e1.id}")
        )
    assert "AuditLog is append-only" in str(exc_info.value)


def test_audit_log_trigger_blocks_delete(migrated_db):
    session, conn = migrated_db
    e1 = audit_repository.create(
        session,
        user_id=1,
        action="USER_LOGIN",
        data_type="auth",
        reason="Login success",
    )

    with pytest.raises(Exception) as exc_info:
        conn.execute(
            text(f"DELETE FROM audit_logs WHERE id = {e1.id}")
        )
    assert "AuditLog is append-only" in str(exc_info.value)


def test_audit_tampering_detected_if_trigger_dropped(migrated_db):
    session, conn = migrated_db
    e1 = audit_repository.create(
        session,
        user_id=1,
        action="USER_LOGIN",
        data_type="auth",
        reason="Legitimate login",
    )
    e2 = audit_repository.create(
        session,
        user_id=1,
        action="EVENT_CREATED",
        data_type="calendar",
        reason="Legitimate event",
    )

    # An attacker with DB admin privileges drops the trigger and alters data
    conn.execute(text("DROP TRIGGER audit_logs_no_update"))
    conn.execute(
        text(f"UPDATE audit_logs SET reason = 'Unauthorized Modification' WHERE id = {e1.id}")
    )
    session.expire_all()

    # The cryptographic hash chain detects the modification
    res = audit_service.verify(session)
    assert res["valid"] is False
    assert res["broken_at_id"] == e1.id
    assert "Tampering detected" in res["message"]


def test_audit_deletion_detected_if_trigger_dropped(migrated_db):
    session, conn = migrated_db
    e1 = audit_repository.create(session, user_id=1, action="A1", data_type="auth", reason="R1")
    e2 = audit_repository.create(session, user_id=1, action="A2", data_type="auth", reason="R2")
    e3 = audit_repository.create(session, user_id=1, action="A3", data_type="auth", reason="R3")

    # Attacker drops delete trigger and removes middle record
    conn.execute(text("DROP TRIGGER audit_logs_no_delete"))
    conn.execute(text(f"DELETE FROM audit_logs WHERE id = {e2.id}"))
    session.expire_all()

    # Chain verification fails on e3 because e3.prev_hash != e1.integrity_hash
    res = audit_service.verify(session)
    assert res["valid"] is False
    assert res["broken_at_id"] == e3.id
    assert "Broken chain" in res["message"]


def test_audit_verify_api_endpoint(client):
    # Register and login
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pw"}).json()["access_token"]

    # Verify endpoint
    v_resp = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v_resp.status_code == 200
    data = v_resp.json()
    assert data["valid"] is True
    assert data["total_records"] >= 1
    assert data["broken_at_id"] is None


def test_audit_verify_api_unauthenticated(client):
    res = client.get("/api/v1/audit/verify")
    assert res.status_code == 401


def test_audit_chain_tamper_detected_via_api(client, migrated_db):
    session, conn = migrated_db
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pw"}).json()["access_token"]

    first_log = session.query(AuditLog).first()
    assert first_log is not None

    # Tamper with row
    conn.execute(text("DROP TRIGGER audit_logs_no_update"))
    conn.execute(text(f"UPDATE audit_logs SET action = 'TAMPERED_ACTION' WHERE id = {first_log.id}"))
    session.expire_all()

    # Verify through API
    v_resp = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert v_resp.status_code == 200
    data = v_resp.json()
    assert data["valid"] is False
    assert data["broken_at_id"] == first_log.id


def test_audit_empty_table_verifies_cleanly(migrated_db):
    session, _ = migrated_db
    res = audit_service.verify(session)
    assert res["valid"] is True
    assert res["total_records"] == 0
    assert res["broken_at_id"] is None
