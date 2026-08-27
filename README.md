# Privacy-Preserving Digital Assistant (PPDA)

A local-first, privacy-preserving personal digital assistant backend built with **FastAPI**, **PostgreSQL / SQLite**, **ONNX Runtime**, and cryptographic **Federated Learning** (Bonawitz et al. Secure Aggregation + Rényi Differential Privacy).

---

## Key Features & Privacy Guarantees

1. **Zero-Trust JWT Authentication & IDOR Immunity**:
   - Direct `bcrypt` password hashing with 72-byte truncation protection.
   - HS256 JWT token issuance and validation.
   - Resource access strictly scoped to authenticated caller; unauthorized cross-user queries return `404 Not Found` to prevent entity enumeration.

2. **On-Device Class Intent Classifier (< 1 ms)**:
   - PyTorch `IntentNet` model trained on 8 assistant intent classes and exported to **ONNX**.
   - Executed via ONNX Runtime CPUExecutionProvider (pinned to single thread to mirror on-device mobile environments).
   - Local extractive message summarization (AES-256-GCM encryption at rest for stored messages).
   - Occlusion saliency token attribution for model explainability.

3. **Tamper-Evident Audit Logging**:
   - Append-only database triggers (PostgreSQL & SQLite) rejecting `UPDATE` and `DELETE` queries.
   - Sequential SHA-256 cryptographic hash chaining (`prev_hash` -> `integrity_hash`).
   - Audit verification endpoint (`GET /api/v1/audit/verify`) detecting any manual database tampering.

4. **Cryptographic Federated Learning & Secure Aggregation**:
   - Independent OS client processes communicating over HTTP.
   - **Bonawitz et al. CCS'17** secure aggregation protocol:
     - X25519 ECDH for pairwise key agreements.
     - ChaCha20 PRG for zero-sum pairwise masking mod $2^{32}$.
     - Shamir $(t, n)$ threshold secret sharing for graceful dropout recovery.
   - Client-level Differential Privacy with Rényi DP (RDP) accounting.

---

## Quickstart

### Prerequisites
- Python 3.11+
- PostgreSQL (or SQLite for local development)
- Docker & Docker Compose (optional)

### 1. Run with Docker Compose
```bash
docker-compose up --build
```
This automatically boots PostgreSQL, applies all Alembic migrations, and launches the FastAPI service on `http://localhost:8000`.

### 2. Local Setup

1. **Clone and create virtual environment**:
   ```bash
   git clone https://github.com/code-bhaskar/Privacy-Preserving-PDA.git
   cd Privacy-Preserving-PDA
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt onnxscript
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   ```

3. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

4. **Start the API server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Interactive API documentation will be available at `http://localhost:8000/docs`.

---

## Running Test Suite

Run the full automated test suite (69 tests covering authentication, IDOR regression, audit hash chain and triggers, intent classifier, and secure aggregation):

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
