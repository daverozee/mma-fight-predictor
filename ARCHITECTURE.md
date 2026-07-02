# Project Architecture

MMA Fight Predictor is a FastAPI portal for fighter lookup, matchup prediction, data ingestion,
career-history analysis, and structured prediction-agent reports. The app is designed to run locally
with Docker Compose and to deploy as separate web, worker, and Postgres services.

## System Topology

```mermaid
flowchart LR
  User["User browser"] --> Web["FastAPI web container"]
  Web --> DB[("Postgres")]
  Web --> Model["Model artifact\nstorage/model.joblib"]
  Worker["Import worker container"] --> DB
  Worker --> Sources["Configured data sources\nAPIs, CSV, JSON feeds"]
  Worker --> Media["Public image sources\nWikidata / Wikimedia Commons"]
  Trainer["Training scripts"] --> DB
  Trainer --> Model
```

### Containers

| Service | Purpose |
| --- | --- |
| `db` | Local Postgres database for users, fighters, external features, media, and fight results. |
| `web` | FastAPI/Jinja portal, public JSON API, prediction endpoint, and agent endpoint. |
| `worker` | Scheduled import cycle for source catalog records, live fights, historical fight results, and media improvement. |

## Request Flow

```mermaid
sequenceDiagram
  participant Browser
  participant FastAPI
  participant Agent as PredictionAgent
  participant Predictor as FightPredictor
  participant DB as Postgres

  Browser->>FastAPI: Choose two fighters
  FastAPI->>DB: Load fighter profiles and feature maps
  FastAPI->>Agent: Analyze matchup
  Agent->>DB: Career arc and data quality checks
  Agent->>Predictor: Run model + adjustments
  Predictor-->>Agent: Probabilities, winner, factors
  Agent-->>FastAPI: Prediction + analyst report
  FastAPI-->>Browser: Result page / JSON response
```

## Data Model

```mermaid
erDiagram
  User {
    int id
    string email
    string password_hash
  }
  FighterProfile {
    int id
    string name
    string weight_class
    float age
    float wins
    float losses
  }
  FighterExternalFeature {
    int id
    string fighter_name
    string feature_name
    float numeric_value
    string text_value
    string source
  }
  FighterMedia {
    int id
    string fighter_name
    string thumbnail_url
    string source
    string status
  }
  FightResult {
    int id
    string winner_name
    string loser_name
    string event_name
    string bout_date
    string source
  }

  FighterProfile ||--o{ FighterExternalFeature : "has wide features"
  FighterProfile ||--o{ FighterMedia : "has media"
  FighterProfile ||--o{ FightResult : "winner or loser"
```

## Ingestion Flow

```mermaid
flowchart TD
  Catalog["app/data/source_catalog.json"] --> Importer["import_catalog"]
  LocalCSV["Local CSV feeds"] --> Importer
  LiveAPI["Live API feeds\nBALLDONTLIE, The Odds API"] --> Importer
  Importer --> Profiles["fighter_profiles"]
  Importer --> Features["fighter_external_features"]
  Current["current fight results"] --> Results["fight_results"]
  Historical["historical fight imports"] --> Results
  MediaJob["media improvement job"] --> Media["fighter_media"]
  Profiles --> Promotion["promote_imported_fighters_to_profiles"]
  Features --> Promotion
```

The source catalog supports local paths, URLs, JSON record paths, CSV files, cursor pagination,
environment-variable placeholders, field mappings, and wide external-feature capture.

## Prediction Flow

```mermaid
flowchart TD
  Profiles["Fighter profiles"] --> Features["build_matchup_features"]
  Features --> Model["scikit-learn probability model"]
  Profiles --> Weight["weight-class adjustment"]
  Results["fight_results"] --> Career["career-arc adjustment"]
  Search["optional search sentiment"] --> Sentiment["bounded sentiment adjustment"]
  Model --> Blend["final probability"]
  Weight --> Blend
  Career --> Blend
  Sentiment --> Blend
  Blend --> Explanation["winner, confidence, factors, profile table"]
```

The current model is trained with scikit-learn candidates and stores the selected artifact at
`storage/model.joblib`. The predictor applies bounded adjustments for weight mismatch, career arc,
and optional search sentiment.

## Prediction Agent

```mermaid
flowchart LR
  Agent["PredictionAgent"] --> ProfileTool["fighter_profile_tool"]
  Agent --> CareerTool["career_arc_tool"]
  Agent --> SentimentTool["sentiment_tool"]
  Agent --> ModelTool["model_prediction_tool"]
  Agent --> QualityTool["data_quality_tool"]
  Agent --> Wager["wager_readiness"]
```

`PredictionAgent` is deterministic today and returns a stable JSON contract:

- `prediction`: winner, probabilities, confidence, matchup factors, and profile comparison.
- `agent.tool_runs`: which analysis checks ran and their status.
- `agent.data_quality`: source coverage and missing-context warnings.
- `agent.model_read`: concise explanation of the model read.
- `agent.wager_readiness`: research-only readiness checks for any future betting workflow.

This shape is intended to support a later OpenAI Agents SDK runner without changing clients that
already call `POST /api/v1/agents/predict`.

## Future Wagering Boundary

Automated betting is not implemented. Any future wager-assistant workflow should be separate from
prediction inference and require:

- approved sportsbook API or partner integration;
- explicit user account authorization;
- human confirmation for every wager;
- identity, age, location, and jurisdiction checks;
- responsible gaming limits;
- audit logs and user-visible history.

The app currently exposes `wager_readiness` as a research and compliance planning object only.
