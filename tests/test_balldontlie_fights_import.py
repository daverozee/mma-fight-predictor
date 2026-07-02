from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FightResult, FighterProfile
from scripts.import_balldontlie_fights import import_fight_edges, normalize_fight


def test_normalize_completed_fight_creates_winner_loser_edge() -> None:
    edge = normalize_fight(
        {
            "id": 44,
            "status": "completed",
            "fighter1": {"id": 1, "name": "Conor McGregor"},
            "fighter2": {"id": 2, "name": "Justin Gaethje"},
            "winner": {"id": 2, "name": "Justin Gaethje"},
            "event": {"name": "UFC Test Night", "date": "2026-06-14T00:00:00Z"},
            "result_method": "Decision",
            "result_method_detail": "Unanimous",
            "weight_class": {"name": "Lightweight"},
            "scheduled_rounds": 3,
            "finish_round": 3,
            "finish_time": "5:00",
        }
    )

    assert edge == {
        "winner_name": "Justin Gaethje",
        "loser_name": "Conor McGregor",
        "event_name": "UFC Test Night",
        "bout_date": "2026-06-14",
        "method": "Decision - Unanimous",
        "promotion": None,
        "weight_class": "Lightweight",
        "scheduled_rounds": 3,
        "finish_round": 3,
        "finish_time": "5:00",
        "source_url": "https://api.balldontlie.io/mma/v1/fights/44",
    }


def test_normalize_skips_unfinished_or_missing_winner() -> None:
    unfinished = {
        "status": "scheduled",
        "fighter1": {"id": 1, "name": "Fighter One"},
        "fighter2": {"id": 2, "name": "Fighter Two"},
        "winner": {"id": 1, "name": "Fighter One"},
    }
    missing_winner = {
        "status": "completed",
        "fighter1": {"id": 1, "name": "Fighter One"},
        "fighter2": {"id": 2, "name": "Fighter Two"},
        "winner": None,
    }

    assert normalize_fight(unfinished) is None
    assert normalize_fight(missing_winner) is None


def test_import_fight_edges_deduplicates_existing_bouts() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    fights = [
        {
            "id": 44,
            "status": "completed",
            "fighter1": {"id": 1, "name": "Conor McGregor"},
            "fighter2": {"id": 2, "name": "Justin Gaethje"},
            "winner": {"id": 2, "name": "Justin Gaethje"},
            "event": {"name": "UFC Test Night", "date": "2026-06-14"},
            "result_method": "Decision",
            "weight_class": {"name": "Lightweight"},
            "finish_round": 3,
        }
    ]

    with Session() as db:
        db.add_all([profile("Conor McGregor"), profile("Justin Gaethje")])
        db.commit()

        first = import_fight_edges(db, fights)
        second = import_fight_edges(db, fights)
        result = db.scalar(select(FightResult).where(FightResult.winner_name == "Justin Gaethje"))

    assert first.imported == 1
    assert first.skipped == 0
    assert second.imported == 0
    assert second.skipped == 1
    assert result is not None
    assert result.winner_profile_id is not None
    assert result.loser_profile_id is not None
    assert result.weight_class == "Lightweight"
    assert result.finish_round == 3


def profile(name: str) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Lightweight",
        age=30,
        height_cm=180,
        reach_cm=182,
        wins=10,
        losses=3,
        ko_rate=0.3,
        submission_rate=0.2,
        takedown_accuracy=0.4,
        takedown_defense=0.7,
        strikes_landed_per_min=4.0,
        strikes_absorbed_per_min=3.0,
        source="test",
    )
