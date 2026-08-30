# HOW TO RUN THE PROJECT

**Project:** Privacy-Preserving Digital Assistant (PPDA) — Backend
**Repository:** `https://github.com/code-bhaskar/Privacy-Preserving-PDA`
**Stack:** Python 3.11 · FastAPI · PostgreSQL 18 (SQLite fallback) · Alembic · SQLAlchemy · ONNX Runtime · PyTorch · Cryptographic Federated Learning (Bonawitz et al. Secure Aggregation) · Rényi Differential Privacy
**Document version:** 1.0 — Submission guide (last updated: 2026-08-30)

This document explains, step by step, how to set up, run, test, and demonstrate
the entire project on a fresh machine. Three run paths are supported:

| Path | What you need | Best for |
|---|---|---|
| **A. Docker Compose** (easiest) | Docker + Docker Compose | Quick evaluation / demo |
| **B. Local PostgreSQL 18** | Python 3.11+, PostgreSQL 18 | **The official submission path** |
| **C. SQLite fallback** | Python 3.11+ only | Quick smoke tests (not the submission) |

---

## Table of Contents

1. [What this project is](#1-what-this-project-is)
2. [Prerequisites](#2-prerequisites)
3. [Get the source code](#3-get-the-source-code)
4. [Create the virtual environment](#4-create-the-virtual-environment)
5. [Configure environment variables (`.env`)](#5-configure-environment-variables-env)
6. [Path A — Run everything with Docker Compose](#6-path-a--run-everything-with-docker-compose)
7. [Path B — Run locally with PostgreSQL 18 (recommended submission)](#7-path-b--run-locally-with-postgresql-18-recommended-submission)
8. [Path C — Quick SQLite fallback](#8-path-c--quick-sqlite-fallback)
9. [Train / verify the ONNX intent model](#9-train--verify-the-onnx-intent-model)
10. [Explore the API (Swagger UI + endpoint reference)](#10-explore-the-api-swagger-ui--endpoint-reference)
11. [A guided demo of the security & privacy features](#11-a-guided-demo-of-the-security--privacy-features)
12. [Run the automated test suite (73 tests)](#12-run-the-automated-test-suite-73-tests)
13. [Federated Learning + Differential Privacy demo (the centerpiece)](#13-federated-learning--differential-privacy-demo-the-centerpiece)
14. [Measured results you should see](#14-measured-results-you-should-see)
15. [Project structure](#15-project-structure)
16. [Troubleshooting](#16-troubleshooting)
17. [One-page quick reference](#17-one-page-quick-reference)

---

## 1. What this project is

A **local-first, privacy-preserving personal digital assistant backend** with:

- **Zero-trust JWT authentication** (bcrypt hashing, HS256 tokens, login rate
  limiting — 5 failed attempts → HTTP 429, logout with token revocation) and
  **IDOR immunity** (cross-user access returns `404`, never leaks existence).
- **AES-256-GCM encryption at rest** for calendar event titles, reminder texts,
  and private messages (per-user AAD). The app **refuses to boot** without
  `JWT_SECRET` and a valid 32-byte `AES_MASTER_KEY`.
- **On-device-class intent classifier** (`IntentNet`, 68,103 params) served via
  **ONNX Runtime** (CPU, single thread, < 0.1 ms p50 latency, zero external
  network calls) with occlusion-saliency explainability.
- **Tamper-evident audit log**: append-only DB triggers (UPDATE/DELETE rejected)
  + SHA-256 hash chaining, verifiable via `GET /api/v1/audit/verify`.
- **Real cryptographic Federated Learning**: independent OS client processes
  over HTTP, **Bonawitz et al. CCS'17 secure aggregation** (X25519 ECDH key
  agreement, ChaCha20 PRG zero-sum pairwise masking mod 2^32, Shamir (t, n)
  secret sharing for dropout recovery), and **client-level Differential
  Privacy** with Rényi DP (RDP) accounting.

---

## 2. Prerequisites

| Software | Version | Why | Install hint |
|---|---|---|---|
| Python | **3.11+** | Runtime | https://www.python.org/downloads/ (tick "Add to PATH" on Windows) |
| PostgreSQL | **18** | Primary database (submission requirement) | https://www.postgresql.org/download/ |
| Docker + Compose | recent | Optional — Path A | https://docs.docker.com/get-docker/ |
| Git | any | Clone the repo | https://git-scm.com/downloads |
| Internet | — | First install + SNIPS dataset download (FL demo) | — |

> **Note:** PostgreSQL 18 is used for the official submission because the
> append-only audit triggers are tested against the PostgreSQL dialect and
> `app/main.py` advertises PostgreSQL 18. SQLite works for quick tests only.

Check your versions:

```bash
python3 --version     # should print 3.11.x or newer
psql --version        # should print psql 18.x (only needed for Path B)
docker --version      # only needed for Path A
```

---

## 3. Get the source code

```bash
git clone https://github.com/code-bhaskar/Privacy-Preserving-PDA.git
cd Privacy-Preserving-PDA
```

---

## 4. Create the virtual environment

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt onnxscript
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt onnxscript
```

The install pulls FastAPI, SQLAlchemy, Alembic, cryptography, bcrypt, PyJWT,
PyTorch, ONNX/ONNX Runtime, matplotlib, pytest, etc. It can take a few minutes.

---

## 5. Configure environment variables (`.env`)

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Now open `.env` and review every key:

```ini
APP_NAME=PPDA
DEBUG=true
# PostgreSQL (recommended):
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ppda
# SQLite quick fallback instead:
# DATABASE_URL=sqlite:///./ppda.db
JWT_SECRET=supersecretjwtkeyforppdadevelopmentonly1234567890
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
AES_MASTER_KEY=Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWo=
FL_CLIENT_COUNT=5
FL_DP_DELTA=1e-5
FL_CLIP_NORM=1.0
```

Key-by-key explanation:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string. `postgresql+psycopg://user:password@host:port/dbname`. |
| `JWT_SECRET` | HS256 signing key for auth tokens. **Mandatory** — boot fails without it. |
| `JWT_ALGORITHM` | Token signing algorithm (HS256). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes. |
| `AES_MASTER_KEY` | **Exactly 32 bytes, base64-encoded** master key for AES-256-GCM encryption at rest. **Mandatory** — boot fails without a valid one. |
| `FL_CLIENT_COUNT` | Default number of federated clients used by API-triggered rounds. |
| `FL_DP_DELTA` | DP δ target for privacy accounting. |
| `FL_CLIP_NORM` | L2 clipping norm for client updates. |

Generate your own keys (recommended instead of the development defaults):

```bash
# JWT secret (any long random string):
python -c "import os;print(os.urandom(48).hex())"
# AES master key (must be 32 random bytes, base64):
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

> **Security note:** the values in `.env.example` are development-only. The app
> calls `validate_security_keys()` at startup and **refuses to boot** if
> `JWT_SECRET` (or `JWT_SECRET_KEY`) is missing or `AES_MASTER_KEY` is not a
> valid 32-byte base64 key. `.env` is git-ignored and must never be committed.

---

## 6. Path A — Run everything with Docker Compose

One command. This boots **PostgreSQL 18** (`postgres:18-alpine`), applies all
Alembic migrations, and launches the FastAPI service:

```bash
docker-compose up --build
```

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- PostgreSQL: `localhost:5432` (user `postgres`, password `postgrespassword`, db `ppda`)

Stop with `Ctrl+C`, then `docker-compose down` (add `-v` to wipe the DB volume).

---

## 7. Path B — Run locally with PostgreSQL 18 (recommended submission)

**Step 1 — Install and start PostgreSQL 18.**
Download from https://www.postgresql.org/download/ for your OS and make sure
the server is running (on Linux: `sudo systemctl start postgresql`).

**Step 2 — Create the database and user:**

```bash
sudo -u postgres psql -c "CREATE USER ppda WITH PASSWORD 'ppda';"
sudo -u postgres psql -c "CREATE DATABASE ppda OWNER ppda;"
```

(On Windows, use `psql -U postgres` in a terminal and run the same `CREATE
USER` / `CREATE DATABASE` statements.)

Verify it is really version 18:

```bash
sudo -u postgres psql -d ppda -c "SELECT version();"
# should print: PostgreSQL 18.x ...
```

**Step 3 — Point the app at the database.** In `.env` set:

```ini
DATABASE_URL=postgresql+psycopg://ppda:ppda@localhost:5432/ppda
```

**Step 4 — Apply migrations:**

```bash
alembic upgrade head
```

This creates all tables (`users`, `calendar_events`, `reminders`, `messages`,
`consents`, `audit_logs`, `model_updates`, …) plus the **append-only triggers**
on `audit_logs`.

**Step 5 — Start the API server:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Expected startup log (in order):

1. `validate_security_keys()` — verifies JWT + AES keys (refuses boot if invalid)
2. `init_db()` — verifies migrations are at head (refuses boot otherwise)
3. ONNX intent model warm-up (backend = `onnx`)
4. Reminder scheduler started
5. `Uvicorn running on http://0.0.0.0:8000`

Sanity check:

```bash
curl http://localhost:8000/health
# {"status":"ok","app":"PPDA"}
```

Interactive docs: **http://localhost:8000/docs**

---

## 8. Path C — Quick SQLite fallback

For a fast smoke test without installing PostgreSQL:

```bash
cp .env.example .env
# edit .env → DATABASE_URL=sqlite:///./ppda.db
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Everything works, but the **submission/demo should use PostgreSQL 18** (Path A or B).

---

## 9. Train / verify the ONNX intent model

The committed artifact `deployed_models/intent_model.onnx` (~269 KB,
self-contained, no external data file) is already in the repo, so the API uses
it out of the box. To (re)train it from scratch:

```bash
python scripts/train_assistant_intent.py
```

- Trains the PyTorch `IntentNet` model on the 8 assistant intents
  (`SCHEDULE_EVENT`, `CREATE_REMINDER`, `GET_EVENTS`, `GET_REMINDERS`,
  `DELETE_EVENT`, `DELETE_REMINDER`, `SUMMARIZE_MESSAGES`, `GREETING`)
- Exports a **self-contained ONNX** file to `deployed_models/intent_model.onnx`

Verify the app is using the ONNX backend (not the TF-IDF fallback):

```bash
python -c "from app.ml_models import model_inference; print(model_inference.active_backend())"
# expected: onnx
```

---

## 10. Explore the API (Swagger UI + endpoint reference)

Open **http://localhost:8000/docs** — every endpoint below is clickable and
testable from the browser. Click **Authorize** and paste
`Bearer <access_token>` after logging in.

### System
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/api/v1/fl/round/status` | Real FL coordinator state machine |

### Users / Auth (`/api/v1`)
| Method | Path | Description |
|---|---|---|
| POST | `/users` | Register (email + password → bcrypt-hashed) |
| POST | `/login` | Get HS256 JWT (rate-limited: 5 failures → 429) |
| POST | `/logout` | Revoke the presented token (blocklist) |
| GET | `/users/me` | Current user (from token) |
| GET | `/users/{user_id}` | IDOR-safe: other users → `404` |
| POST | `/consent` | Set a consent flag (current user) |
| GET | `/consent` | List own consent flags |
| GET | `/consent/{user_id}` | IDOR-safe consent lookup |

### Calendar & Reminders (`/api/v1`)
| Method | Path | Description |
|---|---|---|
| POST | `/events` | Create event (title AES-256-GCM encrypted at rest) |
| GET | `/events` | List own events (decrypted for owner only) |
| PUT | `/events/{event_id}` | Update (ownership-checked) |
| DELETE | `/events/{event_id}` | Delete (ownership-checked) |
| POST | `/reminders` | Create reminder (text encrypted at rest) |
| GET | `/reminders` | List own reminders |
| PUT | `/reminders/{reminder_id}` | Update (ownership-checked) |
| DELETE | `/reminders/{reminder_id}` | Delete (ownership-checked) |

### Assistant & Privacy (`/api/v1`)
| Method | Path | Description |
|---|---|---|
| POST | `/assistant/command` | Natural-language command → ONNX intent classification + entities + occlusion saliency |
| POST | `/messages/summarize` | Local extractive summarization (no cloud calls) |
| GET | `/privacy/posture` | Implemented vs architecture-only privacy features |
| POST | `/privacy/encrypt-demo` | Live AES-256-GCM encrypt/decrypt round-trip demo |
| GET | `/audit` | Own audit trail |
| GET | `/audit/verify` | Verify the SHA-256 audit hash chain end-to-end |

### Federated Learning (`/api/v1/fl`) — real cryptographic coordinator
| Method | Path | Description |
|---|---|---|
| POST | `/register` | Register a client process |
| POST | `/round/start` | Start a secure-aggregation round |
| GET | `/round/status` | Phase: ADVERTISE_KEYS → SHARE_KEYS → COLLECT → UNMASK → AGGREGATING → DONE |
| GET | `/model/weights` | Global model weights (hex) |
| POST | `/keys/advertise` | Client public keys (X25519 ECDH) |
| POST | `/keys/share` | Shamir shares |
| GET | `/keys/inbox/{client_id}` | Fetch shares addressed to a client |
| POST | `/update/masked` | Submit masked `uint32` update |
| POST | `/update/reveal` | Submit mask-reveal shares (dropout recovery) |
| POST | `/round/close-collection` | Force-close collection / trigger dropout recovery |
| POST | `/experiment/reset` | Reset model + privacy ledger |
| GET | `/history` | Round history + cumulative (ε, δ) spent |

### Federated proxy (`/api/v1`)
| Method | Path | Description |
|---|---|---|
| POST | `/federated/round` | Run an FL round; **HTTP 400 with instructions if no clients are connected** (never fabricates results) |
| POST | `/federated/experiment` | Multi-round experiment through the real coordinator |
| GET | `/federated/results` | Latest experiment results |

---

## 11. A guided demo of the security & privacy features

With the server running (Path A/B/C), follow this sequence — it demonstrates
every headline claim. In Swagger (`/docs`) or with `curl`:

```bash
BASE=http://localhost:8000/api/v1

# 1) Register two users
curl -s -X POST $BASE/users -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"S3curePass!","name":"Alice"}'
curl -s -X POST $BASE/users -H 'Content-Type: application/json' \
  -d '{"email":"bob@example.com","password":"S3curePass!","name":"Bob"}'

# 2) Login as Alice → copy access_token from the response
curl -s -X POST $BASE/login -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"S3curePass!"}'
TOKEN=<paste-access-token-here>
AUTH="Authorization: Bearer $TOKEN"

# 3) Authenticated call works
curl -s $BASE/users/me -H "$AUTH"

# 4) Create a calendar event (title will be encrypted at rest)
curl -s -X POST $BASE/events -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"title":"Doctor appointment","start_time":"2026-09-01T10:00:00Z","end_time":"2026-09-01T11:00:00Z"}'

# 5) IDOR immunity: Alice asks for Bob's user record → 404 (not 403)
curl -s -i $BASE/users/2 -H "$AUTH"

# 6) Assistant command → ONNX intent classification (on-device, 0 external calls)
curl -s -X POST $BASE/assistant/command -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"text":"remind me to buy milk tomorrow"}'

# 7) Encryption-at-rest demo (AES-256-GCM round trip)
curl -s -X POST $BASE/privacy/encrypt-demo -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"plaintext":"meeting with client at 3pm"}'

# 8) Privacy posture (what is implemented vs architecture-only)
curl -s $BASE/privacy/posture -H "$AUTH"

# 9) Audit trail + tamper detection
curl -s $BASE/audit -H "$AUTH"
curl -s $BASE/audit/verify -H "$AUTH"
```

**Two impressive database-level proofs (PostgreSQL):**

```sql
-- Prove encryption at rest: titles are ciphertext, not plaintext
SELECT id, left(title, 40) FROM calendar_events;

-- Prove the audit log is append-only: this is REJECTED by the DB trigger
UPDATE audit_logs SET reason = 'tampered' WHERE id = 1;   -- → ERROR: append-only
DELETE FROM audit_logs WHERE id = 1;                      -- → ERROR: append-only
```

**Rate limiting proof:** send 5 wrong-password logins → the 6th returns
`429 Too Many Requests`. **Logout revocation:** `POST /logout` then reuse the
same token → `401 Unauthorized`.

---

## 12. Run the automated test suite (73 tests)

```bash
python -m pytest tests/ -v
```

Expected: **73 passed**.

| File | Tests | Covers |
|---|---|---|
| `tests/test_auth.py` | 41 | JWT auth, logout revocation, rate limiting, encryption at rest, IDOR prevention |
| `tests/test_intent_model.py` | 16 | Intent classification, ONNX latency, explainability |
| `tests/test_audit_integrity.py` | 10 | Audit hash chain + append-only triggers |
| `tests/test_secagg.py` | 6 | Bonawitz secure aggregation, Shamir sharing, RDP accounting |

---

## 13. Federated Learning + Differential Privacy demo (the centerpiece)

### Option 1 — One-shot reproduction script (recommended)

```bash
./scripts/run_fl_demo.sh
```

This single script:
1. Downloads the real **SNIPS** dataset (13,784 utterances, 7 intents) and
   partitions it non-IID across 6 clients with Dirichlet(α = 0.5)
2. Starts the FL coordinator (`fl.server.app`)
3. Starts **6 independent OS client processes** (`python -m fl.client.run`)
4. Runs the privacy–utility sweep ε ∈ {∞, 10, 5, 1} over 20 rounds
5. Exports the global model to ONNX and benchmarks on-device latency

**Artifacts produced:** `fl_results.json`, `results/accuracy_vs_epsilon.png`,
`results/metrics_summary.csv`, `deployed_models/intent_model.onnx`,
`benchmark.json`.

> The full sweep trains real models and takes a while (tens of minutes,
> depending on CPU). The pre-computed artifacts are already committed in
> `results/`, so you can present them without re-running.

### Option 2 — Manual step-by-step

```bash
# Terminal 1 — partition the data
python -m fl.data.prepare --clients 6 --alpha 0.5

# Terminal 2 — start the coordinator
python -m uvicorn fl.server.app:app --host 0.0.0.0 --port 8000

# Terminals 3..8 — six independent client processes
python -m fl.client.run --client-id 0 --server-url http://localhost:8000
python -m fl.client.run --client-id 1 --server-url http://localhost:8000
python -m fl.client.run --client-id 2 --server-url http://localhost:8000
python -m fl.client.run --client-id 3 --server-url http://localhost:8000
python -m fl.client.run --client-id 4 --server-url http://localhost:8000
python -m fl.client.run --client-id 5 --server-url http://localhost:8000

# Run the epsilon sweep
python -m fl.experiments.run_sweep \
    --rounds 20 --local-epochs 1 --clip-norm 20 \
    --clients-per-round 3 --epsilons none,10,5,1 \
    --out fl_results.json
python -m fl.experiments.plot_results

# Export + benchmark the final global model
python -m fl.deploy.export_onnx
python -m fl.deploy.benchmark
```

Check progress any time: `GET http://localhost:8000/api/v1/fl/round/status`
and `GET http://localhost:8000/api/v1/fl/history`.

### What makes this "real" (for the viva)

- Clients are **separate OS processes** speaking HTTP; point
  `--server-url` at another machine and nothing changes.
- Each client reads only its own shard (`fl_data/client_k/train.jsonl`);
  **raw data never leaves the client** — the server only receives masked
  `uint32` vectors (`vector_hex`).
- The server has **no code path** to an individual plaintext update —
  `ServerSecAgg.aggregate()` only ever touches `uint32` sums.
- Dropout recovery works: Shamir shares reconstruct a dropped client's mask
  without ever opening both the `b` and `s` shares of the same client.
- Privacy accounting is genuine: Rényi DP composition (Mironov) over the
  rounds actually executed, converted to (ε, δ).

### Honest limitations (say these in the viva — reviewers value it)

- Protects against an **honest-but-curious server**, not a malicious one.
- DP is client-level; with only 6 clients, ε = 1 leaves the model near chance.
  The honest claim: *"the privacy–utility trade-off is real and measured."*
- INT8 compression is **1.02×**, not 4× (the EmbeddingBag stays fp32); the
  deployable fact is the whole model is a quarter of a megabyte.
- HE / SGX / TrustZone / PIR are **architecture notes only** — not built.

---

## 14. Measured results you should see

From the committed run (`results/metrics_summary.csv`,
`docs/federated_learning.md`) — 6 clients registered, 3 sampled/round,
20 rounds, SNIPS held-out test set (2,067 utterances):

| Target ε | δ | Noise multiplier σ | Final test accuracy | Uplink / client / round |
|---:|---:|---:|---:|---:|
| ∞ (no DP) | – | 0.00 | **0.9555** | 272,412 B |
| 10 | 1e-5 | 1.41 | 0.3164 | 272,412 B |
| 5 | 1e-5 | 2.37 | 0.2022 | 272,412 B |
| 1 | 1e-5 | 9.28 | 0.1722 | 272,412 B |

Chance is 1/7 ≈ 0.143 — accuracy is **monotone in ε**, which is exactly the
expected privacy–utility trade-off. Chart:
`results/accuracy_vs_epsilon.png`.

On-device inference (ONNX Runtime, single-thread CPU):

| Metric | Value |
|---|---|
| Parameters | 68,103 |
| ONNX fp32 size | 269.2 KB |
| Test accuracy through ONNX Runtime | 0.9579 |
| Latency p50 / p95 / p99 | 0.036 / 0.073 / 0.109 ms |
| External network calls per inference | **0** |

---

## 15. Project structure

```
Privacy-Preserving-PDA/
├── app/                        # FastAPI application (layered architecture)
│   ├── api/                    # HTTP route definitions (users, calendar, …)
│   ├── controllers/            # Request handling / orchestration
│   ├── services/               # Business logic
│   ├── repositories/           # Database access (SQLAlchemy)
│   ├── models/                 # ORM models (User, AuditLog, …)
│   ├── schemas/                # Pydantic request/response schemas
│   ├── core/                   # Config, database, auth, security, exceptions
│   ├── ml_models/              # Intent classifier (ONNX), summarizer, entities
│   ├── jobs/  scheduler/       # Background FL job + reminder scheduler
│   └── Data_sets/              # Seed data for intents / summarization
├── fl/                         # Real federated learning package
│   ├── protocol/               # shamir.py, crypto.py (X25519, ChaCha20), quantize.py, secagg.py
│   ├── privacy/                # accountant.py (RDP), dp_client.py
│   ├── model/                  # IntentNet (PyTorch)
│   ├── data/                   # SNIPS download + Dirichlet non-IID partition
│   ├── client/                 # agent.py + run.py (independent client process)
│   ├── server/                 # coordinator.py (6-phase state machine), routes.py, app.py
│   ├── experiments/            # run_sweep.py (ε-sweep), plot_results.py
│   └── deploy/                 # export_onnx.py, benchmark.py
├── deployed_models/            # intent_model.onnx (self-contained, ~269 KB)
├── migrations/                 # Alembic migrations (schema + audit triggers)
├── results/                    # accuracy_vs_epsilon.png, metrics_summary.csv
├── scripts/                    # train_assistant_intent.py, run_fl_demo.sh
├── tests/                      # 73 automated tests
├── docs/                       # backend_status, federated_learning, presentation_checklist
├── docker-compose.yml          # PostgreSQL 18 + API, one command
├── Dockerfile
├── alembic.ini
└── requirements.txt
```

---

## 16. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `RuntimeError` / boot refusal mentioning `JWT_SECRET` or `AES_MASTER_KEY` | Keys missing/invalid in `.env`. `AES_MASTER_KEY` must be base64 of exactly 32 bytes (see §5 to regenerate). |
| Boot refusal mentioning migrations | Run `alembic upgrade head` before starting uvicorn. The app deliberately refuses to boot on an un-migrated database. |
| `connection refused ... :5432` | PostgreSQL is not running, or wrong `DATABASE_URL`. Start the service; check user/password/db name. With Docker, run `docker-compose up` first. |
| Port 8000 already in use | `uvicorn app.main:app --port 8001` (or stop the other process). |
| `ModuleNotFoundError: No module named 'app'` | Run commands from the repository root, with the venv activated. |
| ONNX backend prints `tfidf` instead of `onnx` | The model file is missing/corrupt. Re-run `python scripts/train_assistant_intent.py` and confirm `deployed_models/intent_model.onnx` exists (no `.onnx.data` sidecar). |
| `POST /api/v1/federated/round` returns 400 | **By design** — no real client processes are connected. Start them: `python -m fl.client.run --client-id 0 --server-url http://localhost:8000`. The API never fabricates results. |
| FL client can't reach server | The coordinator must be on the URL given by `--server-url` (default `http://localhost:8000`). For other machines, open the port and use the host's LAN IP. |
| `./scripts/run_fl_demo.sh: Permission denied` | `chmod +x scripts/run_fl_demo.sh` (Linux/macOS). |
| FL demo is slow | It trains real models for ε ∈ {∞,10,5,1} × 20 rounds. Reduce with `ROUNDS=5 ./scripts/run_fl_demo.sh`, or present the committed `results/` artifacts. |
| 429 on login during the demo | You hit the 5-failed-attempts lockout — wait 5 minutes or restart the server (rate-limit state is in-memory). |
| `psycopg` install fails (Path B) | Ensure Python 3.11+ and pip are current; the binary wheel `psycopg[binary]` needs no libpq. On very old systems, `pip install "psycopg[binary]" --upgrade`. |

---

## 17. One-page quick reference

```bash
# ---- ONE-TIME SETUP -------------------------------------------------
git clone https://github.com/code-bhaskar/Privacy-Preserving-PDA.git
cd Privacy-Preserving-PDA
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt onnxscript
cp .env.example .env                                    # then edit DATABASE_URL / keys

# ---- EITHER: Docker (PostgreSQL 18 + API, all-in-one) --------------
docker-compose up --build

# ---- OR: local PostgreSQL 18 ---------------------------------------
sudo -u postgres psql -c "CREATE USER ppda WITH PASSWORD 'ppda';"
sudo -u postgres psql -c "CREATE DATABASE ppda OWNER ppda;"
# .env → DATABASE_URL=postgresql+psycopg://ppda:ppda@localhost:5432/ppda
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# ---- OR: SQLite quick test -----------------------------------------
# .env → DATABASE_URL=sqlite:///./ppda.db
alembic upgrade head && uvicorn app.main:app --port 8000

# ---- VERIFY ---------------------------------------------------------
curl http://localhost:8000/health                       # {"status":"ok","app":"PPDA"}
open http://localhost:8000/docs                         # Swagger UI
python -m pytest tests/ -v                              # 73 passed

# ---- FEDERATED LEARNING DEMO ---------------------------------------
./scripts/run_fl_demo.sh                                # full ε-sweep + ONNX export
# artifacts: results/accuracy_vs_epsilon.png, results/metrics_summary.csv

# ---- (RE)TRAIN THE INTENT MODEL ------------------------------------
python scripts/train_assistant_intent.py
```

**That's it — the backend is now running at http://localhost:8000 with
interactive documentation at http://localhost:8000/docs.**

---

*Prepared as the official "How to run" submission document for the
Privacy-Preserving Digital Assistant (PPDA) project.*
