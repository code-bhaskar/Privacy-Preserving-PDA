# Privacy-Preserving Digital Assistant (PPDA)

A local-first, privacy-preserving personal digital assistant backend built with **FastAPI**, **PostgreSQL / SQLite**, **ONNX Runtime**, and cryptographic **Federated Learning** (Bonawitz et al. Secure Aggregation + Rényi Differential Privacy).

---

## Key Features & Privacy Guarantees

1. **Zero-Trust JWT Authentication & IDOR Immunity**:
   - Direct `bcrypt` password hashing with 72-byte truncation protection.
   - HS256 JWT token issuance and validation.
   - Resource access strictly scoped to authenticated caller; unauthorized cross-user queries return `404 Not Found` to prevent entity enumeration.
   - Rate limiting on `POST /api/v1/login` (maximum 5 failed attempts per window, returning `HTTP 429 Too Many Requests`).
   - Token revocation blocklist with `POST /api/v1/logout`.

2. **Data Encryption at Rest (AES-256-GCM)**:
   - Calendar event titles, reminder texts, and private messages are encrypted at rest with AES-256-GCM using individual user AAD (`str(user_id)`).
   - Audit log entries do not leak plaintext titles or message contents in audit reasons.
   - Application strictly refuses to boot if `JWT_SECRET` / `JWT_SECRET_KEY` or `AES_MASTER_KEY` is missing or invalid.

3. **On-Device Class Intent Classifier (< 1 ms)**:
   - PyTorch `IntentNet` model trained on 8 assistant intent classes and exported to **ONNX** (`deployed_models/intent_model.onnx`).
   - Executed via ONNX Runtime CPUExecutionProvider (pinned to single thread to mirror on-device mobile environments).
   - Local extractive message summarization (no external cloud API transmissions).
   - Occlusion saliency token attribution for model explainability (`"occlusion saliency attribution (not SHAP/LIME)"`).

4. **Tamper-Evident Audit Logging**:
   - Append-only database triggers (PostgreSQL & SQLite) rejecting `UPDATE` and `DELETE` queries.
   - Sequential SHA-256 cryptographic hash chaining (`prev_hash` -> `integrity_hash`).
   - Audit verification endpoint (`GET /api/v1/audit/verify`) detecting any manual database tampering.
   - Strict boot verification: application refuses to boot if database is un-migrated (`check_db_migrated()`).

5. **Cryptographic Federated Learning & Secure Aggregation**:
   - Independent OS client processes communicating over HTTP.
   - **Bonawitz et al. CCS'17** secure aggregation protocol:
     - X25519 ECDH for pairwise key agreements.
     - ChaCha20 PRG for zero-sum pairwise masking mod $2^{32}$.
     - Shamir $(t, n)$ threshold secret sharing for graceful dropout recovery.
   - Client-level Differential Privacy with Rényi DP (RDP) accounting.
   - Honest refusal: `POST /api/v1/federated/round` returns `HTTP 400` when no clients are connected; never fabricates results.

---

## Quickstart

### Prerequisites
- Python 3.11+
- Node 20.19+ / 22.12+ / 24+ and npm (for the Angular demo frontend)
- PostgreSQL 18 (or SQLite for local development only)
- Docker & Docker Compose (optional)

### 0. The whole demo in one command

Boots the FastAPI backend **with the FL coordinator in-process**, spawns the
federated learning client processes through the same API, and serves the Angular
UI on <http://localhost:4200>:

```bash
cp .env.example .env          # once
./scripts/run_demo.sh         # Ctrl-C stops backend + clients + UI
```

Login: `demo@ppda.io` / `DemoPass123!`, then press **Load demo** on the login
screen — it registers the account, grants all four consent categories and seeds
a few encrypted records.

Useful overrides:

```bash
CLIENTS=0 ./scripts/run_demo.sh        # skip FL clients (lighter on RAM)
FRONTEND=prod ./scripts/run_demo.sh    # serve the optimised bundle
PORT=8000 UI_PORT=4200 ./scripts/run_demo.sh
```

The first run downloads the real SNIPS corpus into `fl_data/` and runs the
Alembic migrations; subsequent runs skip both.

Tabs: **Assistant** (intent + occlusion saliency) · **Scheduler** (encrypted
calendar/reminders) · **Privacy** (posture + encrypt demo) · **Audit** (hash
chain) · **Federated pipeline** (dataset → clients → secure-aggregation rounds →
ε sweep → ONNX export).

### 1. Run with Docker Compose
```bash
docker-compose up --build
```
This automatically boots **PostgreSQL 18** (`postgres:18-alpine`), applies all Alembic
migrations, and launches the FastAPI service on `http://localhost:8000`.

### 2. Local Setup

1. **Clone and create virtual environment**:
   ```bash
   git clone https://github.com/code-bhaskar/Privacy-Preserving-PDA.git
   cd Privacy-Preserving-PDA
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt onnxscript
   ```

2. **Create a PostgreSQL 18 database** (required for the submission; optional SQLite
   works for quick smoke tests):

   ```bash
   sudo -u postgres psql -c "CREATE USER ppda WITH PASSWORD 'ppda';"
   sudo -u postgres psql -c "CREATE DATABASE ppda OWNER ppda;"
   ```

   Then configure the environment:
   ```bash
   cp .env.example .env
   # set DATABASE_URL=postgresql+psycopg://ppda:ppda@localhost:5432/ppda
   ```

   The included `docker-compose.yml` uses `postgres:18-alpine` and does all of this for
   you automatically.

3. **Train intent classification ONNX artifact**:
   ```bash
   python scripts/train_assistant_intent.py
   ```

4. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

5. **Start the API server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Interactive API documentation will be available at `http://localhost:8000/docs`.

---

## Running Test Suite

Run the full automated test suite (**124 tests** covering authentication, IDOR regression, encryption at rest, audit hash chain and append-only triggers, intent classifier, secure aggregation, the ONNX label-space guards, and the Angular frontend's data contract):

```bash
python3 -m pytest tests/ -v
```

---

## Federated Learning Workflow

Federated learning is **not a separate service**. The Bonawitz secure-aggregation
coordinator lives inside the same FastAPI process that serves `/api/v1/*`, and
`/api/v1/federated/pipeline/*` drives the rest of the demo — dataset preparation,
client process supervision, rounds, the ε sweep and the ONNX export. Only the
*client* processes are separate, and that isolation is the privacy claim: each
holds its own shard and the server only ever receives masked uint32 vectors.

Everything below is reachable from the **Federated pipeline** tab; the commands
are the headless equivalents.

1. **Start the app** (coordinator included — do not start `fl.server.app`):
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **Prepare the dataset** (real SNIPS, non-IID Dirichlet shards):
   ```bash
   python -m fl.data.prepare --clients 6 --alpha 0.5
   ```

3. **Spawn client processes**:
   ```bash
   for i in {0..4}; do
     python -m fl.client.run --client-id $i --server-url http://localhost:8000 &
   done
   ```

4. **Run a round / the privacy-utility sweep**:
   ```bash
   python -m fl.experiments.run_sweep --clients-per-round 3 --rounds 10 \
       --epsilons none,10,5,1 --out fl_results.json
   ```

5. **Export and benchmark**:
   ```bash
   python -m fl.deploy.export_onnx
   python -m fl.deploy.benchmark
   ```

### Two ONNX artifacts, deliberately kept apart

| Artifact | Classes | Trained on | Served by |
|---|---|---|---|
| `deployed_models/intent_model.onnx` | 8 | assistant intent seed | `POST /assistant/command` |
| `deployed_models/intent_model_federated.onnx` | 7 | SNIPS (federated) | the FL demo / benchmarking |

`fl.deploy.export_onnx` writes the **federated** artifact by default. It will not
overwrite the served model unless you pass `--target live`, and even then it
refuses when the class counts differ: `predict()` maps `argmax` onto
`INTENT_LABELS[i]`, so serving a 7-class SNIPS model as the 8-class assistant
model does not merely lose accuracy — it returns *confidently wrong intent
names*. As a second line of defence, `app/ml_models/onnx_inference.py` measures
the artifact's output width at load time and marks the model unavailable (falling
back to the TF-IDF classifier) rather than mislabelling.
`tests/test_onnx_export_isolation.py` pins both guards.

Regenerate the served assistant model with:

```bash
python scripts/train_assistant_intent.py
```

---

## Demo Frontend (Angular 20)

`frontend/` is a demonstration UI for the existing backend — Angular 20.3,
Bootstrap 5.3.3, HTML5, no backend changes required.

```bash
cd frontend
npm ci
npm start            # http://localhost:4200, proxies /api, /health, /docs to :8000
npm run build        # optimised bundle in dist/frontend/browser
```

The app uses relative URLs and the dev-server proxy (`proxy.conf.json`), so it
never hardcodes a host. `scripts/run_demo.sh` regenerates that proxy config from
its `PORT` value, so overriding the backend port still works.

Because the templates are the real contract with the backend,
`tests/test_frontend_contract.py` pins every field shape the UI binds to — a
renamed or missing response key fails CI instead of silently blanking a panel.
