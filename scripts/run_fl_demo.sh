#!/usr/bin/env bash
# End-to-end reproduction of the federated learning results.
#   ./scripts/run_fl_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
CLIENTS=${CLIENTS:-6}
PER_ROUND=${PER_ROUND:-3}
ROUNDS=${ROUNDS:-20}

mkdir -p logs results

echo "==> 1/5 Download real SNIPS + non-IID Dirichlet partition"
$PY -m fl.data.prepare --clients "$CLIENTS" --alpha 0.5

echo "==> 2/5 Start coordinator"
$PY -m uvicorn fl.server.app:app --host 0.0.0.0 --port 8000 --log-level warning &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; pkill -f "fl.client.run" || true' EXIT
sleep 6

echo "==> 3/5 Start $CLIENTS independent client processes"
for i in $(seq 0 $((CLIENTS - 1))); do
  $PY -m fl.client.run --client-id "$i" > "logs/client_$i.log" 2>&1 &
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
$PY -m fl.deploy.export_onnx
$PY -m fl.deploy.benchmark

echo
echo "Artifacts: fl_results.json, results/accuracy_vs_epsilon.png,"
echo "           results/metrics_summary.csv, deployed_models/"
