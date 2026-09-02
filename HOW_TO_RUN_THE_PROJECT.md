# HOW TO RUN THE PROJECT — PPDA

**Privacy-Preserving Digital Assistant** · FastAPI · PostgreSQL 18 · Angular 20 · ONNX Runtime · Cryptographic Federated Learning (Bonawitz et al. Secure Aggregation) · Rényi Differential Privacy

---

## 0. The whole demo in one command

This is the path to use for a presentation. It boots the backend **with the FL
coordinator in-process**, registers the demo user, grants all four consent
categories, spawns the federated client processes *through the API* (so the UI
can stop them and read their logs), and serves the Angular UI.

```bash
git clone https://github.com/code-bhaskar/Privacy-Preserving-PDA.git
cd Privacy-Preserving-PDA

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt onnxscript
cp .env.example .env                    # SQLite is fine for the demo
cd frontend && npm ci && cd ..

./scripts/run_demo.sh                   # Ctrl-C stops backend + clients + UI
```

Then open **http://localhost:4200**, sign in as `demo@ppda.io` / `DemoPass123!`
and press **Load demo** — it seeds a few encrypted calendar records and
reminders so every tab has something to show.

Useful overrides:

```bash
CLIENTS=0 ./scripts/run_demo.sh         # skip FL clients (saves ~1 GB RAM)
FRONTEND=prod ./scripts/run_demo.sh     # serve the optimised bundle
PORT=8001 UI_PORT=4300 ./scripts/run_demo.sh
```

The first run downloads the real SNIPS corpus (~14k utterances) into `fl_data/`
and applies the Alembic migrations; later runs skip both. On a 2 CPU / 4 GB
machine keep `CLIENTS` at 3 — a 3-client secure-aggregation round takes ~7 s.

> **Do not test the rate limiter before presenting.** Five failed logins lock
> that email for 5 minutes (`MAX_LOGIN_ATTEMPTS = 5`,
> `LOCKOUT_WINDOW_SECONDS = 300` in `app/core/auth.py`), and the lock is
> in-memory, so restarting the backend clears it.

---

## 1. Backend-only setup

```bash
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
  `JWT_SECRET` should be at least 32 bytes or PyJWT warns about a weak HMAC key.
- `FL_SERVER_URL` — loopback URL of the in-process coordinator that supervised
  clients are spawned against. `FL_ROUND_TIMEOUT_SECONDS` (default 240) is how
  long `POST /federated/round` waits for real clients.

## 2. Run it

**Option A — Docker (backend only):**

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

**Option D — backend + Angular UI + FL clients:** `./scripts/run_demo.sh` (section 0).

Then open:
- UI → `http://localhost:4200`
- API → `http://localhost:8000` · Swagger UI → `http://localhost:8000/docs`
- Health → `curl http://localhost:8000/health` → `{"status":"ok","app":"PPDA"}`

## 3. Verify (60 seconds)

```bash
python -m pytest tests/ -q        # 124 passed
python -c "from app.ml_models import model_inference; print(model_inference.active_backend())"
# → onnx
```

What the suite covers: auth + logout/revocation, IDOR regression, AES-256-GCM at
rest, the audit hash chain and its append-only triggers, the ONNX intent
classifier, Bonawitz secure aggregation, the ONNX label-space guards
(`tests/test_onnx_export_isolation.py`), and every response field the Angular
templates bind to (`tests/test_frontend_contract.py`).

The frontend has no browser available in CI, so the contract suite is what keeps
the UI honest: rename a response key and a test fails instead of a panel going
quietly blank. The Angular build itself is AOT with strict templates, so binding
and type errors fail the compile.

```bash
cd frontend && npm run build      # 0 errors, 0 warnings
```

The ONNX intent model is committed (`deployed_models/intent_model.onnx`, 8
classes, 269 KB). Retrain it any time with `python scripts/train_assistant_intent.py`.

## 4. Federated Learning + Differential Privacy

**There is no separate FL service.** The secure-aggregation coordinator runs
inside the same FastAPI process as the assistant and audit APIs, and
`/api/v1/federated/pipeline/*` drives dataset prep, client process supervision,
rounds, the ε sweep and the ONNX export. Only the *client* processes are
separate — and that isolation is the privacy claim: each holds its own shard and
the server only ever receives masked `uint32` vectors.

Everything below is clickable in the **Federated pipeline** tab. The headless
equivalent that reproduces every published number:

```bash
./scripts/run_fl_demo.sh
```

Manual equivalent:

```bash
python -m fl.data.prepare --clients 6 --alpha 0.5
python -m uvicorn app.main:app --port 8000          # NOT fl.server.app — single pipeline
for i in {0..5}; do python -m fl.client.run --client-id $i --server-url http://localhost:8000 & done
python -m fl.experiments.run_sweep --rounds 20 --local-epochs 1 --clip-norm 20 \
    --clients-per-round 3 --epsilons none,10,5,1 --out fl_results.json
python -m fl.deploy.export_onnx && python -m fl.deploy.benchmark
```

Artifacts: `results/accuracy_vs_epsilon.png`, `results/metrics_summary.csv`,
`fl_results.json`, `deployed_models/`.

> `POST /api/v1/federated/round` returns **400 until real clients connect** — by
> design. The API never fabricates results. It returns **403** if the caller has
> not granted `federated_training` consent; `scripts/run_demo.sh` grants it, and
> so does the login screen's **Load demo** button.

### Two ONNX artifacts — do not confuse them

| Artifact | Classes | Trained on | Served by |
|---|---|---|---|
| `deployed_models/intent_model.onnx` | 8 | assistant intent seed | `POST /assistant/command` |
| `deployed_models/intent_model_federated.onnx` | 7 | SNIPS (federated) | FL demo / benchmarking |

`fl.deploy.export_onnx` writes the **federated** artifact. `--target live`
overwrites the served model and *refuses* when the class counts differ, because
`predict()` maps `argmax` onto `INTENT_LABELS[i]` — a 7-class SNIPS model served
as the 8-class assistant model returns confidently **wrong intent names**, not
merely worse ones. `app/ml_models/onnx_inference.py` independently measures the
artifact's output width at load time and falls back to TF-IDF rather than
mislabel. This shipped as a real bug once; `tests/test_onnx_export_isolation.py`
now pins both guards.

## 5. What it proves

20-round sweep (`./scripts/run_fl_demo.sh`):

| Target ε | Noise σ | Test accuracy |
|---:|---:|---:|
| ∞ (no DP) | 0.00 | **0.9555** |
| 10 | 1.41 | 0.3164 |
| 5 | 2.37 | 0.2022 |
| 1 | 9.28 | 0.1722 |

Accuracy is monotone in ε — the privacy–utility trade-off, measured. Shorter runs
score lower (a 2-round sweep gives ≈0.81 at ε=∞ and ≈0.12 at ε=5); the shape of
the curve is the result, not the absolute number, so say how many rounds you ran.

On-device: 68k params, 269 KB ONNX, p50 latency ~0.03 ms, 0 external calls.
Per round: 272,412 bytes uplink per client, `server_saw_plaintext_updates: false`.

## 6. Endpoints that matter

| Endpoint | Shows |
|---|---|
| `POST /api/v1/users` → `POST /api/v1/login` | bcrypt + HS256 JWT (5 failed logins → 429) |
| `POST /api/v1/logout` | Token revocation blocklist |
| `GET /api/v1/users/{other_id}` | IDOR immunity → `404`, never leaks existence |
| `POST /api/v1/events` | Title AES-256-GCM encrypted at rest (check the raw DB row) |
| `POST /api/v1/assistant/command` | On-device ONNX intent + occlusion saliency, 0 external calls |
| `POST /api/v1/messages/summarize` | Local extractive summary, `raw_content_transmitted_externally: false` |
| `POST /api/v1/privacy/encrypt-demo` | Live AES-256-GCM round trip |
| `GET /api/v1/audit/verify` | SHA-256 audit hash chain; DB triggers reject `UPDATE/DELETE` on `audit_logs` |
| `GET /api/v1/privacy/posture` | Implemented vs architecture-only — the honest map |
| `GET /api/v1/fl/round/status` · `/history` | Live secure-aggregation state machine + (ε, δ) spent |
| `GET /api/v1/federated/pipeline/status` | One call with everything the FL tab renders |
| `POST /api/v1/federated/pipeline/clients/spawn` | Supervisor starts real client OS processes |
| `POST /api/v1/federated/pipeline/sweep/start` | ε sweep with live progress |
| `POST /api/v1/federated/pipeline/onnx/export` | Federated ONNX export + latency benchmark |

## 7. If something fails

| Symptom | Fix |
|---|---|
| Boot refuses (keys) | Set valid `JWT_SECRET` + 32-byte base64 `AES_MASTER_KEY` in `.env` |
| Boot refuses (migrations) | Run `alembic upgrade head` first — intentional |
| `:5432 connection refused` | PostgreSQL not running → start it, or `docker-compose up` |
| FL endpoint returns 400 | Start client processes: `python -m fl.client.run --client-id 0` |
| FL endpoint returns 403 | Grant `federated_training` consent (or press **Load demo**) |
| FL tab shows "0 alive" but N registered | Clients were started outside the supervisor — spawn them from the tab, or via `scripts/run_demo.sh` |
| Login returns 429 | Rate limiter tripped; wait 5 min or restart the backend (the lock is in-memory) |
| Backend prints `tfidf` not `onnx` | `python scripts/train_assistant_intent.py` to regenerate the model |
| Assistant intents look wrong | Check `deployed_models/intent_model.onnx` is the 8-class model, not a federated export |
| `ng: No such file or directory` | `cd frontend && npm ci` |
| UI loads but every call 404s | The dev-server proxy is not running — start the UI with `npm start` or `scripts/run_demo.sh`, not a plain static server |
| Port 8000 busy | `PORT=8001 ./scripts/run_demo.sh` (it regenerates the proxy config to match) |

---

*Run paths: `scripts/run_demo.sh` for the full presentation · Docker for a quick backend look · PostgreSQL 18 for the submission · `scripts/run_fl_demo.sh` for the headless FL numbers. Details live in `README.md`, `docs/federated_learning.md`, and `docs/presentation_checklist.md`.*
