# MMA Fight Predictor

An open source MMA fight analysis app for comparing fighters, estimating win probabilities, and building a stronger feature pipeline from multiple public or licensed MMA data sources.

This project is not betting advice. The model output is an experimental probability estimate based on supplied features and training data quality.

## Features

- Trainable scikit-learn model with a sample MMA-style dataset
- Seeded fighter profile library with CSV import path
- Planned multi-source feed adapters for fighter stats, bout history, rankings, odds movement, and recent activity
- Normalized matchup features for size, record, finishing rates, wrestling, striking pace, and defensive metrics
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

## GitHub Project Setup

This repo includes a starter GitHub presence:

- CI workflow for Ruff, model training, and tests
- Dependabot updates for Python packages and GitHub Actions
- Bug report, feature request, and pull request templates
- Contribution, security, changelog, license, and deployment docs

Before publishing, create a GitHub repository, push this project, and set the default branch to `main` so the CI workflow runs on pushes and pull requests.

## Data Roadmap

The current app uses `app/data/sample_fights.csv` so the workflow is runnable from day one. The intended production path is:

1. Add source adapters for multiple existing MMA sites, APIs, downloadable datasets, or licensed providers.
2. Store normalized fighter, bout, and event records.
3. Add scheduled refresh jobs and provenance metadata for every source.
4. Train and evaluate models with time-based splits to avoid future data leakage.
5. Deploy the web app and model artifacts separately once training becomes expensive.

Be careful with website terms of service when collecting online data. Prefer official APIs, downloadable datasets, permissive public datasets, or licensed providers.

## Fighter Profiles

On startup the app seeds `fighter_profiles` from `app/data/sample_fighters.csv` when the table is empty. The prediction page can compare two saved profiles directly, while manual entry remains available for newer stats or hypothetical matchups.

## Low-Cost Hosting Direction

Good first deployment targets are Render, Fly.io, Railway, or a small VPS. For the earliest version, a single Docker container with SQLite volume storage is fine for demos. For a public app, move to managed Postgres and set a strong `SECRET_KEY`.

See `DEPLOYMENT.md` for more detail.
