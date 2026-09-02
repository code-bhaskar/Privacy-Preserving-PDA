#!/usr/bin/env bash
# End-to-end reproduction of the federated learning results.
#   ./scripts/run_fl_demo.sh
#
# This drives the SAME FastAPI app the product runs (app.main:app) — the FL
# coordinator lives in-process, there is no separate coordinator service. For
# the interactive Angular demo use ./scripts/run_demo.sh instead; this script is
# the headless "reproduce the published numbers" path.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
CLIENTS=${CLIENTS:-6}
PER_ROUND=${PER_ROUND:-3}
ROUNDS=${ROUNDS:-20}
PORT=${PORT:-8000}

mkdir -p logs results

cleanup() {
    trap - EXIT INT TERM
    # Bracket form: an unbracketed "fl.client.run" pattern also matches this
    # script's own command line and would kill the shell running it.
    pkill -f "fl[.]client[.]run" 2>/dev/null || true
    [ -n "${SERVER:-}" ] && kill "$SERVER" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> 1/5 Download real SNIPS + non-IID Dirichlet partition"
$PY -m fl.data.prepare --clients "$CLIENTS" --alpha 0.5

echo "==> 2/5 Start the app (FastAPI + in-process FL coordinator) on :${PORT}"
$PY -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --log-level warning &
SERVER=$!
for _ in $(seq 1 60); do
    curl -fsS -m 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
    sleep 1
done

echo "==> 3/5 Start $CLIENTS independent client processes"
for i in $(seq 0 $((CLIENTS - 1))); do
    $PY -m fl.client.run --client-id "$i" --server-url "http://127.0.0.1:${PORT}" \
        > "logs/client_$i.log" 2>&1 &
    sleep 0.3
done
sleep 12

echo "==> 4/5 Privacy-utility sweep (eps = inf, 10, 5, 1)"
$PY -m fl.experiments.run_sweep \
    --rounds "$ROUNDS" --local-epochs 1 --clip-norm 20 \
    --clients-per-round "$PER_ROUND" --epsilons none,10,5,1 \
    --out fl_results.json
$PY -m fl.experiments.plot_results

echo "==> 5/5 Export the global model to ONNX and benchmark on-device latency"
# Writes deployed_models/intent_model_federated.onnx (SNIPS, 7 intents). It does
# NOT touch deployed_models/intent_model.onnx, which is the 8-intent artifact
# POST /assistant/command serves — different label spaces, so overwriting it
# would make the assistant return confidently wrong intent names. Use
# `--target live` only once FL trains on the assistant's own label space.
$PY -m fl.deploy.export_onnx
$PY -m fl.deploy.benchmark

echo
echo "Artifacts: fl_results.json, results/accuracy_vs_epsilon.png,"
echo "           results/metrics_summary.csv,"
echo "           deployed_models/intent_model_federated.onnx (+ int8, model card),"
echo "           deployed_models/benchmark.json (timed on the served model)"
