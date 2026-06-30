# Deployment Notes

## Local Docker

Use Docker Compose for local development:

```powershell
docker compose up --build
```

The `web` service handles HTTP requests. The `worker` service runs scheduled data
imports through `scripts/run_import_worker.py`. The `storage/` directory is mounted into
both containers so the SQLite database and model artifact survive rebuilds.

For hosted multi-service deployments, use managed Postgres before splitting web and
worker across separate platform services. Local Docker Compose can share `./storage`,
but most hosting platforms do not share a SQLite disk between services.

## Affordable Cloud Options

- Render: recommended for today's forum demo. The included `render.yaml` deploys the Docker app with a persistent disk for SQLite signups and model storage.
- Fly.io: good Docker support and regional deployment, slightly more operational detail.
- Railway: very quick app plus Postgres setup, pricing can grow with usage.
- Hetzner, DigitalOcean, or similar VPS: cheapest steady-state option, more server maintenance.

## Fast Public Demo on Render

1. Open Render and choose New > Blueprint.
2. Connect `daverozee/mma-fight-predictor`.
3. Select the `main` branch and the root `render.yaml`.
4. Review the generated web service, environment variables, and 1 GB disk.
5. Deploy the blueprint.

The service will use Render's generated `SECRET_KEY`, SQLite at `/app/storage/app.db`, and the model artifact at `/app/storage/model.joblib`.

For a public version, prefer:

- Docker image deployed from GitHub
- Managed Postgres instead of SQLite
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
```

The starter ships with SQLite dependencies only. Add a Postgres driver, such as `psycopg[binary]`, when moving to Postgres.
