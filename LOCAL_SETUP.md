# Local Setup

This guide gets the MMA Fight Predictor portal running locally with Postgres, the web app, and the
scheduled import worker.

## Requirements

- Git
- Docker Desktop or Docker Engine with Docker Compose
- Python 3.11 if you want to run tests or scripts directly outside Docker

## Fast Setup With Scripts

### Windows PowerShell

```powershell
.\scripts\setup_local.ps1
```

### macOS / Linux

```bash
sh scripts/setup_local.sh
```

The scripts:

1. create `.env` from `.env.example` if needed;
2. build and start Docker Compose services;
3. run the configured import once;
4. train the sample model artifact;
5. print the local app URL.

Open:

```text
http://127.0.0.1:8000
```

## Manual Docker Setup

Copy the environment file:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

Start the stack:

```powershell
docker compose up -d --build
```

Run a one-time import and train the sample model:

```powershell
docker compose exec -T web python scripts/import_data.py
docker compose exec -T web python scripts/train_model.py
```

Watch logs:

```powershell
docker compose logs -f web
docker compose logs -f worker
```

Stop the app:

```powershell
docker compose down
```

Reset the local Postgres database:

```powershell
docker compose down -v
docker compose up -d --build
docker compose exec -T web python scripts/import_data.py
docker compose exec -T web python scripts/train_model.py
```

## Optional API Keys

The app runs without keys using local sample feeds. Add these to `.env` when available:

```text
BALLDONTLIE_API_KEY=
THE_ODDS_API_KEY=
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_ENGINE_ID=
```

Key behavior:

- `BALLDONTLIE_API_KEY` enables live fighter imports and, when available to the account, completed fight imports.
- `THE_ODDS_API_KEY` enables current MMA odds records from The Odds API source template.
- `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` enable live article links and optional matchup sentiment sampling.

Never commit `.env`.

## Data Imports

Run the normal configured import:

```powershell
docker compose exec -T web python scripts/import_data.py
```

Run one worker cycle:

```powershell
docker compose exec -T worker python scripts/run_import_worker.py --once
```

Import UFCStats-derived features:

```powershell
docker compose exec -T web python scripts/import_ufcstats_features.py
```

Import public social links:

```powershell
docker compose exec -T web python scripts/import_social_links.py
docker compose exec -T web python scripts/import_wikidata_instagram.py
```

Audit fight-history freshness:

```powershell
docker compose exec -T web python scripts/audit_fight_history_freshness.py --limit 100
```

## Model Training

Train from sample data:

```powershell
docker compose exec -T web python scripts/train_model.py
```

Train from imported fight history:

```powershell
docker compose exec -T web python scripts/train_model_from_db.py
docker compose restart web
```

`train_model_from_db.py` requires profile-linked fight results. Use the sample trainer first when
bootstrapping a new local database.

## Local Python Development

Use Docker for Postgres, then run Python locally:

```powershell
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python scripts/import_data.py
python scripts/train_model.py
uvicorn app.main:app --reload
```

On macOS/Linux:

```bash
docker compose up -d db
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/import_data.py
python scripts/train_model.py
uvicorn app.main:app --reload
```

## Tests And Quality Checks

The default Docker image is runtime-focused: it does not copy `tests/` or install dev tools.
Run tests from a local Python environment after installing `requirements-dev.txt`:

```powershell
pytest
ruff check .
```

You can still run a quick runtime syntax check inside the container:

```powershell
docker compose exec -T web python -m compileall app scripts
```

## Useful Endpoints

```text
GET  /health
GET  /api/v1/meta
GET  /api/v1/fighters?limit=50&offset=0&search=jones
POST /api/v1/predict
POST /api/v1/agents/predict
```

## Troubleshooting

### Port 8000 is already in use

Edit `docker-compose.yml` and change:

```yaml
ports:
  - "8001:8000"
```

Then open `http://127.0.0.1:8001`.

### Port 5432 is already in use

If another Postgres is running locally, change the host port:

```yaml
ports:
  - "5433:5432"
```

Docker services still reach the database at `db:5432`.

### Database connection errors outside Docker

For local Python, `.env.example` uses:

```text
DATABASE_URL=postgresql+psycopg://mma:mma-dev-password@localhost:5432/mma_fight_predictor
```

Make sure `docker compose up -d db` is running and healthy.

### Empty fighter list

Run:

```powershell
docker compose exec -T web python scripts/import_data.py
```

Then refresh `/fighters`.

### Stale containers after code changes

```powershell
docker compose up -d --build
docker compose restart web worker
```
