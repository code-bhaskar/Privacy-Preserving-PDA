from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# In-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import InvalidCredentialsError
from app.main import app
from app.models.base import Base
from app.models.consent import ConsentCategory
from app.models.user import User


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with patch("app.main.init_db", lambda: None), \
         patch("app.main.start_scheduler", lambda: None), \
         patch("app.main.stop_scheduler", lambda: None), \
         patch("app.ml_models.model_inference.warm_up", lambda: None):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


# ---------------- Auth Primitives Tests ----------------

def test_password_hash_and_verify():
    pwd = "my_secure_password_123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_password_empty():
    hashed = hash_password("")
    assert verify_password("", hashed) is True
    assert verify_password("a", hashed) is False


def test_password_72_byte_truncation():
    base = "a" * 72
    hashed = hash_password(base + "extra_bytes")
    assert verify_password(base, hashed) is True
    assert verify_password(base + "different_extra", hashed) is True


def test_jwt_token_roundtrip():
    token = create_access_token({"sub": "42"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_jwt_token_expiry():
    expired_token = create_access_token({"sub": "42"}, expires_delta=timedelta(seconds=-10))
    with pytest.raises(InvalidCredentialsError):
        decode_access_token(expired_token)


def test_jwt_invalid_token():
    with pytest.raises(InvalidCredentialsError):
        decode_access_token("invalid.token.payload")


def test_jwt_tampered_signature():
    token = create_access_token({"sub": "42"})
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1] + ".tampered"
    with pytest.raises(InvalidCredentialsError):
        decode_access_token(tampered)


def test_jwt_wrong_secret():
    wrong_token = jwt.encode({"sub": "42"}, "wrong-secret-key", algorithm="HS256")
    with pytest.raises(InvalidCredentialsError):
        decode_access_token(wrong_token)


def test_jwt_missing_sub():
    no_sub = jwt.encode({"other": "claim"}, settings.JWT_SECRET, algorithm="HS256")
    payload = decode_access_token(no_sub)
    assert "sub" not in payload


# ---------------- User Registration & Authentication ----------------

def test_user_registration(client):
    res = client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert "password" not in data
    assert "password_hash" not in data


def test_user_registration_duplicate_email(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res = client.post("/api/v1/users", json={"name": "Alice 2", "email": "alice@example.com", "password": "pw2"})
    assert res.status_code == 400


def test_login_success(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pw"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password"


def test_login_unknown_email_uniform_message(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res_wrong_pwd = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "wrong"})
    res_unknown_email = client.post("/api/v1/login", json={"email": "nobody@example.com", "password": "pw"})
    assert res_unknown_email.status_code == 401
    assert res_wrong_pwd.json()["detail"] == res_unknown_email.json()["detail"]


# ---------------- OAuth2 password grant (Swagger UI "Authorize" dialog) ----------------
# Swagger UI implements the OAuth2 password flow by POSTing form-encoded
# username/password to the token URL. These tests pin that contract.

def test_login_oauth2_password_grant_form(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    # Exact shape of Swagger UI's Authorize request: urlencoded form with
    # username + password (+ empty scope)
    res = client.post(
        "/api/v1/login",
        data={"username": "alice@example.com", "password": "pw", "scope": ""},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Token issued via the OAuth2 flow works on protected routes
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_login_oauth2_password_grant_email_field(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res = client.post("/api/v1/login", data={"email": "alice@example.com", "password": "pw"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_oauth2_password_grant_wrong_password(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res = client.post("/api/v1/login", data={"username": "alice@example.com", "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password"


def test_login_oauth2_password_grant_missing_credentials_rejected(client):
    # Missing password -> 422 (same validation semantics as the JSON path)
    res = client.post("/api/v1/login", data={"username": "alice@example.com"})
    assert res.status_code == 422
    # Missing email/username -> 422
    res = client.post("/api/v1/login", data={"password": "pw"})
    assert res.status_code == 422
    # Non-email username -> 422
    res = client.post("/api/v1/login", data={"username": "not-an-email", "password": "pw"})
    assert res.status_code == 422


def test_login_multipart_form(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    res = client.post(
        "/api/v1/login",
        data={"username": "alice@example.com", "password": "pw"},
        files={},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_get_me_authenticated(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pw"}).json()["access_token"]
    res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"


def test_get_me_unauthenticated(client):
    res = client.get("/api/v1/users/me")
    assert res.status_code == 401


def test_get_me_invalid_token(client):
    res = client.get("/api/v1/users/me", headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_get_me_deleted_user_fails(client, db_session):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pw"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pw"}).json()["access_token"]
    db_session.query(User).delete()
    db_session.commit()
    res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


# ---------------- IDOR Protection Tests ----------------

def test_idor_user_read_by_id_denied(client):
    r_a = client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    a_id = r_a.json()["id"]
    client.post("/api/v1/users", json={"name": "Bob", "email": "bob@example.com", "password": "pwB"})
    token_b = client.post("/api/v1/login", json={"email": "bob@example.com", "password": "pwB"}).json()["access_token"]

    res = client.get(f"/api/v1/users/{a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert res.status_code == 404


def test_idor_user_read_own_id_allowed(client):
    r_a = client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    a_id = r_a.json()["id"]
    token_a = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]

    res = client.get(f"/api/v1/users/{a_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res.status_code == 200
    assert res.json()["id"] == a_id


def test_idor_consent_read_by_id_denied(client):
    r_a = client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    a_id = r_a.json()["id"]
    token_a = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    client.post("/api/v1/users", json={"name": "Bob", "email": "bob@example.com", "password": "pwB"})
    token_b = client.post("/api/v1/login", json={"email": "bob@example.com", "password": "pwB"}).json()["access_token"]

    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token_a}"},
                json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})

    res = client.get(f"/api/v1/consent/{a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert res.status_code == 404


def test_consent_defaults_to_deny_and_updates(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]

    # Initially empty consent list
    res = client.get("/api/v1/consent", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []

    # Setting consent granted
    c_set = client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token}"},
                        json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})
    assert c_set.status_code == 200
    assert c_set.json()["granted"] is True

    # Updating consent to false
    c_rev = client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token}"},
                        json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": False})
    assert c_rev.status_code == 200
    assert c_rev.json()["granted"] is False


def test_calendar_requires_consent(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]

    # Attempt to create event without consent
    res = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Test", "start_time": datetime.now(timezone.utc).isoformat()},
    )
    assert res.status_code == 403


def test_calendar_crud_and_isolation(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token_a = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token_a}"},
                json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})

    client.post("/api/v1/users", json={"name": "Bob", "email": "bob@example.com", "password": "pwB"})
    token_b = client.post("/api/v1/login", json={"email": "bob@example.com", "password": "pwB"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token_b}"},
                json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})

    # Alice creates event
    now = datetime.now(timezone.utc)
    ev = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"title": "Team Standup", "start_time": now.isoformat()},
    ).json()
    ev_id = ev["id"]

    # Bob cannot see it
    b_evs = client.get("/api/v1/events", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert len(b_evs) == 0

    # Bob cannot update it -> 404
    upd = client.put(f"/api/v1/events/{ev_id}", headers={"Authorization": f"Bearer {token_b}"}, json={"title": "Tamper"})
    assert upd.status_code == 404

    # Bob cannot delete it -> 404
    d = client.delete(f"/api/v1/events/{ev_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert d.status_code == 404

    # Alice can update it
    a_upd = client.put(f"/api/v1/events/{ev_id}", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "Updated"})
    assert a_upd.status_code == 200
    assert a_upd.json()["title"] == "Updated"

    # Alice can delete it
    a_del = client.delete(f"/api/v1/events/{ev_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert a_del.status_code == 200


def test_calendar_unauthenticated(client):
    assert client.get("/api/v1/events").status_code == 401
    assert client.post("/api/v1/events", json={"title": "X", "start_time": "2026-08-27T00:00:00"}).status_code == 401
    assert client.put("/api/v1/events/1", json={"title": "X"}).status_code == 401
    assert client.delete("/api/v1/events/1").status_code == 401


def test_reminders_requires_consent(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    res = client.post(
        "/api/v1/reminders",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "Buy groceries", "due_time": datetime.now(timezone.utc).isoformat()},
    )
    assert res.status_code == 403


def test_reminders_crud_and_isolation(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token_a = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token_a}"},
                json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})

    client.post("/api/v1/users", json={"name": "Bob", "email": "bob@example.com", "password": "pwB"})
    token_b = client.post("/api/v1/login", json={"email": "bob@example.com", "password": "pwB"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token_b}"},
                json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})

    # Alice creates reminder
    r = client.post(
        "/api/v1/reminders",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"text": "Call doctor", "due_time": datetime.now(timezone.utc).isoformat()},
    ).json()
    r_id = r["id"]

    # Bob lists reminders -> empty
    assert client.get("/api/v1/reminders", headers={"Authorization": f"Bearer {token_b}"}).json() == []

    # Bob update / delete -> 404
    assert client.put(f"/api/v1/reminders/{r_id}", headers={"Authorization": f"Bearer {token_b}"}, json={"text": "X"}).status_code == 404
    assert client.delete(f"/api/v1/reminders/{r_id}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404

    # Alice update / delete
    assert client.put(f"/api/v1/reminders/{r_id}", headers={"Authorization": f"Bearer {token_a}"}, json={"status": "completed"}).status_code == 200
    assert client.delete(f"/api/v1/reminders/{r_id}", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200


def test_reminders_unauthenticated(client):
    assert client.get("/api/v1/reminders").status_code == 401
    assert client.post("/api/v1/reminders", json={"text": "X", "due_time": "2026-08-27T00:00:00"}).status_code == 401
    assert client.put("/api/v1/reminders/1", json={"text": "X"}).status_code == 401
    assert client.delete("/api/v1/reminders/1").status_code == 401


def test_assistant_command_without_consent(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    res = client.post(
        "/api/v1/assistant/command",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "hello"},
    )
    assert res.status_code == 403


def test_assistant_command_with_consent(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token}"},
                json={"category": ConsentCategory.ASSISTANT_NLU.value, "granted": True})

    res = client.post(
        "/api/v1/assistant/command",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "hello"},
    )
    assert res.status_code == 200
    assert res.json()["processing_location"] == "local"


def test_summarization_without_consent(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    res = client.post(
        "/api/v1/messages/summarize",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"sender": "Bob", "content": "Hello"}], "persist": True},
    )
    assert res.status_code == 403


def test_summarization_with_consent(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token}"},
                json={"category": ConsentCategory.MESSAGE_SUMMARIZATION.value, "granted": True})

    res = client.post(
        "/api/v1/messages/summarize",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"sender": "Bob", "content": "Hello there."}], "persist": True},
    )
    assert res.status_code == 200
    assert res.json()["raw_content_transmitted_externally"] is False


def test_audit_logs_unauthenticated(client):
    res = client.get("/api/v1/audit")
    assert res.status_code == 401


def test_audit_logs_scoped_to_current_user(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token_a = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    me_a = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token_a}"}).json()

    client.post("/api/v1/users", json={"name": "Bob", "email": "bob@example.com", "password": "pwB"})
    token_b = client.post("/api/v1/login", json={"email": "bob@example.com", "password": "pwB"}).json()["access_token"]
    me_b = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token_b}"}).json()

    logs_a = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token_a}"}).json()
    for entry in logs_a:
        assert entry["user_id"] == me_a["id"]

    logs_b = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token_b}"}).json()
    for entry in logs_b:
        assert entry["user_id"] == me_b["id"]


def test_federated_routes_unauthenticated(client):
    assert client.post("/api/v1/federated/round", json={"rounds": 1}).status_code == 401
    assert client.post("/api/v1/federated/experiment", json={"rounds": 1}).status_code == 401
    assert client.get("/api/v1/federated/results").status_code == 401


def test_federated_round_honest_refusal_when_no_clients(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token}"},
                json={"category": ConsentCategory.FEDERATED_TRAINING.value, "granted": True})

    res = client.post(
        "/api/v1/federated/round",
        headers={"Authorization": f"Bearer {token}"},
        json={"rounds": 1, "n_clients": 3},
    )
    assert res.status_code == 400
    assert "No federated learning clients connected" in res.json()["detail"]


def test_federated_experiment_honest_refusal_when_no_clients(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice@example.com", "password": "pwA"})
    token = client.post("/api/v1/login", json={"email": "alice@example.com", "password": "pwA"}).json()["access_token"]

    res = client.post(
        "/api/v1/federated/experiment",
        headers={"Authorization": f"Bearer {token}"},
        json={"rounds": 1, "n_clients": 3},
    )
    assert res.status_code == 400
    assert "No federated learning clients connected" in res.json()["detail"]


def test_logout_revokes_token(client):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice_logout@test.com", "password": "pw"})
    token = client.post("/api/v1/login", json={"email": "alice_logout@test.com", "password": "pw"}).json()["access_token"]

    # Verify authenticated call works
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Logout
    logout_res = client.post("/api/v1/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # Subsequent request with revoked token fails with 401
    post_logout_res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert post_logout_res.status_code == 401
    assert "revoked" in post_logout_res.json()["detail"]


def test_login_rate_limiting(client):
    # Attempt 5 wrong logins
    for _ in range(5):
        client.post("/api/v1/login", json={"email": "brute_force@test.com", "password": "wrong"})

    # 6th attempt is throttled with 429
    throttled = client.post("/api/v1/login", json={"email": "brute_force@test.com", "password": "wrong"})
    assert throttled.status_code == 429
    assert "locked" in throttled.json()["detail"]


def test_raw_db_encryption_at_rest(client, db_session):
    client.post("/api/v1/users", json={"name": "Alice", "email": "alice_enc@test.com", "password": "pw"})
    token = client.post("/api/v1/login", json={"email": "alice_enc@test.com", "password": "pw"}).json()["access_token"]
    client.post("/api/v1/consent", headers={"Authorization": f"Bearer {token}"},
                json={"category": ConsentCategory.CALENDAR_DATA.value, "granted": True})

    # Create event and reminder
    ev_resp = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "TOP_SECRET_EVENT_TITLE", "start_time": datetime.now(timezone.utc).isoformat()},
    )
    assert ev_resp.status_code == 201
    assert ev_resp.json()["title"] == "TOP_SECRET_EVENT_TITLE"

    rem_resp = client.post(
        "/api/v1/reminders",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "TOP_SECRET_REMINDER_TEXT", "due_time": datetime.now(timezone.utc).isoformat()},
    )
    assert rem_resp.status_code == 201
    assert rem_resp.json()["text"] == "TOP_SECRET_REMINDER_TEXT"

    # Direct query against DB verifies raw columns are encrypted
    from app.models.calendar_event import CalendarEvent
    from app.models.reminder import Reminder

    raw_ev = db_session.query(CalendarEvent).filter(CalendarEvent.id == ev_resp.json()["id"]).first()
    raw_rem = db_session.query(Reminder).filter(Reminder.id == rem_resp.json()["id"]).first()

    assert "TOP_SECRET" not in raw_ev.title
    assert "TOP_SECRET" not in raw_rem.text


def test_validate_security_keys_boot_refusal(monkeypatch):
    from app.core.security import validate_security_keys

    # Missing JWT secret
    monkeypatch.setattr(settings, "JWT_SECRET", None)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", None)
    with pytest.raises(RuntimeError, match="Missing JWT secret key"):
        validate_security_keys()

    # Missing AES key
    monkeypatch.setattr(settings, "JWT_SECRET", "validsecret12345678901234567890")
    monkeypatch.setattr(settings, "AES_MASTER_KEY", None)
    with pytest.raises(RuntimeError, match="Missing AES master key"):
        validate_security_keys()
