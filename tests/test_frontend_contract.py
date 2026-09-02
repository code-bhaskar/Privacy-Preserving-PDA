"""Contract tests for the Angular demonstration frontend.

The demo UI (`frontend/`) renders fields straight from these endpoints. A renamed
or missing key does not fail loudly in a browser — it silently renders "—" or an
empty table, usually in the middle of a presentation. These tests pin the exact
shape the templates read, so a backend refactor cannot quietly break the demo.

They also cover the single-pipeline federated learning controls
(`/api/v1/federated/pipeline/*`) that let the UI drive dataset preparation, client
processes, rounds, the ε-sweep and ONNX export through the one FastAPI app.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402

DEMO_EMAIL = "contract@ppda.io"
DEMO_PASSWORD = "ContractPass123!"

# The seven coordinator phases the UI renders as a state-machine strip.
EXPECTED_PHASES = [
    "IDLE", "ADVERTISE_KEYS", "SHARE_KEYS", "COLLECT",
    "UNMASK", "AGGREGATING", "DONE",
]

# Every posture status the UI knows how to colour. An unknown status silently
# renders as a grey pill, which is how overclaiming creeps back in.
EXPECTED_POSTURE_STATUSES = {
    "IMPLEMENTED", "DEPLOYMENT_REQUIREMENT", "ARCHITECTURE_ONLY",
    "FUTURE_WORK", "NOT_IMPLEMENTED", "NOT_DONE",
}

CONSENT_CATEGORIES = [
    "assistant_nlu", "calendar_data", "message_summarization", "federated_training",
]


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


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
         patch("app.main.fl_pipeline_shutdown", lambda: None), \
         patch("app.ml_models.model_inference.warm_up", lambda: None):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    """A registered, logged-in, fully-consented user + bearer headers."""
    client.post("/api/v1/users", json={
        "name": "Contract User", "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD, "preferences": {},
    })
    token = client.post("/api/v1/login", json={
        "email": DEMO_EMAIL, "password": DEMO_PASSWORD,
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    for category in CONSENT_CATEGORIES:
        client.post("/api/v1/consent", json={"category": category, "granted": True},
                    headers=headers)
    return headers


def assert_fields(payload, fields, where):
    """Every field the template binds must exist (None is fine, absent is not)."""
    assert isinstance(payload, dict), f"{where}: expected object, got {type(payload).__name__}"
    missing = [f for f in fields if f not in payload]
    assert not missing, f"{where}: missing field(s) {missing}; present={sorted(payload)}"


# --------------------------------------------------------------------------- #
# shell / auth
# --------------------------------------------------------------------------- #

def test_health_shape(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and "app" in body


def test_login_returns_token_used_by_interceptor(client):
    client.post("/api/v1/users", json={
        "name": "T", "email": DEMO_EMAIL, "password": DEMO_PASSWORD, "preferences": {},
    })
    res = client.post("/api/v1/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    # The navbar decodes this client-side and shows `sub` + `exp`.
    header, payload, signature = body["access_token"].split(".")
    assert header and payload and signature


def test_users_me_shape(client, auth):
    body = client.get("/api/v1/users/me", headers=auth).json()
    assert_fields(body, ["id", "name", "email", "preferences", "created_at"], "/users/me")


def test_consent_list_covers_the_four_ui_switches(client, auth):
    body = client.get("/api/v1/consent", headers=auth).json()
    assert isinstance(body, list)
    for row in body:
        assert_fields(row, ["id", "user_id", "category", "granted", "created_at"], "/consent row")
    assert {r["category"] for r in body} == set(CONSENT_CATEGORIES)


def test_consent_toggle_round_trip(client, auth):
    res = client.post("/api/v1/consent",
                      json={"category": "assistant_nlu", "granted": False}, headers=auth)
    assert res.status_code == 200 and res.json()["granted"] is False
    res = client.post("/api/v1/consent",
                      json={"category": "assistant_nlu", "granted": True}, headers=auth)
    assert res.json()["granted"] is True


def test_logout_revokes_token_so_shell_resets(client, auth):
    from app.core.auth import _REVOKED_TOKENS
    try:
        assert client.post("/api/v1/logout", headers=auth).status_code == 200
        assert client.get("/api/v1/users/me", headers=auth).status_code == 401
    finally:
        # The blocklist is an in-memory set keyed on the token string. Tokens are
        # only second-granular, so an identical token minted by a later test would
        # otherwise inherit this revocation. Clear it to keep tests independent.
        _REVOKED_TOKENS.clear()


def test_tokens_minted_in_the_same_second_are_identical(client, auth):
    """Documents a real consequence of second-granular `exp`.

    `create_access_token` puts an integer-seconds `exp` in the payload, so two
    logins for the same user inside one second produce byte-identical JWTs. The
    revocation blocklist keys on that string, which means logging out also
    revokes any other token issued to that user in the same second. The frontend
    treats any 401 as "session gone" and returns to the login screen, so this is
    safe for the demo — but it is asserted here so nobody is surprised by it.
    """
    from app.core.auth import _REVOKED_TOKENS, create_access_token
    try:
        first = create_access_token({"sub": "1"})
        second = create_access_token({"sub": "1"})
        assert first == second, "expected identical JWTs within the same second"
        _REVOKED_TOKENS.add(first)
        assert client.get("/api/v1/users/me",
                          headers={"Authorization": f"Bearer {second}"}).status_code == 401
    finally:
        _REVOKED_TOKENS.clear()


def test_unauthenticated_pipeline_calls_are_rejected(client):
    """No token → 401, never a leaked process/dataset listing."""
    for path in ("/api/v1/federated/pipeline/status",
                 "/api/v1/federated/pipeline/clients",
                 "/api/v1/federated/pipeline/sweep/status",
                 "/api/v1/federated/pipeline/dataset/status"):
        assert client.get(path).status_code == 401, path


# --------------------------------------------------------------------------- #
# IDOR probe panel
# --------------------------------------------------------------------------- #

def test_idor_probe_returns_404_with_string_detail(client, auth):
    """The UI asserts `HTTP 404` and prints `detail` verbatim."""
    me_res = client.get("/api/v1/users/me", headers=auth)
    assert me_res.status_code == 200, f"/users/me -> {me_res.status_code}: {me_res.text}"
    me = me_res.json()
    res = client.get(f"/api/v1/users/{me['id'] + 9999}", headers=auth)
    assert res.status_code == 404, f"probe -> {res.status_code}: {res.text}"
    detail = res.json()["detail"]
    assert isinstance(detail, str) and detail


def test_own_user_id_is_readable(client, auth):
    me = client.get("/api/v1/users/me", headers=auth).json()
    assert client.get(f"/api/v1/users/{me['id']}", headers=auth).status_code == 200


# --------------------------------------------------------------------------- #
# calendar / reminders panel
# --------------------------------------------------------------------------- #

def test_event_crud_shape(client, auth):
    start = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    created = client.post("/api/v1/events", json={
        "title": "Budget review", "start_time": start, "end_time": end,
        "participant": "Priya",
    }, headers=auth)
    assert created.status_code == 201
    ev = created.json()
    assert_fields(ev, ["id", "user_id", "title", "participant",
                       "start_time", "end_time", "created_via"], "event")
    assert ev["title"] == "Budget review"   # decrypted for the owner

    listed = client.get("/api/v1/events", headers=auth).json()
    assert any(e["id"] == ev["id"] for e in listed)

    updated = client.put(f"/api/v1/events/{ev['id']}",
                         json={"title": "Budget review v2"}, headers=auth)
    assert updated.json()["title"] == "Budget review v2"

    assert client.delete(f"/api/v1/events/{ev['id']}", headers=auth).status_code == 200
    assert all(e["id"] != ev["id"] for e in client.get("/api/v1/events", headers=auth).json())


def test_reminder_crud_shape(client, auth):
    due = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    created = client.post("/api/v1/reminders",
                          json={"text": "Submit checklist", "due_time": due}, headers=auth)
    assert created.status_code == 201
    rem = created.json()
    assert_fields(rem, ["id", "user_id", "text", "due_time", "status"], "reminder")
    assert rem["status"] == "pending"

    done = client.put(f"/api/v1/reminders/{rem['id']}", json={"status": "done"}, headers=auth)
    assert done.json()["status"] == "done"

    assert client.delete(f"/api/v1/reminders/{rem['id']}", headers=auth).status_code == 200


def test_assistant_created_event_is_flagged_in_the_ui(client, auth):
    """The table shows a 'via assistant' pill, so created_via must say so.

    The classifier is pinned because the test fixture skips `warm_up()`, which
    would otherwise leave the ONNX model cold and fall back to TF-IDF (whose
    verdict on this sentence is not the point of this test — the created_via
    contract is). ONNX accuracy itself is covered by tests/test_intent_model.py.
    """
    with patch("app.services.assistant_service.model_inference.classify",
               return_value=("SCHEDULE_EVENT", 0.99)):
        res = client.post("/api/v1/assistant/command", json={
            "text": "schedule a meeting with john tomorrow at 10",
        }, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "SCHEDULE_EVENT"
    assert body["action_taken"] == "event_created"
    assert body["result"]["id"] > 0

    events = client.get("/api/v1/events", headers=auth).json()
    created = [e for e in events if e["id"] == body["result"]["id"]]
    assert created, "assistant-created event missing from GET /events"
    assert created[0]["created_via"] == "assistant"


# --------------------------------------------------------------------------- #
# assistant panel
# --------------------------------------------------------------------------- #

def test_assistant_command_shape_including_saliency(client, auth):
    res = client.post("/api/v1/assistant/command", json={
        "text": "remind me to submit the report tomorrow at 6",
    }, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert_fields(body, ["intent", "confidence", "requires_ml", "entities",
                         "action_taken", "result", "processing_location",
                         "explanation"], "/assistant/command")
    assert body["processing_location"] == "local"
    assert 0.0 <= body["confidence"] <= 1.0

    ex = body["explanation"]
    assert_fields(ex, ["method", "top_tokens"], "explanation")
    assert ex["top_tokens"], "UI renders one saliency bar per token"
    for tok in ex["top_tokens"]:
        # The bar width and the +/- number both read `contribution`.
        assert "token" in tok and "contribution" in tok, tok
        assert isinstance(tok["contribution"], (int, float))


def test_assistant_command_without_consent_is_403_with_string(client):
    """The UI prints this detail in the chat feed as an error line."""
    fresh = TestClient(app)
    client.post("/api/v1/users", json={
        "name": "No Consent", "email": "noconsent@ppda.io",
        "password": DEMO_PASSWORD, "preferences": {},
    })
    token = client.post("/api/v1/login", json={
        "email": "noconsent@ppda.io", "password": DEMO_PASSWORD}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/assistant/command", json={"text": "hello"}, headers=headers)
    assert res.status_code == 403
    assert isinstance(res.json()["detail"], str)
    fresh.close()


def test_summarize_shape(client, auth):
    res = client.post("/api/v1/messages/summarize", json={
        "messages": [
            {"sender": "Priya", "content": "Move the budget review to Thursday 11am."},
            {"sender": "Tom", "content": "Delivery slips two weeks, demo moves to the 24th."},
        ],
        "max_sentences": 3, "persist": True,
    }, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert_fields(body, ["summary", "n_messages", "processing_location",
                         "raw_content_transmitted_externally"], "/messages/summarize")
    # The UI turns this into a green "external transmission: none" badge.
    assert body["raw_content_transmitted_externally"] is False
    assert body["n_messages"] == 2
    assert body["summary"]


# --------------------------------------------------------------------------- #
# privacy panel
# --------------------------------------------------------------------------- #

def test_encrypt_demo_shape(client, auth):
    res = client.post("/api/v1/privacy/encrypt-demo",
                      json={"plaintext": "meeting with client at 3pm"}, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert_fields(body, ["algorithm", "ciphertext_b64", "roundtrip_ok"], "/privacy/encrypt-demo")
    assert body["algorithm"] == "AES-256-GCM"
    assert body["roundtrip_ok"] is True
    assert len(body["ciphertext_b64"]) > 20
    assert "meeting with client" not in body["ciphertext_b64"]


def test_posture_statuses_are_all_renderable(client, auth):
    body = client.get("/api/v1/privacy/posture", headers=auth).json()
    assert isinstance(body, list) and len(body) >= 8
    unknown = set()
    for row in body:
        assert_fields(row, ["technology", "status", "notes"], "posture row")
        if row["status"] not in EXPECTED_POSTURE_STATUSES:
            unknown.add(row["status"])
    assert not unknown, f"UI has no colour for posture status(es): {unknown}"


def test_posture_advertises_the_real_stack(client, auth):
    """Guards the two claims the demo makes out loud."""
    joined = " ".join(r["notes"] for r in client.get("/api/v1/privacy/posture", headers=auth).json())
    assert "Bonawitz" in joined, "secure aggregation note should name the protocol"
    assert "occlusion" in joined.lower(), "explainability is occlusion saliency, not LIME"
    assert "Simulated" not in joined, "FL is real client processes, not a simulator"


# --------------------------------------------------------------------------- #
# audit panel
# --------------------------------------------------------------------------- #

def test_audit_verify_shape(client, auth):
    res = client.get("/api/v1/audit/verify", headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert_fields(body, ["valid", "total_records", "broken_at_id", "message"], "/audit/verify")
    assert body["valid"] is True


def test_audit_list_shape_and_hash_chain_fields(client, auth):
    client.post("/api/v1/privacy/encrypt-demo", json={"plaintext": "x" * 8}, headers=auth)
    rows = client.get("/api/v1/audit?limit=50", headers=auth).json()
    assert isinstance(rows, list) and rows
    for row in rows:
        assert_fields(row, ["id", "user_id", "action", "data_type", "reason",
                            "external_processing", "processing_location",
                            "prev_hash", "integrity_hash", "created_at"], "audit row")
    # The chain-link strip compares row[n].prev_hash to row[n-1].integrity_hash.
    ordered = sorted(rows, key=lambda r: r["id"])
    for prev, cur in zip(ordered, ordered[1:]):
        assert cur["prev_hash"] == prev["integrity_hash"], (
            f"chain break between {prev['id']} and {cur['id']}"
        )


def test_audit_reasons_do_not_leak_plaintext(client, auth):
    """The UI claims this out loud next to the reason column."""
    secret = "Zebra Quartz Vault Meeting"
    client.post("/api/v1/events", json={
        "title": secret,
        "start_time": (datetime.now(timezone.utc) + timedelta(hours=9)).isoformat(),
    }, headers=auth)
    rows = client.get("/api/v1/audit?limit=200", headers=auth).json()
    assert rows
    for row in rows:
        assert secret not in row["reason"], f"plaintext leaked in audit row {row['id']}"


# --------------------------------------------------------------------------- #
# single-pipeline federated learning controls
# --------------------------------------------------------------------------- #

def test_pipeline_status_has_every_field_the_dashboard_reads(client, auth):
    body = client.get("/api/v1/federated/pipeline/status", headers=auth).json()
    assert_fields(body, [
        "single_pipeline", "coordinator_in_process", "coordinator_url", "server_url",
        "phases", "dataset", "dataset_job", "clients", "clients_alive", "registered",
        "round", "model_dim", "model_size_bytes", "sweep", "privacy_spent", "history",
        "history_count", "results_file", "results_file_exists", "python_executable",
        "onnx_artifact", "onnx_artifact_exists", "artifacts",
    ], "/federated/pipeline/status")

    assert body["single_pipeline"] is True
    assert body["coordinator_in_process"] is True
    assert body["model_dim"] > 0
    assert body["model_size_bytes"] == body["model_dim"] * 4

    # phase strip
    assert body["phases"] == EXPECTED_PHASES
    assert_fields(body["round"], ["phase", "round_id", "config", "peer_pubkeys",
                                  "survivors", "dropped", "registered_clients",
                                  "collected"], "round")
    assert body["round"]["phase"] in EXPECTED_PHASES

    # dataset card
    assert_fields(body["dataset"], ["ready", "data_root", "num_classes", "intents",
                                    "alpha", "planned_clients", "test_samples",
                                    "shards", "total_train_samples"], "dataset")
    for shard in body["dataset"]["shards"]:
        assert_fields(shard, ["client_id", "samples"], "dataset shard")

    # dataset background job
    assert_fields(body["dataset_job"], ["running", "exit_code", "started_at",
                                        "finished_at", "log", "dataset"], "dataset_job")

    # clients card
    assert isinstance(body["clients"], list)
    for c in body["clients"]:
        assert_fields(c, ["client_id", "pid", "alive", "exit_code", "started_at",
                          "uptime_s", "drop_at", "server_url", "log_path", "shard"],
                      "supervised client")
    assert_fields(body["registered"], ["registered_clients", "clients"], "registered")
    for rc in body["registered"]["clients"]:
        assert_fields(rc, ["client_id", "num_samples", "last_seen_age_s"], "registered client")

    # sweep card + chart
    assert_fields(body["sweep"], ["running", "started_at", "finished_at", "elapsed_s",
                                  "epsilons", "rounds", "clients_per_round",
                                  "current_epsilon", "current_epsilon_label",
                                  "completed_rounds", "total_rounds", "progress_pct",
                                  "points", "rounds_log", "error"], "sweep")
    assert 0.0 <= body["sweep"]["progress_pct"] <= 100.0

    # history table
    assert isinstance(body["history"], list)
    for h in body["history"]:
        assert_fields(h, ["round_id", "round_wall_time_s", "participants", "survivors",
                          "dropped", "dropout_recovered", "test_accuracy", "test_loss",
                          "clip_norm", "noise_multiplier", "target_epsilon",
                          "privacy_spent", "bytes_per_client_uplink",
                          "total_uplink_bytes", "server_saw_plaintext_updates"],
                      "history record")
        assert h["server_saw_plaintext_updates"] is False


def test_pipeline_status_is_cheap_and_pollable(client, auth):
    """The tab polls this every 1.5s; it must not error or spawn work."""
    for _ in range(3):
        assert client.get("/api/v1/federated/pipeline/status", headers=auth).status_code == 200


def test_sweep_status_shape_before_any_sweep(client, auth):
    body = client.get("/api/v1/federated/pipeline/sweep/status", headers=auth).json()
    assert body["running"] is False
    assert body["points"] == [] and body["rounds_log"] == []
    assert body["error"] is None


def test_sweep_refuses_without_clients_instead_of_faking(client, auth):
    """Honest refusal: the UI prints `reason` in the notice banner."""
    from fl.server.coordinator import coordinator
    saved = dict(coordinator.registered)
    coordinator.registered = {}
    try:
        res = client.post("/api/v1/federated/pipeline/sweep/start", json={
            "epsilons": [None, 5.0], "rounds": 1, "clients_per_round": 3,
            "local_epochs": 1, "clip_norm": 20.0,
        }, headers=auth)
        assert res.status_code == 200
        body = res.json()
        assert body["started"] is False
        assert isinstance(body.get("reason"), str) and body["reason"]
    finally:
        coordinator.registered = saved


def test_federated_round_refuses_without_clients(client, auth):
    from fl.server.coordinator import coordinator
    saved = dict(coordinator.registered)
    coordinator.registered = {}
    try:
        res = client.post("/api/v1/federated/round", json={
            "n_clients": 3, "rounds": 1, "epsilon": 5.0, "secure_aggregation": True,
        }, headers=auth)
        assert res.status_code == 400
        assert "client" in res.json()["detail"].lower()
    finally:
        coordinator.registered = saved


def test_round_result_shape_when_it_does_run(client, auth):
    """The JSON viewer binds these exact keys from POST /federated/round."""
    from fl.pipeline.supervisor import supervisor
    from fl.server.coordinator import coordinator

    saved_registered = dict(coordinator.registered)
    saved_history = list(coordinator.history)
    saved_phase = coordinator.phase
    saved_round_id = coordinator.round_id

    class _FakeProc:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    from fl.pipeline.supervisor import _Client
    import time as _time

    fake = _Client(client_id=0, proc=_FakeProc(), log_path="/tmp/x.log",
                   started_at=_time.time(), drop_at=None,
                   server_url="http://127.0.0.1:8000", rounds=1)
    fake2 = _Client(client_id=1, proc=_FakeProc(), log_path="/tmp/y.log",
                    started_at=_time.time(), drop_at=None,
                    server_url="http://127.0.0.1:8000", rounds=1)

    coordinator.registered = {0: {"num_samples": 100, "last_seen": _time.time()},
                              1: {"num_samples": 80, "last_seen": _time.time()}}
    supervisor._clients = {0: fake, 1: fake2}

    def _instant_round(*a, **kw):
        from fl.server.coordinator import Phase
        coordinator.phase = Phase.DONE
        coordinator.history.append({
            "round_wall_time_s": 1.5, "round_id": coordinator.round_id + 1,
            "participants": [0, 1], "survivors": [0, 1], "dropped": [],
            "dropout_recovered": False, "test_accuracy": 0.8123, "test_loss": 0.4,
            "clip_norm": 20.0, "noise_multiplier": 0.0, "target_epsilon": None,
            "privacy_spent": None, "bytes_per_client_uplink": 1000,
            "total_uplink_bytes": 2000, "server_saw_plaintext_updates": False,
        })
        coordinator.round_id += 1
        coordinator.sample_counts = {0: 100, 1: 80}
        return coordinator.history[-1]

    try:
        with patch("app.services.federated_service.coordinator.start_round", _instant_round):
            res = client.post("/api/v1/federated/round", json={
                "n_clients": 2, "rounds": 1, "epsilon": None, "secure_aggregation": True,
            }, headers=auth)
        assert res.status_code == 200, res.text
        rows = res.json()
        assert len(rows) == 1
        r = rows[0]
        assert_fields(r, ["round_id", "n_clients", "dp_epsilon", "global_accuracy",
                          "latency_ms", "comm_bytes_total", "model_size_bytes",
                          "contributions"], "round result")
        assert r["contributions"], "UI renders one row per client contribution"
        for c in r["contributions"]:
            assert_fields(c, ["client_id", "n_local_samples", "payload_bytes",
                              "dp_epsilon", "masked", "raw_data_transmitted"],
                          "contribution")
            assert c["masked"] is True
            assert c["raw_data_transmitted"] is False
    finally:
        coordinator.registered = saved_registered
        coordinator.history = saved_history
        coordinator.phase = saved_phase
        coordinator.round_id = saved_round_id
        supervisor._clients = {}


def test_spawn_clients_validates_dataset_readiness(client, auth):
    """With no fl_data the UI must get an actionable message, not a stack trace."""
    with patch("app.services.pipeline_service.dataset_status", return_value={"ready": False}):
        res = client.post("/api/v1/federated/pipeline/clients/spawn",
                          json={"count": 2}, headers=auth)
    assert res.status_code == 400
    assert "prepare" in res.json()["detail"].lower()


def test_spawn_request_validation_bounds(client, auth):
    res = client.post("/api/v1/federated/pipeline/clients/spawn",
                      json={"count": 99}, headers=auth)
    assert res.status_code == 422


def test_dataset_prepare_request_validation(client, auth):
    res = client.post("/api/v1/federated/pipeline/dataset/prepare",
                      json={"clients": 1, "alpha": 0.5}, headers=auth)
    assert res.status_code == 422   # minimum 2 shards


def test_client_log_endpoint_shape_for_unknown_client(client, auth):
    body = client.get("/api/v1/federated/pipeline/clients/77/log", headers=auth).json()
    assert_fields(body, ["client_id", "found", "lines"], "client log")
    assert body["found"] is False


def test_stop_clients_with_no_clients_is_a_no_op(client, auth):
    res = client.post("/api/v1/federated/pipeline/clients/stop",
                      json={"client_ids": None}, headers=auth)
    assert res.status_code == 200
    assert res.json() == {"stopped": []}


def test_federated_results_endpoint_is_list(client, auth):
    body = client.get("/api/v1/federated/results", headers=auth).json()
    assert isinstance(body, list)
