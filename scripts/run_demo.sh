#!/usr/bin/env bash
# One command to bring up the whole PPDA demo: backend (with the FL coordinator
# in-process), the federated learning client processes, and the Angular frontend.
#
#   ./scripts/run_demo.sh                 # backend + 3 FL clients + frontend dev server
#   CLIENTS=0 ./scripts/run_demo.sh       # skip FL clients (lighter on RAM)
#   FRONTEND=prod ./scripts/run_demo.sh   # serve the optimised production build
#   PORT=8000 UI_PORT=4200 ./scripts/run_demo.sh
#
# Then open the printed UI URL. Demo login: demo@ppda.io / DemoPass123!
#
# Everything runs from ONE FastAPI process on purpose — the FL coordinator is
# not a separate service, and the Angular app talks to it through the dev-server
# proxy using relative URLs. Ctrl-C stops the backend, the clients and the UI.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PY:-.venv/bin/python}
PORT=${PORT:-8000}
UI_PORT=${UI_PORT:-4200}
CLIENTS=${CLIENTS:-3}
FRONTEND=${FRONTEND:-dev}
DEMO_EMAIL=${DEMO_EMAIL:-demo@ppda.io}
DEMO_PASSWORD=${DEMO_PASSWORD:-DemoPass123!}
HOST=${HOST:-0.0.0.0}
# Resolved to an absolute path: the script `cd`s into frontend/ before using it,
# so a repo-root-relative default would become frontend/frontend/node_modules/...
NG_BIN=${NG_BIN:-"$PWD/frontend/node_modules/.bin/ng"}

SERVER_URL="http://127.0.0.1:${PORT}"
PIDS=()

cleanup() {
    trap - EXIT INT TERM
    echo
    echo "==> shutting down"
    # Bracket form so this script's own command line never matches the pattern.
    pkill -f "fl[.]client[.]run" 2>/dev/null || true
    for pid in "${PIDS[@]:-}"; do
        [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
    done
    [ -n "${PROXY_FILE:-}" ] && rm -f "$PROXY_FILE"
    wait 2>/dev/null || true
    echo "==> stopped"
}
trap cleanup EXIT INT TERM

step() { echo; echo "==> $*"; }

# --------------------------------------------------------------------------- #
step "0/4 Environment"
[ -x "$PY" ] || { echo "No $PY — create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[ -f .env ] || { echo "No .env — copy it with: cp .env.example .env"; exit 1; }
echo "    python   : $PY ($($PY -V 2>&1))"
echo "    backend  : ${SERVER_URL}"
echo "    frontend : port ${UI_PORT} (${FRONTEND})"
echo "    clients  : ${CLIENTS}"

# --------------------------------------------------------------------------- #
step "1/4 Database migrations"
$PY -m alembic upgrade head

# --------------------------------------------------------------------------- #
step "2/4 Federated learning dataset (real SNIPS, non-IID Dirichlet shards)"
if [ -d fl_data/client_0 ]; then
    echo "    fl_data/ already prepared — skipping download"
else
    $PY -m fl.data.prepare --clients 6 --alpha 0.5
fi

# --------------------------------------------------------------------------- #
step "3/4 Backend (FastAPI + in-process FL coordinator)"
mkdir -p logs results deployed_models
$PY -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level warning &
PIDS+=("$!")

echo -n "    waiting for ${SERVER_URL}/health"
for _ in $(seq 1 60); do
    if curl -fsS -m 2 "${SERVER_URL}/health" >/dev/null 2>&1; then echo " — up"; break; fi
    echo -n "."; sleep 1
done
curl -fsS -m 5 "${SERVER_URL}/health" >/dev/null || { echo " backend failed to start; see logs above"; exit 1; }

if [ "$CLIENTS" -gt 0 ]; then
    # Spawn through the pipeline API, NOT as direct children of this script. The
    # supervisor inside the server owns those processes, which is what makes the
    # Federated tab's alive/stop/log controls work on them. Clients started by the
    # shell would register with the coordinator but show as "0 alive" in the UI.
    echo "    bootstrapping ${DEMO_EMAIL} so the spawn call can authenticate"
    curl -s -m 20 -X POST "${SERVER_URL}/api/v1/users" \
        -H 'Content-Type: application/json' \
        -d "{\"name\":\"Demo User\",\"email\":\"${DEMO_EMAIL}\",\"password\":\"${DEMO_PASSWORD}\",\"preferences\":{}}" \
        > /dev/null || true   # 4xx just means the demo user already exists

    TOKEN=$(curl -s -m 20 -X POST "${SERVER_URL}/api/v1/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"${DEMO_EMAIL}\",\"password\":\"${DEMO_PASSWORD}\"}" \
        | $PY -c "import json,sys
try: print(json.load(sys.stdin).get('access_token',''))
except Exception: print('')" 2>/dev/null || true)

    if [ -n "$TOKEN" ]; then
        # A fresh database has no consent rows, and POST /federated/round answers
        # 403 without FEDERATED_TRAINING. Grant all four categories up front so
        # the presenter can log in and click straight through; the login screen's
        # "Load demo" button does the same thing idempotently.
        echo -n "    granting consent"
        for CAT in assistant_nlu calendar_data message_summarization federated_training; do
            CODE=$(curl -s -m 20 -o /dev/null -w "%{http_code}" \
                -X POST "${SERVER_URL}/api/v1/consent" \
                -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
                -d "{\"category\":\"${CAT}\",\"granted\":true}")
            echo -n " ${CAT}=${CODE}"
        done
        echo
    fi

    if [ -z "$TOKEN" ]; then
        echo "    could not obtain a JWT — falling back to shell-spawned clients"
        echo "    (the Federated tab will show them as registered but not supervised)"
        for i in $(seq 0 $((CLIENTS - 1))); do
            $PY -m fl.client.run --client-id "$i" --server-url "$SERVER_URL" --rounds 1000 \
                > "logs/client_${i}.log" 2>&1 &
            PIDS+=("$!")
            sleep 0.4
        done
    else
        echo "    asking the supervisor to spawn ${CLIENTS} independent client processes"
        curl -s -m 60 -X POST "${SERVER_URL}/api/v1/federated/pipeline/clients/spawn" \
            -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
            -d "{\"count\":${CLIENTS}}" \
            | $PY -c "import json,sys
try:
    d = json.load(sys.stdin)
    ids = [c['client_id'] for c in d.get('spawned', [])]
    print(f'      spawned client ids {ids}' + (f\", errors {d['errors']}\" if d.get('errors') else ''))
except Exception as e:
    print('      spawn response unreadable:', e)"
    fi

    echo -n "    waiting for registration"
    for _ in $(seq 1 45); do
        N=$(curl -fsS -m 5 "${SERVER_URL}/api/v1/fl/round/status" 2>/dev/null \
            | $PY -c "import json,sys
try: print(json.load(sys.stdin).get('registered_clients', 0))
except Exception: print(0)" 2>/dev/null || echo 0)
        [ "${N:-0}" -ge "$CLIENTS" ] && { echo " — ${N} registered"; break; }
        echo -n "."; sleep 2
    done
else
    echo "    CLIENTS=0 — no FL clients started (the Federated tab can spawn them later)"
fi

# --------------------------------------------------------------------------- #
step "4/4 Angular frontend"
if [ ! -x "$NG_BIN" ]; then
    echo "    installing frontend dependencies (npm ci)"
    (cd frontend && npm ci)
fi
[ -x "$NG_BIN" ] || {
    echo "    Angular CLI not found at $NG_BIN"
    echo "    Install it with: cd frontend && npm install"
    exit 1
}
echo "    ng         : $($NG_BIN version 2>/dev/null | grep -m1 'Angular CLI' || echo 'present')"

# The checked-in proxy.conf.json points at :8000. Regenerate it so PORT overrides
# still reach the backend instead of silently 404ing every /api call.
PROXY_FILE="$(mktemp "${TMPDIR:-/tmp}/ppda-proxy-XXXXXX.json")"
cat > "$PROXY_FILE" <<PROXY
{
  "/api":          { "target": "${SERVER_URL}", "secure": false, "changeOrigin": false },
  "/health":       { "target": "${SERVER_URL}", "secure": false, "changeOrigin": false },
  "/docs":         { "target": "${SERVER_URL}", "secure": false, "changeOrigin": false },
  "/openapi.json": { "target": "${SERVER_URL}", "secure": false, "changeOrigin": false }
}
PROXY

if [ "$FRONTEND" = "prod" ]; then
    # `ng serve -c production` keeps the dev-server proxy while building the
    # optimised bundle. A plain static file server would not proxy /api, so the
    # SPA's relative URLs would 404.
    echo "    serving the optimised production bundle on ${UI_PORT}"
    (cd frontend && "$NG_BIN" serve --configuration production \
        --host "$HOST" --port "$UI_PORT" --proxy-config "$PROXY_FILE") &
    PIDS+=("$!")
else
    echo "    serving the development bundle on ${UI_PORT}"
    (cd frontend && "$NG_BIN" serve \
        --host "$HOST" --port "$UI_PORT" --proxy-config "$PROXY_FILE") &
    PIDS+=("$!")
fi

echo -n "    waiting for the UI"
UI_UP=0
for _ in $(seq 1 180); do
    if curl -fsS -m 2 "http://127.0.0.1:${UI_PORT}/" >/dev/null 2>&1; then echo " — up"; UI_UP=1; break; fi
    echo -n "."; sleep 1
done
if [ "$UI_UP" -ne 1 ]; then
    echo
    echo "    the frontend did not come up on port ${UI_PORT}; see the ng output above"
    exit 1
fi

cat <<BANNER

--------------------------------------------------------------------------
 PPDA demo is running

   UI            http://localhost:${UI_PORT}
   API           ${SERVER_URL}/api/v1
   API docs      ${SERVER_URL}/docs
   Health        ${SERVER_URL}/health

   Login         demo@ppda.io  /  DemoPass123!

 Tabs: Assistant · Scheduler · Privacy · Audit · Federated pipeline

 Federated tab: the ${CLIENTS} client processes are independent OS processes
 that hold their own SNIPS shard. The server only ever receives masked uint32
 vectors — run a round there and watch server_saw_plaintext_updates stay false.

 Note on the export step: it writes
   deployed_models/intent_model_federated.onnx   (SNIPS, 7 intents)
 and deliberately leaves the served assistant model alone:
   deployed_models/intent_model.onnx             (assistant, 8 intents)
 The two label spaces differ, so swapping them would make the assistant return
 confidently wrong intent names.

 Ctrl-C stops everything.
--------------------------------------------------------------------------
BANNER

wait
