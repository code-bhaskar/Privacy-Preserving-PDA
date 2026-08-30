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
- PostgreSQL 18 (or SQLite for local development only)
- Docker & Docker Compose (optional)

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

Run the full automated test suite (73 tests covering authentication, IDOR regression, encryption at rest, audit hash chain and triggers, intent classifier, and secure aggregation):

```bash
python3 -m pytest tests/ -v
```

---

## Federated Learning Workflow

1. **Start the Coordinator** (included in FastAPI or standalone):
   ```bash
   python -m uvicorn fl.server.app:app --port 8000
   ```

2. **Spawn Client Processes** (e.g., 5 independent processes):
   ```bash
   for i in {0..4}; do
     python -m fl.client.run --client-id $i --server-url http://localhost:8000 &
   done
   ```

3. **Execute Privacy Epsilon Sweep**:
   ```bash
   python -m fl.experiments.run_sweep --clients 5 --rounds 10
   ```
