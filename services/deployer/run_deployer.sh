#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/../.." && pwd)"

PORT="${DEPLOYER_PORT:-8080}"
MODE="${1:-host}" # "host" or "docker"

echo "=========================================================="
echo "  Dispatch Intelligence - Deployment Manager"
echo "  Mode: $MODE | Port: $PORT"
echo "=========================================================="

if [ "$MODE" = "docker" ]; then
    echo "Menjalankan Deployer via Docker container terisolasi..."
    docker compose -f "$DIR/docker-compose.deployer.yml" up -d --build
    echo "Deployer berjalan di http://localhost:$PORT"
    exit 0
fi

# Host mode
echo "Menjalankan Deployer langsung pada host Python..."
cd "$ROOT_DIR"

if [ ! -d "$DIR/.venv" ]; then
    echo "Membuat virtual environment khusus Deployer..."
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install --upgrade pip
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
fi

echo "Memulai server FastAPI Deployer pada port $PORT..."
echo "Akses Web Dashboard di: http://localhost:$PORT"
export PYTHONPATH="$ROOT_DIR:$PYTHONPATH"
export DEPLOYER_PORT="$PORT"

"$DIR/.venv/bin/python3" -m uvicorn services.deployer.main:app --host 0.0.0.0 --port "$PORT"
