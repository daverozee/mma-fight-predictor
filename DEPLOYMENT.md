# Deployment Notes

## Local Docker

Use Docker Compose for local development:

```powershell
docker compose up --build
```

The `db` service runs Postgres with a persistent `postgres-data` volume. The `web`
service handles HTTP requests. The `worker` service runs scheduled data imports through
`scripts/run_import_worker.py`. The `storage/` directory is still mounted for model
artifacts and optional SQLite migration source files.

For hosted multi-service deployments, use managed Postgres or a self-hosted Postgres
instance shared by the web and worker services.

## Affordable Cloud Options

- Render: usable for a forum demo with a managed Postgres database configured as `DATABASE_URL`.
- Fly.io: good Docker support and regional deployment, slightly more operational detail.
- Railway: very quick app plus Postgres setup, pricing can grow with usage.
- Hetzner, DigitalOcean, or similar VPS: cheapest steady-state option, more server maintenance.

## Fast Public Demo on Render

1. Open Render and choose New > Blueprint.
2. Connect `daverozee/mma-fight-predictor`.
3. Select the `main` branch and the root `render.yaml`.
4. Review the generated web service, environment variables, and database settings.
5. Deploy the blueprint.

The service should use Render's generated `SECRET_KEY`, a Postgres `DATABASE_URL`, and
the model artifact path at `/app/storage/model.joblib`.

For a public version, prefer:

- Docker image deployed from GitHub
- Managed Postgres or self-hosted Postgres
- Strong `SECRET_KEY`
- HTTPS handled by the platform
- Background worker process for data ingestion and model retraining
- Separate object storage for trained model artifacts if they become large

## Environment Variables

```text
APP_NAME=MMA Fight Predictor
APP_ENV=production
SECRET_KEY=replace-with-a-long-random-value
DATABASE_URL=postgresql+psycopg://...
MODEL_PATH=/app/storage/model.joblib
DATA_IMPORT_INTERVAL_SECONDS=21600
DATA_IMPORT_RUN_ON_STARTUP=true
BALLDONTLIE_FIGHTS_IMPORT_ENABLED=true
BALLDONTLIE_FIGHTS_PER_PAGE=100
BALLDONTLIE_FIGHTS_MAX_PAGES=250
BALLDONTLIE_FIGHTS_PAUSE_SECONDS=0
HISTORICAL_FIGHT_RESULTS_URL=
HISTORICAL_FIGHT_RESULTS_FORMAT=winner-loser
HISTORICAL_FIGHT_RESULTS_EVENTS_URL=
HISTORICAL_FIGHT_RESULTS_SOURCE=configured-fight-history
MEDIA_SEED_LIMIT=500
MEDIA_WIKIMEDIA_LOOKUP_LIMIT=25
MEDIA_VERIFICATION_LIMIT=50
```

Postgres support uses `psycopg[binary]`.
