import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.ml.features import FEATURE_COLUMNS
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
