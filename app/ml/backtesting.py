from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json

import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, log_loss
from sklearn.metrics import roc_auc_score

from app.matchup_context import parse_bout_date
from app.ml.features import FEATURE_COLUMNS
from app.ml.training import TARGET_COLUMN, candidate_models, score_predictions


@dataclass(frozen=True)
class BacktestResult:
    cutoff_date: str
    selected_model: str
    train_rows: int
    test_rows: int
    train_fights: int
    test_fights: int
    accuracy: float
    balanced_accuracy: float
    log_loss: float
    roc_auc: float
    brier_score: float
    calibration: list[dict[str, float | int | str]]
    candidates: list[dict[str, float | str]]

    def as_dict(self) -> dict[str, object]:
        return {
            "cutoff_date": self.cutoff_date,
            "selected_model": self.selected_model,
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "train_fights": self.train_fights,
            "test_fights": self.test_fights,
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
            "log_loss": self.log_loss,
            "roc_auc": self.roc_auc,
            "brier_score": self.brier_score,
            "calibration": self.calibration,
            "candidates": self.candidates,
        }


def chronological_backtest(
    frame: pd.DataFrame,
    cutoff_date: str | date | None = None,
    train_fraction: float = 0.8,
) -> BacktestResult:
    required = set(FEATURE_COLUMNS + [TARGET_COLUMN, "fight_date", "fight_result_id"])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Backtest frame is missing columns: {sorted(missing)}")

    data = frame.copy()
    data["fight_date_parsed"] = data["fight_date"].map(parse_required_date)
    cutoff = parse_required_date(cutoff_date) if cutoff_date else percentile_cutoff(data, train_fraction)
    train = data[data["fight_date_parsed"] < cutoff]
    test = data[data["fight_date_parsed"] >= cutoff]
    if train.empty or test.empty:
        raise ValueError("Chronological backtest needs both training and test rows.")
    if train[TARGET_COLUMN].nunique() < 2 or test[TARGET_COLUMN].nunique() < 2:
        raise ValueError("Chronological backtest needs both outcomes on each side of the cutoff.")

    x_train = train[FEATURE_COLUMNS]
    y_train = train[TARGET_COLUMN].astype(int)
    x_test = test[FEATURE_COLUMNS]
    y_test = test[TARGET_COLUMN].astype(int)

    candidate_scores = []
    fitted_models = {}
    for name, model in candidate_models().items():
        model.fit(x_train, y_train)
        probabilities = model.predict_proba(x_test)[:, 1]
        candidate_scores.append(score_predictions(name, y_test, probabilities))
        fitted_models[name] = probabilities

    candidate_scores = sorted(candidate_scores, key=lambda result: (result.log_loss, -result.roc_auc))
    selected = candidate_scores[0]
    probabilities = fitted_models[selected.name]
    predictions = (probabilities >= 0.5).astype(int)
    return BacktestResult(
        cutoff_date=cutoff.isoformat(),
        selected_model=selected.name,
        train_rows=len(train),
        test_rows=len(test),
        train_fights=train["fight_result_id"].nunique(),
        test_fights=test["fight_result_id"].nunique(),
        accuracy=round(float(accuracy_score(y_test, predictions)), 4),
        balanced_accuracy=round(float(balanced_accuracy_score(y_test, predictions)), 4),
        log_loss=round(float(log_loss(y_test, probabilities, labels=[0, 1])), 4),
        roc_auc=round(float(roc_auc_score(y_test, probabilities)), 4),
        brier_score=round(float(brier_score_loss(y_test, probabilities)), 4),
        calibration=calibration_buckets(y_test, probabilities),
        candidates=[
            {
                "name": candidate.name,
                "accuracy": candidate.accuracy,
                "balanced_accuracy": candidate.balanced_accuracy,
                "log_loss": candidate.log_loss,
                "roc_auc": candidate.roc_auc,
            }
            for candidate in candidate_scores
        ],
    )


def write_backtest_report(result: BacktestResult, report_path: str | Path) -> None:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")


def parse_required_date(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    parsed = parse_bout_date(value)
    if parsed is None:
        raise ValueError(f"Invalid fight date for backtest: {value!r}")
    return parsed


def percentile_cutoff(frame: pd.DataFrame, train_fraction: float) -> date:
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1.")
    dates = sorted(frame["fight_date_parsed"].unique())
    if len(dates) < 2:
        raise ValueError("Chronological backtest needs at least two fight dates.")
    index = max(1, min(len(dates) - 1, int(len(dates) * train_fraction)))
    return dates[index]


def calibration_buckets(y_true: pd.Series, probabilities) -> list[dict[str, float | int | str]]:
    buckets = []
    for lower, upper in [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]:
        mask = (probabilities >= lower) & (probabilities < upper)
        count = int(mask.sum())
        if count == 0:
            continue
        bucket_truth = y_true[mask]
        bucket_probabilities = probabilities[mask]
        buckets.append(
            {
                "bucket": f"{lower:.1f}-{min(upper, 1.0):.1f}",
                "count": count,
                "average_probability": round(float(bucket_probabilities.mean()), 4),
                "actual_win_rate": round(float(bucket_truth.mean()), 4),
            }
        )
    return buckets
