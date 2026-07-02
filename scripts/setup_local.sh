#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

SKIP_BUILD=0
SKIP_IMPORT=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --skip-import) SKIP_IMPORT=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop or Docker Engine, then rerun this script." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add optional API keys there when available."
fi

if [ "$SKIP_BUILD" -eq 1 ]; then
  docker compose up -d
else
  docker compose up -d --build
fi

if [ "$SKIP_IMPORT" -eq 0 ]; then
  docker compose exec -T web python scripts/import_data.py
  docker compose exec -T web python scripts/train_model.py
fi

cat <<'EOF'

MMA Fight Predictor is running:
  http://127.0.0.1:8000

Useful commands:
  docker compose logs -f web
  docker compose logs -f worker
  pytest
  ruff check .
EOF
