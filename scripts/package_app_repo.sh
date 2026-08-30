#!/usr/bin/env bash
# Build a self-contained PPDA backend app directory that can be moved/zipped
# and run on its own.
#
#   ./scripts/package_app_repo.sh [DEST]
#
# Default DEST is dist_ppda_backend (git-ignored).
#
# The app imports the `fl` package directly (app/main.py, onnx_inference.py,
# federated_service.py), so `fl/` MUST be included for the app to run alone.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-dist_ppda_backend}"

cd "$ROOT"

rm -rf "$DEST"
mkdir -p "$DEST"

# --- Required at runtime -----------------------------------------------------
cp -r app fl migrations deployed_models "$DEST/"
cp alembic.ini requirements.txt .env.example .gitignore "$DEST/"

# --- Deployment, docs, evidence (recommended for a submission repo) ----------
cp Dockerfile docker-compose.yml README.md "$DEST/" 2>/dev/null || true
cp -r docs results "$DEST/" 2>/dev/null || true
cp -r scripts "$DEST/" 2>/dev/null || true

# --- Clean generated/private artifacts ---------------------------------------
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$DEST" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
rm -f "$DEST/.env" "$DEST"/*.db "$DEST"/*.sqlite3
rm -rf "$DEST/fl_data" "$DEST/logs" "$DEST/deployed_models"/*.onnx.data

# Keep only the shipped ONNX model, let the rest stay generated.
find "$DEST/deployed_models" -maxdepth 1 -type f ! -name 'intent_model.onnx' -delete

echo "Standalone app repo created at: $DEST"
echo "Contents:"
echo "  app/ fl/ migrations/ deployed_models/ alembic.ini requirements.txt .env.example"
echo "  Dockerfile docker-compose.yml README.md docs/ results/ scripts/ (if present)"
echo
echo "Verify:"
echo "  cd $DEST"
echo "  python3 -m venv .venv && source .venv/bin/activate"
echo "  pip install -r requirements.txt onnxscript"
echo "  cp .env.example .env   # set DATABASE_URL / secrets"
echo "  alembic upgrade head"
echo "  uvicorn app.main:app --host 0.0.0.0 --port 8000"
