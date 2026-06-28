# MMA Fight Predictor API

The app exposes a public JSON API for fighter lookup and profile-based predictions.

## Endpoints

```text
GET /api/v1/meta
GET /api/v1/fighters?limit=50&offset=0&search=cruz
GET /api/v1/fighters/{fighter_id}
POST /api/v1/predict
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
