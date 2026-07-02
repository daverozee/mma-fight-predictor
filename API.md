# MMA Fight Predictor API

The app exposes a public JSON API for fighter lookup and profile-based predictions.

## Endpoints

```text
GET /api/v1/meta
GET /api/v1/fighters?limit=50&offset=0&search=cruz
GET /api/v1/fighters/{fighter_id}
POST /api/v1/predict
POST /api/v1/agents/predict
GET /api/v1/cards/analyze
```

## Predict

Request:

```json
{
  "fighter_a_id": 9,
  "fighter_b_id": 10
}
```

Response includes each fighter profile, the predicted winner, probabilities, confidence, and model feature differences.

```json
{
  "prediction": {
    "winner": "Aalon Cruz",
    "probability_a": 0.51,
    "probability_b": 0.49,
    "confidence": 0.51
  }
}
```

Profiles marked `provisional-live-feed` use live source fields where available and league-average fallbacks where source coverage is incomplete.

## Agent Predict

Request:

```json
{
  "fighter_a_id": 9,
  "fighter_b_id": 10,
  "include_sentiment": true
}
```

Response includes the standard prediction plus an analyst report:

```json
{
  "prediction": {
    "winner": "Aalon Cruz",
    "probability_a": 0.51,
    "probability_b": 0.49,
    "confidence": 0.51
  },
  "agent": {
    "version": "prediction-agent-v1",
    "tool_runs": [],
    "data_quality": {},
    "model_read": {},
    "wager_readiness": {}
  }
}
```

`wager_readiness` is research-only. Automated wagering should only be added through approved sportsbook integrations with user confirmation, identity, age, location, account authorization, responsible gaming limits, and audit logs.

## Card Analyzer

Request:

```text
GET /api/v1/cards/analyze?limit_cards=8
```

Response groups upcoming odds-feed fights by card date and includes a prediction for each fight
where both fighters can be matched to saved profiles.
