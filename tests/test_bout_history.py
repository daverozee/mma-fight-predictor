from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bout_history import fighter_bout_history
from app.database import Base
from app.models import FightResult, FighterProfile


def test_fighter_bout_history_returns_recent_first_with_result_and_opponent_link() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        fighter = FighterProfile(
            name="History Fighter",
            weight_class="Lightweight",
            age=30,
            height_cm=178,
            reach_cm=180,
            wins=1,
            losses=1,
            ko_rate=0.2,
            submission_rate=0.1,
            takedown_accuracy=0.4,
            takedown_defense=0.6,
            strikes_landed_per_min=4.0,
            strikes_absorbed_per_min=3.0,
        )
        opponent = FighterProfile(
            name="Linked Opponent",
            weight_class="Lightweight",
            age=31,
            height_cm=177,
            reach_cm=179,
            wins=1,
            losses=1,
            ko_rate=0.2,
            submission_rate=0.1,
            takedown_accuracy=0.4,
            takedown_defense=0.6,
            strikes_landed_per_min=4.0,
            strikes_absorbed_per_min=3.0,
        )
        db.add_all([fighter, opponent])
        db.flush()
        opponent_id = opponent.id
        db.add_all(
            [
                FightResult(
                    winner_name="History Fighter",
                    loser_name="Linked Opponent",
                    event_name="Older Event",
                    bout_date="2020-01-01",
                    method="Decision",
                    source="test",
                ),
                FightResult(
                    winner_name="Recent Opponent",
                    loser_name="History Fighter",
                    event_name="Recent Event",
                    bout_date="2024-01-01",
                    method="KO",
                    source="test",
                ),
            ]
        )
        db.commit()

        history = fighter_bout_history(db, fighter)

    assert [bout["event_name"] for bout in history] == ["Recent Event", "Older Event"]
    assert [bout["result"] for bout in history] == ["Loss", "Win"]
    assert history[1]["opponent"] == "Linked Opponent"
    assert history[1]["opponent_id"] == opponent_id
