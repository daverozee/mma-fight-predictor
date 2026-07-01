from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FightResult, FighterProfile
from scripts.audit_fight_history_freshness import audit_fight_history_freshness


def test_fight_history_audit_flags_missing_or_stale_histories() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        db.add_all(
            [
                profile("Partial Fighter", wins=20, losses=10),
                profile("Covered Fighter", wins=2, losses=1),
            ]
        )
        db.add_all(
            [
                FightResult(
                    winner_name="Partial Fighter",
                    loser_name="Opponent One",
                    event_name="Old Event",
                    bout_date="2020-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Covered Fighter",
                    loser_name="Opponent Two",
                    event_name="Recent Event",
                    bout_date="2026-05-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Covered Fighter",
                    loser_name="Opponent Three",
                    event_name="Recent Event 2",
                    bout_date="2026-01-01",
                    source="test",
                ),
                FightResult(
                    winner_name="Opponent Four",
                    loser_name="Covered Fighter",
                    event_name="Recent Event 3",
                    bout_date="2025-06-01",
                    source="test",
                ),
            ]
        )
        db.commit()

        rows = audit_fight_history_freshness(
            db,
            as_of=date(2026, 7, 1),
            min_missing_bouts=8,
            stale_years=2,
        )

    assert [row["name"] for row in rows] == ["Partial Fighter"]
    assert rows[0]["missing_bouts"] == 29
    assert rows[0]["last_bout_years_ago"] == 6.5


def profile(name: str, wins: int, losses: int) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Lightweight",
        age=30,
        height_cm=180,
        reach_cm=182,
        wins=wins,
        losses=losses,
        ko_rate=0.3,
        submission_rate=0.2,
        takedown_accuracy=0.4,
        takedown_defense=0.7,
        strikes_landed_per_min=4.0,
        strikes_absorbed_per_min=3.0,
        source="test",
    )
