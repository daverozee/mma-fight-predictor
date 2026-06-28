from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.features import FEATURE_COLUMNS


def train_model(data_path: str | Path, model_path: str | Path) -> Pipeline:
    data = pd.read_csv(data_path)
    missing = set(FEATURE_COLUMNS + ["fighter_a_won"]) - set(data.columns)
    if missing:
        raise ValueError(f"Training data is missing columns: {sorted(missing)}")

    x = data[FEATURE_COLUMNS]
    y = data["fighter_a_won"]

    model = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )
    model.fit(x, y)

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    return model
