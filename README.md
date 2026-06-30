# MMA Fight Predictor

An open source MMA fight analysis app for comparing fighters, estimating win probabilities, and building a stronger feature pipeline from multiple public or licensed MMA data sources.

This project is not betting advice. The model output is an experimental probability estimate based on supplied features and training data quality.

## Features

- Trainable scikit-learn model with a sample MMA-style dataset
- Seeded fighter profile library with CSV import path
- Multi-source feed adapters for fighter stats, bout history, rankings, odds movement, and recent activity
- Normalized matchup features for size, record, finishing rates, wrestling, striking pace, and defensive metrics
- Open JSON source catalog for importing CSV and JSON feeds with custom field mappings
- Public JSON API for fighter lookup and matchup predictions
- Protected app workflow with local development and Docker support
- MIT licensed and ready for GitHub

## Run With Docker

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Start the app:

```powershell
docker compose up --build
```

Compose starts a `web` service for the portal and a `worker` service for scheduled
data imports.

Open http://localhost:8000.

## Run With Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python scripts/train_model.py
uvicorn app.main:app --reload
```

Open http://localhost:8000.

## Development

```powershell
pytest
ruff check .
```

Train the predictor from the imported bout-history database and let the trainer select the
best-performing algorithm:

```powershell
python scripts/train_model_from_db.py
```

With Docker:

```powershell
docker compose exec -T web python scripts/train_model_from_db.py
docker compose restart web
```

## GitHub Project Setup

This repo includes a starter GitHub presence:

- CI workflow for Ruff, model training, and tests
- Dependabot updates for Python packages and GitHub Actions
- Bug report, feature request, and pull request templates
- Contribution, security, changelog, license, and deployment docs

Before publishing, create a GitHub repository, push this project, and set the default branch to `main` so the CI workflow runs on pushes and pull requests.

## Data Feeds

The app normalizes incoming MMA data into fighter, bout, and matchup features. The local sample files keep the workflow runnable from day one while the same structures support external feeds.

1. Use source adapters for multiple existing MMA sites, APIs, downloadable datasets, or licensed providers.
2. Store normalized fighter, bout, and event records.
3. Add scheduled refresh jobs and provenance metadata for every source.
4. Train and evaluate models with time-based splits to avoid future data leakage.
5. Deploy the web app and model artifacts separately once training becomes expensive.

Be careful with website terms of service when collecting online data. Prefer official APIs, downloadable datasets, permissive public datasets, or licensed providers.

Run a full configured import:

```powershell
python scripts/import_data.py
```

Run the same import cycle once through the worker entrypoint:

```powershell
python scripts/run_import_worker.py --once
```

With Docker, the worker runs this cycle on startup and then every
`DATA_IMPORT_INTERVAL_SECONDS` seconds. The default interval is six hours.

Import UFC bout-history edges for the defeat tree:

```powershell
python scripts/import_fight_results.py `
  "https://raw.githubusercontent.com/ThasankaK/UFC-Dataset-and-Model-Predictor/master/ufc_event_fight_stats.csv" `
  --format ufcstats-event-fight-stats `
  --events-csv "https://raw.githubusercontent.com/ThasankaK/UFC-Dataset-and-Model-Predictor/master/ufc_events.csv" `
  --source ufcstats-public-dataset `
  --source-url "https://github.com/ThasankaK/UFC-Dataset-and-Model-Predictor"
```

Import completed live fight-result edges from BALLDONTLIE for the defeat tree and
career-arc features:

```powershell
$env:BALLDONTLIE_API_KEY = "your-balldontlie-key"
python scripts/import_balldontlie_fights.py
```

This requires BALLDONTLIE account access to the MMA `/fights` endpoint.

Import richer UFCStats-derived career features and fight aggregates:

```powershell
python scripts/import_ufcstats_features.py
```

Import public Instagram profile links from Wikidata where they can be matched to roster names:

```powershell
python scripts/import_social_links.py
python scripts/import_wikidata_instagram.py
```

Discover additional Instagram links with Google Custom Search JSON API:

```powershell
$env:GOOGLE_SEARCH_API_KEY = "your-google-api-key"
$env:GOOGLE_SEARCH_ENGINE_ID = "your-search-engine-id"
python scripts/discover_social_links.py --limit 50 --dry-run
python scripts/discover_social_links.py --limit 50
```

With Docker:

```powershell
docker compose up -d --build
docker compose logs -f worker
docker compose exec -T worker python scripts/run_import_worker.py --once
docker compose exec -T web python scripts/import_balldontlie_fights.py
docker compose exec -T web python scripts/import_ufcstats_features.py
docker compose exec -T web python scripts/import_social_links.py
docker compose exec -T web python scripts/import_wikidata_instagram.py
docker compose exec -T web python scripts/discover_social_links.py --limit 50 --dry-run
```

The same Google Custom Search settings can power the optional online sentiment pulse in
matchup predictions. When enabled on the prediction form, the app samples recent public
search coverage for both fighters and applies a small bounded adjustment to the displayed
probabilities.

Edit `app/data/source_catalog.json` to add CSV or JSON sources, point to local files or URLs, and map provider fields into profile fields. Source URLs and headers support environment placeholders such as `${BALLDONTLIE_API_KEY}`. Unmapped fields can be stored as external fighter features so the feature list can grow without changing the prediction schema every time a source adds a new stat.

See `LIVE_FEEDS.md` for live API and scraping candidates.

Live API records can expand the raw fighter universe before every fighter is prediction-ready. Prediction-ready fighters still need the complete profile fields used by the model.

## API

The app exposes public JSON endpoints for fighter lookup and model predictions:

```text
GET /api/v1/fighters
POST /api/v1/predict
```

See `API.md` or `/api-docs` in the running app for examples.

## Fighter Profiles

The import worker seeds and refreshes `fighter_profiles` from the configured source catalog.
The prediction page compares two saved profiles directly from the roster search.

## Low-Cost Hosting Direction

Good first deployment targets are Render, Fly.io, Railway, or a small VPS. For the
earliest version, local Docker Compose can run a web container plus a worker container
against shared SQLite storage. For a public hosted app, move to managed Postgres before
splitting web and worker across separate platform services, and set a strong `SECRET_KEY`.

See `DEPLOYMENT.md` for more detail.
