from pathlib import Path

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from app.config import get_settings
from app.ml.features import FEATURE_COLUMNS, FighterFeatures, build_matchup_features
from app.ml.training import train_model


class FightPredictor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model_path = Path(self.settings.model_path)
        self.data_path = Path(__file__).resolve().parents[1] / "data" / "sample_fights.csv"
        self._model: Pipeline | None = None

    def model(self) -> Pipeline:
        if self._model is None:
            if not self.model_path.exists():
                train_model(self.data_path, self.model_path)
            self._model = joblib.load(self.model_path)
        return self._model

    def predict(self, fighter_a: FighterFeatures, fighter_b: FighterFeatures) -> dict[str, object]:
        features = build_matchup_features(fighter_a, fighter_b)
        frame = pd.DataFrame([{column: features[column] for column in FEATURE_COLUMNS}])
        probability_a = float(self.model().predict_proba(frame)[0][1])
        winner = fighter_a.name if probability_a >= 0.5 else fighter_b.name
        confidence = probability_a if probability_a >= 0.5 else 1 - probability_a
        return {
            "winner": winner,
            "probability_a": round(probability_a, 3),
            "probability_b": round(1 - probability_a, 3),
            "confidence": round(confidence, 3),
            "features": features,
        }
