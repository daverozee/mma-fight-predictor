import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.ml.features import FEATURE_COLUMNS
from app.ml.backtesting import chronological_backtest
from app.ml.training import TARGET_COLUMN, train_model_from_frame
from app.ml.training_data import build_training_frame_from_results
from app.models import FightResult, FighterProfile


def test_build_training_frame_from_results_creates_mirrored_examples() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add_all(
            [
                profile("Winner", wins=12, losses=2, strikes_landed_per_min=5),
                profile("Loser", wins=8, losses=5, strikes_landed_per_min=3),
                FightResult(
                    winner_name="Winner",
                    loser_name="Loser",
                    event_name="Test Event",
                    bout_date="2024-01-01",
                    source="test",
                ),
            ]
        )
        db.commit()

        frame = build_training_frame_from_results(db)

    assert len(frame) == 2
    assert set(frame[TARGET_COLUMN]) == {0, 1}
    assert set(FEATURE_COLUMNS + [TARGET_COLUMN]).issubset(frame.columns)
    assert frame.iloc[0]["striking_diff"] == 2
    assert frame.iloc[1]["striking_diff"] == -2
    assert "elo_diff" in frame.columns
    assert "fight_date" in frame.columns
    assert "fight_result_id" in frame.columns


def test_training_frame_uses_pre_fight_history_features() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add_all(
            [
                profile("Rising Fighter", wins=12, losses=2),
                profile("Falling Fighter", wins=8, losses=5),
                FightResult(
                    winner_name="Rising Fighter",
                    loser_name="Falling Fighter",
                    event_name="First Event",
                    bout_date="2020-01-01",
                    method="KO",
                    source="test",
                ),
                FightResult(
                    winner_name="Rising Fighter",
                    loser_name="Falling Fighter",
                    event_name="Second Event",
                    bout_date="2021-01-01",
                    method="Decision",
                    source="test",
                ),
            ]
        )
        db.commit()

        frame = build_training_frame_from_results(db)

    second_fight = frame[
        (frame["fight_date"] == "2021-01-01") & (frame[TARGET_COLUMN] == 1)
    ].iloc[0]
    assert second_fight["win_rate_diff"] == 1.0
    assert second_fight["elo_diff"] > 0
    assert second_fight["recent_win_rate_diff"] == 1.0
    assert second_fight["finish_rate_diff"] == 1.0


def test_chronological_backtest_splits_future_fights() -> None:
    rows = []
    for index in range(12):
        date = f"2024-01-{index + 1:02d}"
        for target, sign in [(1, 1), (0, -1)]:
            row = {column: 0.0 for column in FEATURE_COLUMNS}
            row["win_rate_diff"] = 0.3 * sign
            row["elo_diff"] = 80 * sign
            row[TARGET_COLUMN] = target
            row["fight_date"] = date
            row["fight_result_id"] = index + 1
            rows.append(row)

    result = chronological_backtest(pd.DataFrame(rows), cutoff_date="2024-01-09")

    assert result.train_fights == 8
    assert result.test_fights == 4
    assert result.selected_model
    assert result.accuracy >= 0.5
    assert result.calibration


def test_train_model_from_frame_selects_probability_model(tmp_path) -> None:
    rows = []
    for index in range(40):
        label = int(index % 2 == 0)
        row = {column: 0.0 for column in FEATURE_COLUMNS}
        row["win_rate_diff"] = 0.25 if label else -0.25
        row["striking_diff"] = 1.0 if label else -1.0
        row[TARGET_COLUMN] = label
        rows.append(row)

    result = train_model_from_frame(
        pd.DataFrame(rows),
        tmp_path / "model.joblib",
        tmp_path / "model.report.json",
    )

    assert result.row_count == 40
    assert result.selected_model
    assert len(result.candidates) >= 3
    assert (tmp_path / "model.joblib").exists()
    assert (tmp_path / "model.report.json").exists()


def profile(name: str, **overrides) -> FighterProfile:
    payload = {
        "name": name,
        "weight_class": "Lightweight",
        "age": 30,
        "height_cm": 180,
        "reach_cm": 182,
        "wins": 10,
        "losses": 3,
        "ko_rate": 0.3,
        "submission_rate": 0.2,
        "takedown_accuracy": 0.4,
        "takedown_defense": 0.7,
        "strikes_landed_per_min": 4.0,
        "strikes_absorbed_per_min": 3.0,
        "source": "test",
    }
    payload.update(overrides)
    return FighterProfile(**payload)
