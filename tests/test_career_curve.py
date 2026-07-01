from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.career_curve import fighter_career_curve
from app.database import Base
from app.models import FightResult, FighterProfile


def test_fighter_career_curve_tracks_cumulative_victories() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        fighter = FighterProfile(
            name="Curve Fighter",
            weight_class="Lightweight",
            age=30,
            height_cm=178,
            reach_cm=180,
            wins=2,
            losses=1,
            ko_rate=0.2,
            submission_rate=0.1,
            takedown_accuracy=0.4,
            takedown_defense=0.6,
            strikes_landed_per_min=4.0,
            strikes_absorbed_per_min=3.0,
        )
        db.add(fighter)
        db.flush()
        db.add_all(
            [
                FightResult(
                    winner_name="Curve Fighter",
                    loser_name="Opponent One",
                    event_name="First",
                    bout_date="2020-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Opponent Two",
                    loser_name="Curve Fighter",
                    event_name="Second",
                    bout_date="2021-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Curve Fighter",
                    loser_name="Opponent Three",
                    event_name="Third",
                    bout_date="2022-01-01",
                    source="test",
                ),
            ]
        )
        db.commit()

        curve = fighter_career_curve(db, fighter)

    assert curve["available"] is True
    assert curve["total_victories"] == 2
    assert curve["total_losses"] == 1
    assert curve["total_bouts"] == 3
    assert [point["victories"] for point in curve["points"]] == [1, 1, 2]
    assert [point["losses"] for point in curve["points"]] == [0, 1, 1]
    assert curve["y_max"] == 2
    assert curve["win_polyline"]
    assert curve["loss_polyline"]
    assert curve["first_label"] == "2020"
    assert curve["last_label"] == "2022"
