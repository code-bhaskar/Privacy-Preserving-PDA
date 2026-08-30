# HOW TO RUN THE PROJECT — PPDA Backend

**Privacy-Preserving Digital Assistant** · FastAPI · PostgreSQL 18 · ONNX Runtime · Cryptographic Federated Learning (Bonawitz et al. Secure Aggregation) · Rényi Differential Privacy

---

## 1. Setup (once)

```bash
git clone https://github.com/code-bhaskar/Privacy-Preserving-PDA.git
cd Privacy-Preserving-PDA
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt onnxscript
cp .env.example .env
```

In `.env`:
- `DATABASE_URL` — PostgreSQL 18 for the real run (`postgresql+psycopg://ppda:ppda@localhost:5432/ppda`), or `sqlite:///./ppda.db` for a quick smoke test.
- `JWT_SECRET` and `AES_MASTER_KEY` (base64 of exactly 32 bytes) are **mandatory** — the app refuses to boot without them. Generate:
  ```bash
  python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
  ```

## 2. Run it

**Option A — Docker (everything in one command):**

```bash
docker-compose up --build        # boots PostgreSQL 18 + runs migrations + starts API
```

**Option B — Local PostgreSQL 18 (submission path):**

```bash
sudo -u postgres psql -c "CREATE USER ppda WITH PASSWORD 'ppda';"
sudo -u postgres psql -c "CREATE DATABASE ppda OWNER ppda;"
alembic upgrade head                       # required — app won't boot on an un-migrated DB
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Option C — SQLite quick test:**

```bash
# .env → DATABASE_URL=sqlite:///./ppda.db
alembic upgrade head && uvicorn app.main:app --port 8000
```

Then open:
- API → `http://localhost:8000` · Swagger UI → `http://localhost:8000/docs`
- Health → `curl http://localhost:8000/health` → `{"status":"ok","app":"PPDA"}`

## 3. Verify (30 seconds)

```bash
python -m pytest tests/ -v          # 73 passed (auth/IDOR, encryption at rest,
                                    # audit hash chain + triggers, ONNX, secure aggregation)
python -c "from app.ml_models import model_inference; print(model_inference.active_backend())"
# → onnx
```

The ONNX intent model is already committed (`deployed_models/intent_model.onnx`). Retrain it any time with `python scripts/train_assistant_intent.py`.

## 4. Federated Learning + Differential Privacy demo

One script reproduces every published number:

```bash
./scripts/run_fl_demo.sh
```

It downloads SNIPS, partitions it non-IID (Dirichlet α=0.5) across 6 client processes, runs the secure-aggregation ε-sweep (∞, 10, 5, 1) over 20 rounds, and exports the global model to ONNX. Artifacts: `results/accuracy_vs_epsilon.png`, `results/metrics_summary.csv`, `fl_results.json`.

Manual equivalent:

```bash
python -m fl.data.prepare --clients 6 --alpha 0.5
python -m uvicorn fl.server.app:app --port 8000
for i in {0..5}; do python -m fl.client.run --client-id $i --server-url http://localhost:8000 & done
python -m fl.experiments.run_sweep --rounds 20 --local-epochs 1 --clip-norm 20 \
    --clients-per-round 3 --epsilons none,10,5,1 --out fl_results.json
```

> `POST /api/v1/federated/round` returns **400 until real clients connect** — by design. The API never fabricates results.

## 5. What it proves

| Target ε | Noise σ | Test accuracy |
|---:|---:|---:|
| ∞ (no DP) | 0.00 | **0.9555** |
| 10 | 1.41 | 0.3164 |
| 5 | 2.37 | 0.2022 |
| 1 | 9.28 | 0.1722 |

Accuracy is monotone in ε — the privacy–utility trade-off, measured. On-device: 68k params, 269 KB ONNX, p50 latency 0.036 ms, 0 external calls. The server only ever sees masked `uint32` vectors — it has no code path to any individual update.

## 6. Endpoints that matter

| Endpoint | Shows |
|---|---|
| `POST /api/v1/users` → `POST /api/v1/login` | bcrypt + HS256 JWT (5 failed logins → 429) |
| `GET /api/v1/users/{other_id}` | IDOR immunity → `404`, never leaks existence |
| `POST /api/v1/events` | Title AES-256-GCM encrypted at rest (check the raw DB row) |
| `POST /api/v1/assistant/command` | On-device ONNX intent + saliency, 0 external calls |
| `POST /api/v1/privacy/encrypt-demo` | Live AES-256-GCM round trip |
| `GET /api/v1/audit/verify` | SHA-256 audit hash chain; DB triggers reject `UPDATE/DELETE` on `audit_logs` |
| `GET /api/v1/privacy/posture` | Implemented vs architecture-only — the honest map |
| `GET /api/v1/fl/round/status` · `/history` | Live secure-aggregation state machine + (ε, δ) spent |

## 7. If something fails

| Symptom | Fix |
|---|---|
| Boot refuses (keys) | Set valid `JWT_SECRET` + 32-byte base64 `AES_MASTER_KEY` in `.env` |
| Boot refuses (migrations) | Run `alembic upgrade head` first — intentional |
| `:5432 connection refused` | PostgreSQL not running → start it, or `docker-compose up` |
| FL endpoint returns 400 | Start client processes: `python -m fl.client.run --client-id 0` |
| Backend prints `tfidf` not `onnx` | `python scripts/train_assistant_intent.py` to regenerate the model |
| Port 8000 busy | `--port 8001` |

---

*Run paths: Docker for a quick look · PostgreSQL 18 for the submission · full FL demo via `scripts/run_fl_demo.sh`. Details live in `README.md`, `docs/federated_learning.md`, and `docs/presentation_checklist.md`.*
