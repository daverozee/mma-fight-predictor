from pathlib import Path
from dataclasses import dataclass
import json
import os

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.features import FEATURE_COLUMNS

TARGET_COLUMN = "fighter_a_won"
RANDOM_STATE = 42


@dataclass(frozen=True)
class CandidateResult:
    name: str
    accuracy: float
    balanced_accuracy: float
    log_loss: float
    roc_auc: float


@dataclass(frozen=True)
class TrainingResult:
    model: Pipeline
    selected_model: str
    candidates: list[CandidateResult]
    row_count: int


def train_model(data_path: str | Path, model_path: str | Path) -> Pipeline:
    data = pd.read_csv(data_path)
    result = train_model_from_frame(data, model_path)
    return result.model


def train_model_from_frame(
    data: pd.DataFrame,
    model_path: str | Path,
    report_path: str | Path | None = None,
) -> TrainingResult:
    missing = set(FEATURE_COLUMNS + [TARGET_COLUMN]) - set(data.columns)
    if missing:
        raise ValueError(f"Training data is missing columns: {sorted(missing)}")
    if data[TARGET_COLUMN].nunique() < 2:
        raise ValueError("Training data must include both wins and losses.")

    x = data[FEATURE_COLUMNS]
    y = data[TARGET_COLUMN].astype(int)
    candidates = candidate_models()
    evaluated = evaluate_candidates(candidates, x, y)
    selected_name = best_candidate(evaluated).name
    model = candidates[selected_name]
    model.fit(x, y)

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)

    result = TrainingResult(
        model=model,
        selected_model=selected_name,
        candidates=evaluated,
        row_count=len(data),
    )
    if report_path is not None:
        write_training_report(result, report_path)
    return result


def candidate_models() -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline(
            steps=[
                ("scale", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=3,
                        class_weight="balanced",
                        random_state=RANDOM_STATE,
                        n_jobs=1,
                    ),
                )
            ]
        ),
        "extra_trees": Pipeline(
            steps=[
                (
                    "classifier",
                    ExtraTreesClassifier(
                        n_estimators=300,
                        min_samples_leaf=3,
                        class_weight="balanced",
                        random_state=RANDOM_STATE,
                        n_jobs=1,
                    ),
                )
            ]
        ),
        "gradient_boosting": Pipeline(
            steps=[
                (
                    "classifier",
                    GradientBoostingClassifier(
                        n_estimators=150,
                        learning_rate=0.04,
                        max_depth=3,
                        random_state=RANDOM_STATE,
                    ),
                )
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            steps=[
                (
                    "classifier",
                    HistGradientBoostingClassifier(
                        max_iter=150,
                        learning_rate=0.04,
                        l2_regularization=0.01,
                        random_state=RANDOM_STATE,
                    ),
                )
            ]
        ),
    }


def evaluate_candidates(
    candidates: dict[str, Pipeline],
    x: pd.DataFrame,
    y: pd.Series,
) -> list[CandidateResult]:
    if len(y) >= 50 and y.value_counts().min() >= 5:
        return evaluate_with_cross_validation(candidates, x, y)
    return evaluate_with_holdout(candidates, x, y)


def evaluate_with_cross_validation(
    candidates: dict[str, Pipeline],
    x: pd.DataFrame,
    y: pd.Series,
) -> list[CandidateResult]:
    folds = min(5, int(y.value_counts().min()))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE)
    results = []
    for name, model in candidates.items():
        probabilities = cross_val_predict(model, x, y, cv=cv, method="predict_proba")[:, 1]
        results.append(score_predictions(name, y, probabilities))
    return sorted(results, key=lambda result: (result.log_loss, -result.roc_auc))


def evaluate_with_holdout(
    candidates: dict[str, Pipeline],
    x: pd.DataFrame,
    y: pd.Series,
) -> list[CandidateResult]:
    stratify = y if y.value_counts().min() >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.3,
        random_state=RANDOM_STATE,
        stratify=stratify,
    )
    results = []
    for name, model in candidates.items():
        model.fit(x_train, y_train)
        probabilities = model.predict_proba(x_test)[:, 1]
        results.append(score_predictions(name, y_test, probabilities))
    return sorted(results, key=lambda result: (result.log_loss, -result.roc_auc))


def score_predictions(name: str, y_true: pd.Series, probabilities) -> CandidateResult:
    predictions = (probabilities >= 0.5).astype(int)
    return CandidateResult(
        name=name,
        accuracy=round(float(accuracy_score(y_true, predictions)), 4),
        balanced_accuracy=round(float(balanced_accuracy_score(y_true, predictions)), 4),
        log_loss=round(float(log_loss(y_true, probabilities, labels=[0, 1])), 4),
        roc_auc=round(float(roc_auc_score(y_true, probabilities)), 4),
    )


def best_candidate(results: list[CandidateResult]) -> CandidateResult:
    if not results:
        raise ValueError("No model candidates were evaluated.")
    return min(results, key=lambda result: (result.log_loss, -result.roc_auc))


def write_training_report(result: TrainingResult, report_path: str | Path) -> None:
    report = {
        "selected_model": result.selected_model,
        "row_count": result.row_count,
        "candidates": [
            {
                "name": candidate.name,
                "accuracy": candidate.accuracy,
                "balanced_accuracy": candidate.balanced_accuracy,
                "log_loss": candidate.log_loss,
                "roc_auc": candidate.roc_auc,
            }
            for candidate in result.candidates
        ],
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
